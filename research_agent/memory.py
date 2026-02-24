from __future__ import annotations

from collections import Counter

from research_agent.schema import Event


class ContextMemory:
    def __init__(self, max_events: int = 12, compress_batch: int = 4):
        self.max_events = max_events
        self.compress_batch = compress_batch
        self.events: list[Event] = []
        self.summary: list[str] = []
        self.citation_counter: Counter[str] = Counter()

    def add_event(self, role: str, content: str, citations: list[str] | None = None) -> None:
        citations = citations or []
        self.events.append(Event(role=role, content=content, citations=citations))
        self.citation_counter.update(citations)
        if len(self.events) > self.max_events:
            self._compress_oldest()

    def _compress_oldest(self) -> None:
        batch = self.events[: self.compress_batch]
        self.events = self.events[self.compress_batch :]
        compact = " | ".join(f"{item.role}:{item.content[:180]}" for item in batch)
        self.summary.append(compact)

    def snapshot(self) -> str:
        summary_text = "\n".join(self.summary[-3:])
        event_text = "\n".join(
            f"[{event.role}] {event.content[:500]}" for event in self.events[-self.max_events :]
        )
        return f"Summary Memory:\n{summary_text}\n\nRecent Events:\n{event_text}".strip()

    def top_citations(self, limit: int = 6) -> list[str]:
        return [citation for citation, _ in self.citation_counter.most_common(limit)]

