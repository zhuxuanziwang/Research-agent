from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PaperDocument:
    paper_id: str
    title: str
    year: int
    language: str
    venue: str
    authors: list[str]
    abstract: str
    methodology: str
    findings: str
    limitations: str
    citations: list[str]
    keywords: list[str]
    stance: str = "mixed"


@dataclass(slots=True)
class PaperChunk:
    chunk_id: str
    paper_id: str
    title: str
    year: int
    language: str
    section: str
    text: str
    citations: list[str]
    keywords: list[str]
    stance: str


@dataclass(slots=True)
class RetrievalHit:
    chunk: PaperChunk
    keyword_score: float
    semantic_score: float
    hybrid_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "paper_id": self.chunk.paper_id,
            "title": self.chunk.title,
            "year": self.chunk.year,
            "language": self.chunk.language,
            "section": self.chunk.section,
            "text": self.chunk.text,
            "citations": self.chunk.citations,
            "keywords": self.chunk.keywords,
            "stance": self.chunk.stance,
            "keyword_score": round(self.keyword_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "hybrid_score": round(self.hybrid_score, 4),
        }


@dataclass(slots=True)
class Event:
    role: str
    content: str
    citations: list[str] = field(default_factory=list)

