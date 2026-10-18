"""LLM explanations over any OpenAI-compatible chat-completions endpoint.

Deliberately not the `openai` SDK: the spec only needs base URL + model + key, and
a raw POST is ~30 lines. That keeps the provider swappable (OpenAI, Ollama,
LM Studio, vLLM, a mock) without a dependency per vendor.

Every failure mode raises. `alerts.handle_detection_event` catches, logs a
warning and falls back to the template, so an unreachable model costs tone, not
the alert.
"""

import json
import logging

import httpx

from ..schemas import DetectionEvent
from .explanation import Explanation

from prompt import build_prompt, get_system_prompt

log = logging.getLogger(__name__)

def _extract(content: str) -> Explanation:
    """Pull the three fields out of a reply that may be fenced or chatty."""
    text = content.strip()
    if text.startswith("```"):
        # ```json ... ``` or ``` ... ```
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {content[:200]!r}")
    data = json.loads(text[start : end + 1])

    fields = {
        key: str(data[key]).strip()
        for key in ("title", "explanation", "recommended_action")
        if data.get(key)
    }
    if len(fields) != 3:
        raise ValueError(f"reply missing fields, got {sorted(fields)}")
    return Explanation(**fields)


class LLMProvider:
    """Chat-completions provider. Raises on any failure so the caller can fall back."""

    name = "llm"

    def __init__(
        self,
        base: str,
        model: str,
        api_key: str,
        timeout: float = 5.0,
        language: str = "en",
        prompt_version: str = "2.1"
    ) -> None:
        self._url = f"{base.rstrip('/')}/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout
        self._lang = language
        self._prompt_version = prompt_version

    def build_prompt(self, event: DetectionEvent) -> str:
        return build_prompt(event)

    async def explain(self, event: DetectionEvent) -> Explanation:
        payload = {
            "model": self._model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": get_system_prompt(language=self._lang, version=self._prompt_version)},
                {"role": "user", "content": build_prompt(event)},
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            body = response.json()

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"unexpected chat-completions shape: {body}") from exc

        return _extract(content)
