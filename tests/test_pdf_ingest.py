from __future__ import annotations

import unittest

from research_agent.pdf_ingest import infer_language, split_sections


class PdfIngestTests(unittest.TestCase):
    def test_split_sections_from_headings(self) -> None:
        text = """
Abstract
This paper studies hybrid retrieval for review agents.

Methodology
We evaluate dense retrieval and keyword search over multilingual corpora.

Findings
Hybrid retrieval improves contradiction recall by 18%.

Limitations
The benchmark has limited coverage for low-resource languages.
"""
        sections = split_sections(text)
        self.assertIn("hybrid retrieval", sections["abstract"].lower())
        self.assertIn("evaluate dense retrieval", sections["methodology"].lower())
        self.assertIn("18%", sections["findings"])
        self.assertIn("limited coverage", sections["limitations"].lower())

    def test_language_inference(self) -> None:
        self.assertEqual(infer_language("本文研究跨语言检索与引用链。"), "zh")
        self.assertEqual(infer_language("Este estudio presenta resultados en salud pública."), "es")
        self.assertEqual(infer_language("This paper evaluates long-context retrieval."), "en")


if __name__ == "__main__":
    unittest.main()

