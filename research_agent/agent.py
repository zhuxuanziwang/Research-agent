from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_agent.config import Settings
from research_agent.dataset import build_chunks, load_papers
from research_agent.grok import GrokClient
from research_agent.memory import ContextMemory
from research_agent.retrieval import HybridRetriever
from research_agent.tools import ToolExecutor


class ResearchPaperAgent:
    def __init__(self, data_path: str | Path, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.data_path = Path(data_path)
        self.papers = load_papers(self.data_path)
        self.chunks = build_chunks(self.papers)
        self.retriever = HybridRetriever(
            self.chunks, alpha=self.settings.retrieval_alpha
        )
        self.tools = ToolExecutor(self.retriever, self.papers)
        self.memory = ContextMemory(max_events=self.settings.memory_window)
        self.grok = GrokClient(self.settings)
        self.last_primary_paper: str | None = None

    def _run_step(self, step: dict[str, Any]) -> dict[str, Any]:
        tool = step.get("tool", "hybrid_search")
        args = dict(step.get("tool_args", {}))
        if "query" not in args and step.get("sub_question"):
            args["query"] = step["sub_question"]
        args.setdefault("top_k", self.settings.top_k)

        if tool == "citation_graph" and args.get("paper_id") == "auto":
            args["paper_id"] = self.last_primary_paper or self.papers[0].paper_id

        observation = self.tools.run(tool, **args)
        hits = observation.get("hits", [])
        if hits:
            self.last_primary_paper = hits[0]["paper_id"]
        return observation

    def run(self, query: str) -> dict[str, Any]:
        plan = self.grok.plan(
            query=query,
            memory=self.memory.snapshot(),
            tools=self.tools.describe(),
        )
        steps = list(plan.get("steps", []))
        self.memory.add_event("planner", json.dumps(plan, ensure_ascii=False))

        execution_trace: list[dict[str, Any]] = []
        pooled_hits: dict[str, dict[str, Any]] = {}

        for _ in range(self.settings.max_iterations):
            if not steps:
                break

            step = steps.pop(0)
            observation = self._run_step(step)

            for hit in observation.get("hits", []):
                current = pooled_hits.get(hit["chunk_id"])
                if current is None or hit["hybrid_score"] > current["hybrid_score"]:
                    pooled_hits[hit["chunk_id"]] = hit

            self.memory.add_event(
                "tool",
                json.dumps(
                    {
                        "step_id": step.get("id"),
                        "tool": step.get("tool"),
                        "sub_question": step.get("sub_question"),
                        "result_preview": observation.get("hits", [])[:2],
                    },
                    ensure_ascii=False,
                ),
                citations=observation.get("citations", []),
            )

            reflection = self.grok.reflect(
                step=step, observation=observation, memory=self.memory.snapshot()
            )
            self.memory.add_event("reflect", json.dumps(reflection, ensure_ascii=False))

            execution_trace.append(
                {"step": step, "observation": observation, "reflection": reflection}
            )
            if reflection.get("replan") and reflection.get("new_steps"):
                steps = list(reflection["new_steps"]) + steps

        evidence = sorted(
            pooled_hits.values(),
            key=lambda item: (item["hybrid_score"], item["year"]),
            reverse=True,
        )[:8]
        final_summary = self.grok.summarize(
            query=query, memory=self.memory.snapshot(), evidence=evidence
        )

        return {
            "query": query,
            "mode": "mock" if self.settings.grok_mock else "live",
            "plan": plan,
            "execution_trace": execution_trace,
            "summary": final_summary,
            "citations": self.memory.top_citations(limit=8),
            "evidence": evidence,
        }

