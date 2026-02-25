from __future__ import annotations

import unittest

from research_agent.pdf_ingest import _build_paper_id, infer_language, split_sections


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

    def test_generated_paper_id_is_collision_resistant(self) -> None:
        one = _build_paper_id(0, "ACL 26 LoRA submission", "REAL")
        two = _build_paper_id(1, "ACL 26 LoRA submission", "REAL")
        three = _build_paper_id(0, "ICME 2025 CaTeR", "REAL")
        self.assertNotEqual(one, two)
        self.assertNotEqual(one, three)


if __name__ == "__main__":
    unittest.main()
