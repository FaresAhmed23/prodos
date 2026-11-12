"""Extracts relatable and important event details from an event into json format"""

from __future__ import annotations

import json
from app.schemas import DetectionEvent

def _convertEvent(event: DetectionEvent, compact: bool) -> dict[str, object]:
    """Compact = True ignores event details to make the eventDict more compact."""
    eventDict = event.model_dump()

    if compact:
        del eventDict["details"]

    return eventDict

def extractEventInfo(event: DetectionEvent, compact: bool | None) -> str:
    """returns a raedy json object."""

    if compact is None:
        compact = False

    eventJson = json.dumps(_convertEvent(event, compact), ensure_ascii=False, indent=2, default=str)
    return eventJson