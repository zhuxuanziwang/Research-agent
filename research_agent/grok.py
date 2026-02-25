from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from research_agent.config import Settings


class GrokClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _extract_json(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    def _chat(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        if not self.settings.grok_api_key:
            raise RuntimeError("GROK_API_KEY is required for live reasoning.")

        payload = {
            "model": self.settings.grok_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.settings.grok_base_url,
            method="POST",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ResearchAgent/1.0 (+https://github.com/zhuxuanziwang/Research-agent)",
                "Authorization": f"Bearer {self.settings.grok_api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Grok API HTTP {exc.code}: {detail[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Grok API network error: {exc}") from exc
        except TimeoutError as exc:
            raise RuntimeError("Grok API timeout.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Grok API returned invalid JSON envelope.") from exc

        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("Grok API response missing choices.")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Grok API response missing message content.")
        return content

    def plan(
        self,
        query: str,
        memory: str,
        tools: list[dict[str, str]],
        orchestration_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        orchestration_profile = orchestration_profile or {}
        intent = orchestration_profile.get("intent", "focused_analysis")
        prompt = {
            "query": query,
            "memory": memory,
            "tools": tools,
            "orchestration_profile": orchestration_profile,
            "schema": {
                "objective": "string",
                "steps": [
                    {
                        "id": "string",
                        "sub_question": "string",
                        "tool": "string",
                        "tool_args": "object",
                    }
                ],
            },
            "rules": [
                "use 3-8 steps",
                "prefer hybrid_search for evidence",
                "must include at least one step to resolve ambiguities",
                "only request sections present in orchestration_profile.available_sections",
                "if tool is citation_graph, set tool_args.paper_id explicitly or use 'auto'",
                "avoid repeating near-duplicate steps",
            ],
        }
        if intent == "multi_paper_overview":
            prompt["rules"].extend(
                [
                    "must include at least one step that enumerates all distinct papers",
                    "must include one step to produce per-paper summary before cross-paper synthesis",
                    "avoid TOC-only or intro-only extraction focus",
                ]
            )

        content = self._chat(
            [
                {
                    "role": "system",
                    "content": "You are a planning reasoner. Return strict JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        parsed = self._extract_json(content)
        steps = parsed.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RuntimeError("Grok plan response is invalid: missing non-empty steps.")
        return parsed

    def reflect(
        self, step: dict[str, Any], observation: dict[str, Any], memory: str
    ) -> dict[str, Any]:
        prompt = {
            "step": step,
            "observation": observation,
            "memory": memory,
            "schema": {
                "replan": "boolean",
                "reason": "string",
                "new_steps": [
                    {
                        "id": "string",
                        "sub_question": "string",
                        "tool": "string",
                        "tool_args": "object",
                    }
                ],
            },
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": "Evaluate ambiguity and return strict JSON.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.1,
        )
        parsed = self._extract_json(content)
        if "replan" not in parsed:
            raise RuntimeError("Grok reflection response is invalid: missing replan.")
        parsed.setdefault("reason", "")
        parsed.setdefault("new_steps", [])
        return parsed

    def summarize(
        self, query: str, memory: str, evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        prompt = {
            "query": query,
            "memory": memory,
            "evidence": evidence,
            "schema": {
                "answer": "string",
                "evidence_points": ["string"],
                "risks": ["string"],
            },
            "rules": [
                "ground every claim in evidence",
                "point out ambiguity and contradictions",
                "be concise",
            ],
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": "You are a synthesis reasoner. Return strict JSON.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.15,
        )
        parsed = self._extract_json(content)
        if not parsed.get("answer"):
            raise RuntimeError("Grok summary response is invalid: missing answer.")
        parsed.setdefault("evidence_points", [])
        parsed.setdefault("risks", [])
        return parsed
