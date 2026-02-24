from __future__ import annotations

from collections import defaultdict
from typing import Any

from research_agent.retrieval import HybridRetriever
from research_agent.schema import PaperDocument


class ToolExecutor:
    def __init__(self, retriever: HybridRetriever, papers: list[PaperDocument]):
        self.retriever = retriever
        self.papers = papers
        self.paper_index = {paper.paper_id: paper for paper in papers}
        self.cited_by_index: dict[str, list[str]] = defaultdict(list)
        for paper in papers:
            for cited in paper.citations:
                if cited in self.paper_index:
                    self.cited_by_index[cited].append(paper.paper_id)

    def describe(self) -> list[dict[str, str]]:
        return [
            {
                "name": "hybrid_search",
                "description": "hybrid semantic+keyword search over paper sections",
            },
            {
                "name": "timeline_scan",
                "description": "fetch chronologically sorted evidence snippets",
            },
            {
                "name": "citation_graph",
                "description": "inspect citation and reverse-citation connections",
            },
        ]

    def run(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name == "hybrid_search":
            return self.hybrid_search(
                query=kwargs.get("query", ""), top_k=int(kwargs.get("top_k", 6))
            )
        if tool_name == "timeline_scan":
            return self.timeline_scan(
                query=kwargs.get("query", ""), top_k=int(kwargs.get("top_k", 6))
            )
        if tool_name == "citation_graph":
            return self.citation_graph(paper_id=kwargs.get("paper_id", ""))

        return {"tool": tool_name, "error": "unknown tool"}

    def hybrid_search(self, query: str, top_k: int = 6) -> dict[str, Any]:
        hits = self.retriever.search(query=query, top_k=top_k)
        serialized = [hit.to_dict() for hit in hits]
        unique_papers = {item["paper_id"] for item in serialized}
        stances = {item["stance"] for item in serialized}
        citations = [
            f"[{item['paper_id']}] {item['title']} ({item['year']})"
            for item in serialized
        ]

        return {
            "tool": "hybrid_search",
            "query": query,
            "hits": serialized,
            "citations": citations,
            "ambiguity": {
                "low_coverage": len(unique_papers) < 2,
                "conflicting_stances": len(stances) > 1,
            },
        }

    def timeline_scan(self, query: str, top_k: int = 6) -> dict[str, Any]:
        hits = self.retriever.search(query=query, top_k=max(top_k, 10))
        serialized = [hit.to_dict() for hit in hits]
        serialized.sort(key=lambda item: item["year"])
        sliced = serialized[:top_k]
        citations = [f"[{item['paper_id']}] {item['title']} ({item['year']})" for item in sliced]
        return {
            "tool": "timeline_scan",
            "query": query,
            "hits": sliced,
            "citations": citations,
            "ambiguity": {"low_coverage": len(sliced) < 2, "conflicting_stances": False},
        }

    def citation_graph(self, paper_id: str) -> dict[str, Any]:
        paper = self.paper_index.get(paper_id)
        if not paper:
            return {
                "tool": "citation_graph",
                "paper_id": paper_id,
                "error": "paper not found",
                "citations": [],
                "ambiguity": {"low_coverage": True, "conflicting_stances": False},
            }

        outgoing = paper.citations
        incoming = self.cited_by_index.get(paper_id, [])
        citations = [f"[{paper.paper_id}] {paper.title} ({paper.year})"]
        citations.extend([f"[{cid}] cited relation" for cid in outgoing + incoming])

        return {
            "tool": "citation_graph",
            "paper_id": paper.paper_id,
            "title": paper.title,
            "year": paper.year,
            "outgoing": outgoing,
            "incoming": incoming,
            "citations": citations,
            "ambiguity": {
                "low_coverage": len(outgoing) + len(incoming) < 2,
                "conflicting_stances": False,
            },
        }

