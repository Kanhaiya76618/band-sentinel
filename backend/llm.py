"""
Aegis — the LLM layer.

Three interchangeable clients behind one interface:

    * OfflineLLM     — deterministic scripted reasoning, ZERO keys. Powers the
                       offline demo so the cascade always lands on camera.
    * AIMLClient     — AI/ML API (OpenAI-compatible). Used by observer /
                       remediator / commander  -> targets the AI/ML API prize.
    * FeatherlessLLM — Featherless AI (OpenAI-compatible). Used by
                       diagnostician / validator -> targets the Featherless prize.

The cross-framework + cross-provider split is deliberate: it's what scores the
"agents collaborate across frameworks" criterion and makes you eligible for BOTH
partner prizes at once.

NOTE FOR KICKOFF (first time using these): the base URLs and model ids below are
the OpenAI-compatible defaults. Confirm the exact `base_url` and a current model
id from each provider's setup guide before the live run — they occasionally
change, and you only want to debug that once.
"""
from __future__ import annotations

import os
from typing import Optional


class LLMClient:
    """Minimal chat interface. Agents only ever call `.complete()`."""

    def complete(self, system: str, user: str, **kw) -> str:  # pragma: no cover
        raise NotImplementedError


class OfflineLLM(LLMClient):
    """
    Returns canned-but-coherent reasoning keyed by (role, tag). The *logic* of
    the system (anomaly detection, chaos validation, cost math) is real Python
    elsewhere — this only supplies the natural-language phrasing so the room
    reads like a real conversation with zero API calls.
    """

    def __init__(self, scripts: Optional[dict[tuple[str, str], str]] = None):
        self._scripts = scripts or {}

    def register(self, role: str, tag: str, text: str) -> None:
        self._scripts[(role, tag)] = text

    def complete(self, system: str, user: str, role: str = "", tag: str = "", **kw) -> str:
        return self._scripts.get((role, tag), user)


class _OpenAICompatible(LLMClient):
    """Shared implementation for any OpenAI-compatible /chat/completions API."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, temperature: float = 0.2, **kw) -> str:
        import httpx  # lazy import: offline mode needs no network deps

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class AIMLClient(_OpenAICompatible):
    """AI/ML API — https://aimlapi.com  (OpenAI-compatible)."""

    def __init__(self, model: str = "gpt-4o-mini"):
        super().__init__(
            base_url=os.getenv("AIML_BASE_URL", "https://api.aimlapi.com/v1"),
            api_key=os.getenv("AIML_API_KEY", ""),
            model=os.getenv("AIML_MODEL", model),
        )


class FeatherlessLLM(_OpenAICompatible):
    """Featherless AI — https://featherless.ai  (OpenAI-compatible)."""

    def __init__(self, model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"):
        super().__init__(
            base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            api_key=os.getenv("FEATHERLESS_API_KEY", ""),
            model=os.getenv("FEATHERLESS_MODEL", model),
        )


def make_llm(provider: str) -> LLMClient:
    """
    Factory. provider in {"offline","aiml","featherless"}.
    Offline mode is the default so `python -m backend.run` works with no setup.
    """
    mode = os.getenv("LLM_MODE", "offline").lower()
    if mode == "offline":
        return OfflineLLM()
    if provider == "featherless":
        return FeatherlessLLM()
    return AIMLClient()
