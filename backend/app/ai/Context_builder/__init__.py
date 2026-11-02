"""Prodos Context Builder public local api."""

from __future__ import annotations

import threading

from app.schemas import DetectionEvent
from app.ai.Context_builder.config import ContextBuilderConfig, DEFAULT_CONFIG
from app.ai.Context_builder.contextBuilding import Context, ContextBuilder
from app.ai.Context_builder.types import ExplainedAlert, Incident, SiteState

_builder: ContextBuilder | None = None
_lock = threading.Lock()


def get_builder() -> ContextBuilder:
    """Lazy singleton, so importing the package never touches the database."""
    global _builder
    if _builder is None:
        with _lock:
            if _builder is None:
                _builder = ContextBuilder()
    return _builder


def reset_builder(builder: ContextBuilder | None = None) -> None:
    """for testing: inject a builder wired to an in-memory database."""
    global _builder
    with _lock:
        _builder = builder


async def build_context(event: DetectionEvent, site_id: str | None = None,
                        lang: str | None = None) -> Context:
    """Main high-level call. Check context.explained_alert to decide whether
    to skip the LLM. Call only for non-replayed events."""
    return await get_builder().abuild(event, site_id, lang)


async def record_explanation(context: Context, alert: ExplainedAlert) -> None:
    """Call after the alert is created so later events can reuse its text."""
    await get_builder().arecord_explanation(context, alert)


__all__ = [
    "build_context", "record_explanation", "get_builder", "reset_builder",
    "Context", "ContextBuilder", "Incident", "ExplainedAlert", "SiteState",
    "ContextBuilderConfig", "DEFAULT_CONFIG",
]