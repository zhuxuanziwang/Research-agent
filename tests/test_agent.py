from __future__ import annotations

from pathlib import Path
import unittest

from research_agent.agent import ResearchPaperAgent
from research_agent.config import Settings


class StubGrokClient:
    def plan(
        self,
        query: str,
        memory: str,
        tools: list[dict[str, str]],
        orchestration_profile: dict | None = None,
    ) -> dict:
        return {
            "objective": query,
            "steps": [
                {
                    "id": "s1",
                    "sub_question": query,
                    "tool": "hybrid_search",
                    "tool_args": {"query": query, "top_k": 5},
                }
            ],
        }

    def reflect(self, step: dict, observation: dict, memory: str) -> dict:
        return {"replan": False, "reason": "enough evidence", "new_steps": []}

    def summarize(self, query: str, memory: str, evidence: list[dict]) -> dict:
        return {
            "answer": f"Summary for: {query}",
            "evidence_points": [f"[{item['paper_id']}] {item['title']}" for item in evidence[:3]],
            "risks": [],
        }


class AgentTests(unittest.TestCase):
    def test_agent_runs_with_compact_trace(self) -> None:
        settings = Settings(max_iterations=4)
        agent = ResearchPaperAgent(
            Path("data/sample_papers.json"),
            settings=settings,
            grok_client=StubGrokClient(),
        )
        result = agent.run("How does hybrid retrieval handle conflicting multilingual papers?")

        self.assertEqual(result["mode"], "live")
        self.assertIn("summary", result)
        self.assertIn("execution_trace", result)
        self.assertGreater(len(result["execution_trace"]), 0)
        self.assertIn("observation_summary", result["execution_trace"][0])
        self.assertNotIn("full_trace", result)


if __name__ == "__main__":
    unittest.main()
