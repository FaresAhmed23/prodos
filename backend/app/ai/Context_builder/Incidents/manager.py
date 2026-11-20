"""INCIDENTS part: link/create incidents, find related ones, handle reuse."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ai.Context_builder.config import IncidentConfig, ReuseConfig
from app.ai.Context_builder.database import Database
from app.ai.Context_builder.Incidents.keys import incident_key
from app.ai.Context_builder.Incidents.related import RelatedSelector
from app.ai.Context_builder.types import (
    ExplainedAlert, Incident, IncidentResolution, ensure_utc,
)
from app.schemas import DetectionEvent


def severity_band(severity: int) -> int:
    """0 = calm (1-3), 1 = serious (4-7), 2 = urgent (8-10).
    Same values as the template provider and /alerts/stats."""
    if severity <= 3:
        return 0
    if severity <= 7:
        return 1
    return 2


class IncidentManager:
    def __init__(self, db: Database, cfg: IncidentConfig, reuse_cfg: ReuseConfig,
                 selector: RelatedSelector | None = None) -> None:
        self._db = db
        self._cfg = cfg
        self._reuse = reuse_cfg
        self._selector = selector or RelatedSelector(db, cfg)

    def resolve(self, event: DetectionEvent, site_id: str, lang: str) -> IncidentResolution:
        """Main entry point: link or create the incident, select related incidents, check reuse."""
        current, created = self._link_or_create(event, site_id)
        related = self._selector.select(current)
        reusable = None if created else self.find_reusable(current, event, lang)
        return IncidentResolution(current=current, created=created,
                                  related=related, reusable=reusable)

    def _link_or_create(self, event: DetectionEvent, site_id: str) -> tuple[Incident, bool]:
        """Find latest incident by (site, key). Within gap: absorb + update.
        Otherwise create + insert (ALT 1). Returns (incident, created)."""
        key = incident_key(event)
        latest = self._db.find_latest_by_key(site_id, key)
        if latest is not None and self._within_gap(latest, event):
            latest.absorb(event)
            self._db.update_incident(latest)
            return latest, False
        incident = Incident.create_from_event(event, site_id, key)
        self._db.insert_incident(incident)
        return incident, True

    def _within_gap(self, incident: Incident, event: DetectionEvent) -> bool:
        """True if the event falls inside the incident's span, or within
        gap_minutes before its start / after its end (out-of-order safe)."""
        when = ensure_utc(event.detected_at)
        first = ensure_utc(incident.first_seen_at)
        last = ensure_utc(incident.last_seen_at)
        gap = timedelta(minutes=self._cfg.gap_minutes)
        if when > last:
            return when - last <= gap
        if when < first:
            return first - when <= gap
        return True

    def find_reusable(self, incident: Incident, event: DetectionEvent, lang: str,
                      now: datetime | None = None) -> ExplainedAlert | None:
        """Return the stored explanation only if ALL hold:
        - incident has explained_alert_id
        - explained_at within reuse_minutes
        - same lang (if require_same_lang)
        - event severity band <= explained_severity
        - event_count - explained_event_count < regenerate_every_n_events
        `now` is usable for tests."""

        r = self._reuse
        if not incident.explained_alert_id or incident.explained_at is None:
            return None

        now = ensure_utc(now) if now else datetime.now(timezone.utc)
        age = now - ensure_utc(incident.explained_at)
        if age > timedelta(minutes=r.reuse_minutes):
            return None

        if r.require_same_lang and incident.explained_lang != lang:
            return None

        if (r.block_on_severity_escalation and incident.explained_severity is not None
                and severity_band(event.severity) > severity_band(incident.explained_severity)):
            return None

        if incident.explained_event_count is not None:
            grown = incident.event_count - incident.explained_event_count
            if grown >= r.regenerate_every_n_events:
                return None

        return self._db.get_explained_alert(incident.explained_alert_id,
                                            incident.explained_lang)

    def record_explanation(self, incident_id: str, alert: ExplainedAlert,
                           lang: str, event_count: int) -> None:
        """Write-back so later events can reuse this text."""
        self._db.set_explained(incident_id, alert.alert_id, lang,
                               alert.severity, event_count, alert.created_at)