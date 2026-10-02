"""Detection event -> stored Event -> generated Alert.

Deliberately has no WebSocket broadcaster and does not import `mqtt`: the caller
owns fan-out. That keeps the dependency one-way (mqtt -> alerts) instead of
circular, and keeps this module testable with a fake provider and no broker.
"""

import asyncio
import logging
import uuid

from .ai.explanation import Explanation
from .ai.template_provider import TemplateProvider
from .database import SessionLocal
from .models import Alert, Event, utcnow
from .schemas import DetectionEvent

log = logging.getLogger(__name__)

# F-5 replaces this with "LLM if LLM_API_KEY is set, else template".
provider = TemplateProvider()


def _store(event: DetectionEvent, explanation: Explanation) -> Alert | None:
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
        session.commit()
        return alert


async def handle_detection_event(event: DetectionEvent) -> Alert | None:
    """Store the event and raise an alert for it. Returns None if it was a replay.

    The provider is allowed to fail: an unreachable explanation service must
    never cost the owner an alert, so anything thrown here falls back to the
    offline template.
    """
    try:
        explanation = await provider.explain(event)
    except Exception:
        log.exception("explanation provider failed; falling back to template")
        explanation = await TemplateProvider().explain(event)
    return await asyncio.to_thread(_store, event, explanation)