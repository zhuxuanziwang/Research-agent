from __future__ import annotations

import json
from pathlib import Path

from research_agent.schema import PaperChunk, PaperDocument


SECTION_ORDER = ("abstract", "methodology", "findings", "limitations")


def load_papers(data_path: str | Path) -> list[PaperDocument]:
    path = Path(data_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    papers: list[PaperDocument] = []

    for record in records:
        papers.append(PaperDocument(**record))
    return papers


def build_chunks(papers: list[PaperDocument]) -> list[PaperChunk]:
    chunks: list[PaperChunk] = []
    for paper in papers:
        for section in SECTION_ORDER:
            text = getattr(paper, section)
            chunk_id = f"{paper.paper_id}:{section}"
            chunks.append(
                PaperChunk(
                    chunk_id=chunk_id,
                    paper_id=paper.paper_id,
                    title=paper.title,
                    year=paper.year,
                    language=paper.language,
                    section=section,
                    text=text,
                    citations=paper.citations,
                    keywords=paper.keywords,
                    stance=paper.stance,
                )
            )
    return chunks

