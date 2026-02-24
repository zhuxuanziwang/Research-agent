from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    grok_api_key: str = ""
    grok_base_url: str = "https://api.x.ai/v1/chat/completions"
    grok_model: str = "grok-2-latest"
    grok_mock: bool = True
    top_k: int = 6
    max_iterations: int = 8
    memory_window: int = 12
    retrieval_alpha: float = 0.55

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("GROK_API_KEY", "").strip()
        explicit_mock = os.getenv("GROK_MOCK")
        grok_mock = _as_bool(explicit_mock, default=not bool(api_key))

        return cls(
            grok_api_key=api_key,
            grok_base_url=os.getenv(
                "GROK_BASE_URL", "https://api.x.ai/v1/chat/completions"
            ).strip(),
            grok_model=os.getenv("GROK_MODEL", "grok-2-latest").strip(),
            grok_mock=grok_mock,
            top_k=int(os.getenv("TOP_K", "6")),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "8")),
            memory_window=int(os.getenv("MEMORY_WINDOW", "12")),
            retrieval_alpha=float(os.getenv("RETRIEVAL_ALPHA", "0.55")),
        )

