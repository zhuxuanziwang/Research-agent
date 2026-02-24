from __future__ import annotations

import math
import re
from collections import Counter

from research_agent.schema import PaperChunk, RetrievalHit


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0

    common = set(vec_a).intersection(vec_b)
    numerator = sum(vec_a[tok] * vec_b[tok] for tok in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return numerator / (norm_a * norm_b)


class HybridRetriever:
    def __init__(self, chunks: list[PaperChunk], alpha: float = 0.55):
        self.chunks = chunks
        self.alpha = alpha

        doc_freq: Counter[str] = Counter()
        self.chunk_tokens: dict[str, list[str]] = {}
        self.chunk_vectors: dict[str, dict[str, float]] = {}

        for chunk in chunks:
            merged = " ".join([chunk.title, chunk.text, " ".join(chunk.keywords)])
            tokens = tokenize(merged)
            self.chunk_tokens[chunk.chunk_id] = tokens
            doc_freq.update(set(tokens))

        total_docs = max(len(chunks), 1)
        self.idf: dict[str, float] = {}
        for token, freq in doc_freq.items():
            self.idf[token] = math.log((1.0 + total_docs) / (1.0 + freq)) + 1.0

        for chunk in chunks:
            self.chunk_vectors[chunk.chunk_id] = self._tfidf_vector(
                self.chunk_tokens[chunk.chunk_id]
            )

    def _tfidf_vector(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = max(len(tokens), 1)
        return {tok: (count / total) * self.idf.get(tok, 1.0) for tok, count in tf.items()}

    def search(self, query: str, top_k: int = 6) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        query_set = set(query_tokens)
        query_vector = self._tfidf_vector(query_tokens)
        hits: list[RetrievalHit] = []

        for chunk in self.chunks:
            tokens = self.chunk_tokens[chunk.chunk_id]
            token_set = set(tokens)
            overlap = query_set.intersection(token_set)
            keyword_score = len(overlap) / max(len(query_set), 1)

            semantic_score = cosine_similarity(
                query_vector, self.chunk_vectors[chunk.chunk_id]
            )
            hybrid_score = self.alpha * semantic_score + (1.0 - self.alpha) * keyword_score

            if hybrid_score <= 0:
                continue

            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    keyword_score=keyword_score,
                    semantic_score=semantic_score,
                    hybrid_score=hybrid_score,
                )
            )

        hits.sort(
            key=lambda item: (item.hybrid_score, item.semantic_score, item.chunk.year),
            reverse=True,
        )
        return hits[:top_k]

