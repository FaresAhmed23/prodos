"""Detection event -> stored Event -> generated Alert.

Deliberately has no WebSocket broadcaster and does not import `mqtt`: the caller
owns fan-out. That keeps the dependency one-way (mqtt -> alerts) instead of
circular, and keeps this module testable with a fake provider and no broker.
"""

import asyncio
import json
import logging
import uuid

from .ai.explanation import Explanation
from .ai.llm_provider import LLMProvider
from .ai.template_provider import TemplateProvider
from .config import settings
from .database import SessionLocal
from .models import Alert, Event, ExplanationLog, utcnow
from .schemas import DetectionEvent

log = logging.getLogger(__name__)


def build_provider():
    """LLM when a key is configured, offline template otherwise.

    The key is the only switch on purpose: there is no other way to end up
    calling a model that nobody configured, which matters because a failed call
    silently costs the owner the LLM's tone.
    """
    if settings.llm_api_key:
        if not settings.llm_api_base or not settings.llm_model:
            log.warning(
                "LLM_API_KEY set but LLM_API_BASE/LLM_MODEL missing; using template provider"
            )
        else:
            return LLMProvider(
                base=settings.llm_api_base,
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout,
            )
    return TemplateProvider()


provider = build_provider()


def _store(
    event: DetectionEvent,
    explanation: Explanation,
    provider_used: str,
    prompt: str | None,
) -> Alert | None:
    with SessionLocal() as session:
        if session.get(Event, event.event_id) is not None:
            # MQTT is at-least-once in practice; event_id is the natural key, so a
            # redelivery must not fan out into a second identical alert.
            log.info("event %s already stored; skipping", event.event_id)
            return None
        session.add(
            Event(
                event_id=event.event_id,
                event_type=event.event_type,
                detected_at=event.detected_at,
                severity=event.severity,
                confidence=event.confidence,
                sensor_ids=list(event.sensor_ids),
                details=dict(event.details),
            )
        )
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            event_id=event.event_id,
            created_at=utcnow(),
            severity=event.severity,
            title=explanation.title,
            explanation=explanation.explanation,
            recommended_action=explanation.recommended_action,
            status="new",
        )
        session.add(alert)
        # Same transaction as the alert, and only on the path that actually
        # created one: a replay must not inflate the fine-tuning dataset.
        session.add(
            ExplanationLog(
                event=json.loads(event.model_dump_json()),
                provider_used=provider_used,
                prompt=prompt,
                output={
                    "title": explanation.title,
                    "explanation": explanation.explanation,
                    "recommended_action": explanation.recommended_action,
                },
            )
        )
        session.commit()
        return alert


async def handle_detection_event(event: DetectionEvent) -> Alert | None:
    """Store the event and raise an alert for it. Returns None if it was a replay.

    The provider is allowed to fail: an unreachable explanation service must
    never cost the owner an alert, so anything thrown here falls back to the
    offline template.
    """
    prompt = provider.build_prompt(event) if isinstance(provider, LLMProvider) else None
    try:
        explanation = await provider.explain(event)
        provider_used = getattr(provider, "name", "template")
    except Exception:
        log.warning(
            "explanation provider failed (%s); falling back to template",
            type(provider).__name__,
            exc_info=True,
        )
        explanation = await TemplateProvider().explain(event)
        provider_used = "template"
        prompt = None
    return await asyncio.to_thread(_store, event, explanation, provider_used, prompt)