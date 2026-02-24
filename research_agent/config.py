from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    grok_api_key: str = ""
    grok_base_url: str = "https://api.x.ai/v1/chat/completions"
    grok_model: str = "grok-4-1-fast-reasoning"
    top_k: int = 6
    max_iterations: int = 8
    memory_window: int = 12
    retrieval_alpha: float = 0.55

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("GROK_API_KEY", "").strip()

        return cls(
            grok_api_key=api_key,
            grok_base_url=os.getenv(
                "GROK_BASE_URL", "https://api.x.ai/v1/chat/completions"
            ).strip(),
            grok_model=os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip(),
            top_k=int(os.getenv("TOP_K", "6")),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "8")),
            memory_window=int(os.getenv("MEMORY_WINDOW", "12")),
            retrieval_alpha=float(os.getenv("RETRIEVAL_ALPHA", "0.55")),
        )
