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

    def _default_plan(self, query: str) -> dict[str, Any]:
        return {
            "objective": query,
            "steps": [
                {
                    "id": "s1",
                    "sub_question": f"Break down scope and time range for: {query}",
                    "tool": "timeline_scan",
                    "tool_args": {"query": query, "top_k": 5},
                },
                {
                    "id": "s2",
                    "sub_question": query,
                    "tool": "hybrid_search",
                    "tool_args": {"query": query, "top_k": 6},
                },
                {
                    "id": "s3",
                    "sub_question": f"{query} contradictory multilingual evidence",
                    "tool": "hybrid_search",
                    "tool_args": {"query": f"{query} contradictory multilingual", "top_k": 6},
                },
                {
                    "id": "s4",
                    "sub_question": "Inspect citation lineage of strongest source",
                    "tool": "citation_graph",
                    "tool_args": {"paper_id": "auto"},
                },
            ],
        }

    def _default_summary(self, query: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        take = evidence[:4]
        points = [
            f"- [{item['paper_id']}] {item['title']} ({item['year']}), {item['section']}"
            for item in take
        ]
        return {
            "answer": (
                f"Query: {query}\n"
                "Synthesis: Hybrid retrieval over mock paper corpus found converging evidence "
                "that citation-grounded retrieval improves review quality, but results degrade "
                "when PDF parsing is noisy or multilingual coverage is weak."
            ),
            "evidence_points": points,
            "risks": [
                "Potential benchmark inconsistency across venues",
                "Limited longitudinal validation beyond 2025",
            ],
        }

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
        if self.settings.grok_mock or not self.settings.grok_api_key:
            return ""

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
                "Authorization": f"Bearer {self.settings.grok_api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return ""

        choices = body.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    def plan(self, query: str, memory: str, tools: list[dict[str, str]]) -> dict[str, Any]:
        if self.settings.grok_mock or not self.settings.grok_api_key:
            return self._default_plan(query)

        prompt = {
            "query": query,
            "memory": memory,
            "tools": tools,
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
                "use 3-6 steps",
                "prefer hybrid_search for evidence",
                "must include at least one step to resolve ambiguities",
            ],
        }

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
        if not parsed.get("steps"):
            return self._default_plan(query)
        return parsed

    def reflect(
        self, step: dict[str, Any], observation: dict[str, Any], memory: str
    ) -> dict[str, Any]:
        if self.settings.grok_mock or not self.settings.grok_api_key:
            ambiguity = observation.get("ambiguity", {})
            low_coverage = bool(ambiguity.get("low_coverage"))
            conflicts = bool(ambiguity.get("conflicting_stances"))
            replan = low_coverage or conflicts
            reason = "evidence coverage is narrow" if low_coverage else "conflicting findings"
            reason = reason if replan else "sufficient evidence for next step"
            new_steps: list[dict[str, Any]] = []
            if replan:
                new_steps.append(
                    {
                        "id": f"r-{step.get('id', 'x')}",
                        "sub_question": f"Resolve ambiguity for: {step.get('sub_question', '')}",
                        "tool": "hybrid_search",
                        "tool_args": {
                            "query": f"{step.get('sub_question', '')} replication study limitations",
                            "top_k": 6,
                        },
                    }
                )
            return {"replan": replan, "reason": reason, "new_steps": new_steps}

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
            return {"replan": False, "reason": "invalid response", "new_steps": []}
        return parsed

    def summarize(
        self, query: str, memory: str, evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if self.settings.grok_mock or not self.settings.grok_api_key:
            return self._default_summary(query, evidence)

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
        if not parsed:
            return self._default_summary(query, evidence)
        return parsed
