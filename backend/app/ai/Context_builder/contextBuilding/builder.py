"""CONTEXTBUILDING part: assembles everything into a Context."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.ai.Context_builder.config import ContextBuilderConfig, DEFAULT_CONFIG
from app.ai.Context_builder.contextBuilding.context import Context
from app.ai.Context_builder.contextBuilding.site import SiteStateLoader
from app.ai.Context_builder.database import Database, get_database
from app.ai.Context_builder.Incidents import IncidentManager, incident_key
from app.ai.Context_builder.types import ExplainedAlert, Incident, SiteState
from app.schemas import DetectionEvent

log = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(self, db: Database | None = None,
                 cfg: ContextBuilderConfig | None = None) -> None:
        """Wires Database, IncidentManager and SiteStateLoader."""
        self._cfg = cfg or DEFAULT_CONFIG
        self._db = db or get_database()
        self._incidents = IncidentManager(self._db, self._cfg.incident, self._cfg.reuse)
        self._site_loader = SiteStateLoader(self._db, self._cfg.site)

    def build(self, event: DetectionEvent, site_id: str | None = None,
              lang: str | None = None) -> Context:
        """Sync core, follows the main path. doesn't raise: on failure
        returns self._degraded(...). Call only for fresh, non-replayed events,
        because it increments the incident's event_count."""
        warnings: list[str] = []

        site_id, w = self._resolve_site(event, site_id)
        warnings += w

        site, w = self._site_loader.load(site_id)
        warnings += w

        try:

            lang = lang or (site.primary_language if site.found else None) \
                or self._cfg.context.default_lang

            resolution = self._incidents.resolve(event, site_id, lang)  # steps 2-5, ALT 1/3

            return Context(
                event=event,
                site_id=site_id,
                lang=lang,
                current=resolution.current,
                related=resolution.related,
                site=site,
                explained_alert=resolution.reusable,
                is_new_incident=resolution.created,
                warnings=warnings,
                built_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            log.warning("context build failed, returning degraded context: %s",
                        exc, exc_info=True)
            return self._degraded(event, site_id, lang, reason=str(exc), warnings=warnings)[0]

    async def abuild(self, event: DetectionEvent, site_id: str | None = None,
                     lang: str | None = None) -> Context:
        """asyncio.to_thread wrapper around build()."""
        return await asyncio.to_thread(self.build, event, site_id, lang)

    def record_explanation(self, context: Context, alert: ExplainedAlert) -> None:
        """Write-back so later events reuse this text. No-op for degraded
        contexts (their incident is not in the database). Never raises."""
        if "db_degraded" in context.warnings:
            return
        try:
            self._incidents.record_explanation(
                context.current.incident_id, alert,
                context.lang, context.current.event_count)
        except Exception as exc:
            log.warning("record_explanation failed: %s", exc, exc_info=True)

    async def arecord_explanation(self, context: Context, alert: ExplainedAlert) -> None:
        await asyncio.to_thread(self.record_explanation, context, alert)

    def _resolve_site(self, event: DetectionEvent,
                      site_id: str | None) -> tuple[str, list[str]]:
        """Explicit site_id > sensors majority > default_site_id (+ warnings)."""
        if site_id:
            return site_id, []
        resolved, warnings = self._db.resolve_site_id(event.sensor_ids)
        if resolved:
            return resolved, warnings
        return self._cfg.site.default_site_id, warnings

    def _degraded(self, event: DetectionEvent, site_id: str | None,
                  lang: str | None, reason: str, warnings: list[str]) -> tuple[Context, str]:
        """Minimal Context with a temporary, unsaved incident and warning
        'db_degraded'. Touches no database, so it cannot fail the same way."""
        site_id = site_id or self._cfg.site.default_site_id
        if "db_degraded" not in warnings:
            warnings.append("db_degraded")
        return Context(
            event=event,
            site_id=site_id,
            lang=lang or self._cfg.context.default_lang,
            current=Incident.create_from_event(event, site_id, incident_key(event)),
            related=[],
            site=SiteState.unknown(site_id, self._cfg.site),
            explained_alert=None,
            is_new_incident=True,
            warnings=warnings,
            built_at=datetime.now(timezone.utc),
        ), reason