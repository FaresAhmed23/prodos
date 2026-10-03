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

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OWNED BY MOHAMED AHMED (AI quality). Prompt wording is his to change; the
# provider does not care as long as the model answers with the three JSON keys.
# Kept in the module so `explanation_logs` can record the exact prompt used.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You write security alerts for the owner of a small business \
(café, clinic, small hotel, retail store) who offers customer WiFi but has no \
security expertise.

You are given one detected event. Reply with a JSON object and nothing else, \
using exactly these three string keys:

  "title"                - one short sentence, headline style
  "explanation"          - at most 3 short sentences
  "recommended_action"   - exactly one concrete thing this owner can do today

Rules you must follow:
- The reader is non-technical. Never use the words "deauthentication frame", \
"deauth", "BSSID", "802.11", "packet", "probe request", "beacon", "channel", \
"signal strength", or "SSID". Describe what it means for the business instead.
- Lead with what is happening in the owner's own terms (customers, WiFi, \
money, passwords), never with the mechanism.
- Say why it matters to them, then stop. Do not add reassurance beyond one line.
- "recommended_action" must be a single specific action, not "contact your \
IT department" and not "monitor the situation".
- Severity 1-3: calm and factual. Severity 4-7: matter-of-fact, still not alarmist. \
Severity 8-10: urgent and direct, but never panic-inducing and never use \
exclamation marks.
- Never invent technical detail that is not in the event."""

_USER_TEMPLATE = """Detected event:
{event}

Write the alert."""


def build_prompt(event: DetectionEvent) -> str:
    # model_dump_json, not model_dump: detected_at is a datetime and the JSON
    # column on the log row cannot store one.
    return _USER_TEMPLATE.format(event=event.model_dump_json(indent=2))


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
    ) -> None:
        self._url = f"{base.rstrip('/')}/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout

    def build_prompt(self, event: DetectionEvent) -> str:
        return build_prompt(event)

    async def explain(self, event: DetectionEvent) -> Explanation:
        payload = {
            "model": self._model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
