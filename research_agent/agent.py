from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from research_agent.config import Settings
from research_agent.dataset import build_chunks, load_papers
from research_agent.grok import GrokClient
from research_agent.memory import ContextMemory
from research_agent.retrieval import HybridRetriever
from research_agent.tools import ToolExecutor


class ResearchPaperAgent:
    def __init__(
        self,
        data_path: str | Path,
        settings: Settings | None = None,
        grok_client: GrokClient | None = None,
    ):
        self.settings = settings or Settings.from_env()
        self.data_path = Path(data_path)
        self.papers = load_papers(self.data_path)
        self.chunks = build_chunks(self.papers)
        self.retriever = HybridRetriever(
            self.chunks, alpha=self.settings.retrieval_alpha
        )
        self.tools = ToolExecutor(self.retriever, self.papers)
        self.memory = ContextMemory(max_events=self.settings.memory_window)
        self.grok = grok_client or GrokClient(self.settings)
        self.last_primary_paper: str | None = None

    def _infer_query_intent(self, query: str) -> str:
        low = query.lower()
        multi_markers = (
            "these papers",
            "these paper",
            "what are these papers",
            "what are these paper",
            "what's these paper",
            "each paper",
            "paper by paper",
            "这几篇",
            "每篇",
            "分别",
        )
        if any(marker in low for marker in multi_markers):
            return "multi_paper_overview"
        return "focused_analysis"

    def _build_orchestration_profile(self, query: str) -> dict[str, Any]:
        intent = self._infer_query_intent(query)
        paper_catalog = [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
            }
            for paper in self.papers
        ]
        return {
            "intent": intent,
            "available_sections": ["abstract", "methodology", "findings", "limitations"],
            "paper_catalog": paper_catalog,
            "guidance": {
                "multi_paper_overview": [
                    "summarize each paper separately before cross-paper synthesis",
                    "avoid asking for sections that do not exist in available_sections",
                    "prioritize broad coverage across distinct paper_id values",
                ],
                "focused_analysis": [
                    "go deeper on one focal paper while checking contradictory evidence",
                    "use citation_graph only when paper_id is explicit or auto-selected",
                ],
            },
        }

    def _compact_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "tool": observation.get("tool"),
            "ambiguity": observation.get("ambiguity", {}),
            "citation_count": len(observation.get("citations", [])),
        }
        hits = observation.get("hits", [])
        if isinstance(hits, list):
            top_hits: list[dict[str, Any]] = []
            for item in hits[:3]:
                top_hits.append(
                    {
                        "paper_id": item.get("paper_id"),
                        "title": item.get("title"),
                        "year": item.get("year"),
                        "section": item.get("section"),
                        "hybrid_score": round(float(item.get("hybrid_score", 0.0)), 4),
                    }
                )
            summary["hit_count"] = len(hits)
            summary["top_hits"] = top_hits
        if observation.get("tool") == "citation_graph":
            summary["graph"] = {
                "paper_id": observation.get("paper_id"),
                "title": observation.get("title"),
                "outgoing_count": len(observation.get("outgoing", [])),
                "incoming_count": len(observation.get("incoming", [])),
            }
        return summary

    def _run_step(self, step: dict[str, Any]) -> dict[str, Any]:
        tool = step.get("tool", "hybrid_search")
        args = dict(step.get("tool_args", {}))
        if "query" not in args and step.get("sub_question"):
            args["query"] = step["sub_question"]
        args.setdefault("top_k", self.settings.top_k)

        if tool == "citation_graph":
            paper_id = args.get("paper_id")
            if paper_id in (None, "", "auto"):
                args["paper_id"] = self.last_primary_paper or self.papers[0].paper_id

        observation = self.tools.run(tool, **args)
        hits = observation.get("hits", [])
        if hits:
            self.last_primary_paper = hits[0]["paper_id"]
        return observation

    def run(
        self,
        query: str,
        include_full_trace: bool = False,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        def emit(event: dict[str, Any]) -> None:
            if progress_callback is not None:
                progress_callback(event)

        orchestration_profile = self._build_orchestration_profile(query)
        emit({"stage": "planning"})
        plan = self.grok.plan(
            query=query,
            memory=self.memory.snapshot(),
            tools=self.tools.describe(),
            orchestration_profile=orchestration_profile,
        )
        steps = list(plan.get("steps", []))
        emit(
            {
                "stage": "planned",
                "total_steps": len(steps),
                "plan_steps": [
                    {
                        "step_id": step.get("id"),
                        "sub_question": step.get("sub_question"),
                        "tool": step.get("tool"),
                    }
                    for step in steps
                ],
            }
        )
        self.memory.add_event("planner", json.dumps(plan, ensure_ascii=False))

        execution_trace: list[dict[str, Any]] = []
        full_trace: list[dict[str, Any]] = []
        pooled_hits: dict[str, dict[str, Any]] = {}
        executed_count = 0
        expected_total_steps = len(steps)

        for _ in range(self.settings.max_iterations):
            if not steps:
                break

            step = steps.pop(0)
            executed_count += 1
            emit(
                {
                    "stage": "step_started",
                    "step_index": executed_count,
                    "total_steps": expected_total_steps,
                    "step_id": step.get("id"),
                    "sub_question": step.get("sub_question"),
                    "tool": step.get("tool"),
                }
            )
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

            compact = {
                "step_id": step.get("id"),
                "sub_question": step.get("sub_question"),
                "tool": step.get("tool"),
                "observation_summary": self._compact_observation(observation),
                "reflection": {
                    "replan": bool(reflection.get("replan")),
                    "reason": reflection.get("reason", ""),
                    "new_steps_count": len(reflection.get("new_steps", [])),
                },
            }
            execution_trace.append(compact)
            emit(
                {
                    "stage": "step_finished",
                    "step_index": executed_count,
                    "total_steps": expected_total_steps,
                    "trace_entry": compact,
                }
            )
            if include_full_trace:
                full_trace.append(
                    {"step": step, "observation": observation, "reflection": reflection}
                )
            if reflection.get("replan") and reflection.get("new_steps"):
                new_steps = list(reflection["new_steps"])
                steps = new_steps + steps
                expected_total_steps += len(new_steps)
                emit(
                    {
                        "stage": "replanned",
                        "added_steps": len(new_steps),
                        "total_steps": expected_total_steps,
                    }
                )

        evidence = sorted(
            pooled_hits.values(),
            key=lambda item: (item["hybrid_score"], item["year"]),
            reverse=True,
        )[:8]
        emit(
            {
                "stage": "summarizing",
                "evidence_count": len(evidence),
                "executed_steps": executed_count,
            }
        )
        final_summary = self.grok.summarize(
            query=query, memory=self.memory.snapshot(), evidence=evidence
        )

        result = {
            "query": query,
            "mode": "live",
            "data_path": str(self.data_path),
            "paper_count": len(self.papers),
            "plan": plan,
            "execution_trace": execution_trace,
            "summary": final_summary,
            "citations": self.memory.top_citations(limit=8),
            "evidence": evidence,
        }
        if include_full_trace:
            result["full_trace"] = full_trace
        emit(
            {
                "stage": "done",
                "executed_steps": executed_count,
                "total_steps": expected_total_steps,
            }
        )
        return result
