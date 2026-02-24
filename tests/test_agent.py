from __future__ import annotations

from pathlib import Path
import unittest

from research_agent.agent import ResearchPaperAgent
from research_agent.config import Settings


class AgentTests(unittest.TestCase):
    def test_agent_runs_with_mock_grok(self) -> None:
        settings = Settings(grok_mock=True, max_iterations=6)
        agent = ResearchPaperAgent(Path("data/mock_papers.json"), settings=settings)
        result = agent.run("How does hybrid retrieval handle conflicting multilingual papers?")

        self.assertIn("summary", result)
        self.assertIn("execution_trace", result)
        self.assertGreater(len(result["execution_trace"]), 0)
        self.assertGreater(len(result["citations"]), 0)


if __name__ == "__main__":
    unittest.main()

