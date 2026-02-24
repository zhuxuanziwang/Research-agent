from __future__ import annotations

from pathlib import Path
import unittest

from research_agent.dataset import build_chunks, load_papers
from research_agent.retrieval import HybridRetriever


class RetrievalTests(unittest.TestCase):
    def test_hybrid_search_returns_ranked_hits(self) -> None:
        papers = load_papers(Path("data/sample_papers.json"))
        chunks = build_chunks(papers)
        retriever = HybridRetriever(chunks)

        hits = retriever.search("hybrid retrieval 跨语言 evidencia conflictiva", top_k=8)
        self.assertGreaterEqual(len(hits), 3)
        self.assertGreaterEqual(hits[0].hybrid_score, hits[-1].hybrid_score)
        self.assertTrue(any(hit.chunk.language in {"zh", "es"} for hit in hits))


if __name__ == "__main__":
    unittest.main()
