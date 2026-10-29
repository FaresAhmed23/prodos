"""All Read/write operations needed to be done on the Inciedents table"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app import models
from app.ai.Context_builder.types import Incident


class IncidentQueries:
    """Mixin for Database. All methods are sync and open their own session.
    Row -> dataclass conversion happens inside the `with` block, so no ORM
    object ever leaves a session."""

    # conversion helpers
    def _to_incident(self, row) -> Incident:
        """Convert a row to an incident object."""
        return Incident(
            incident_id=row.incident_id,
            site_id=row.site_id,
            incident_key=row.incident_key,
            event_type=row.event_type,
            first_seen_at=self._utc(row.first_seen_at),
            last_seen_at=self._utc(row.last_seen_at),
            event_count=row.event_count,
            max_severity=row.max_severity,
            max_confidence=row.max_confidence,
            sensor_ids=list(row.sensor_ids or []),
            explained_alert_id=row.explained_alert_id,
            explained_at=self._utc(row.explained_at),
            explained_lang=row.explained_lang,
            explained_severity=row.explained_severity,
            explained_event_count=row.explained_event_count,
        )

    @staticmethod
    def _incident_fields(inc: Incident) -> dict:
        return {
            "site_id": inc.site_id,
            "incident_key": inc.incident_key,
            "event_type": inc.event_type,
            "first_seen_at": inc.first_seen_at,
            "last_seen_at": inc.last_seen_at,
            "event_count": inc.event_count,
            "max_severity": inc.max_severity,
            "max_confidence": inc.max_confidence,
            "sensor_ids": list(inc.sensor_ids),
        }

    # queries
    def find_latest_by_key(self, site_id: str, key: str) -> Incident | None:
        """Get the most recent incident (using last_seen_at) for this site and key."""
        with self.session() as s:
            row = s.scalars(
                select(models.Incident)
                .where(models.Incident.site_id == site_id,
                       models.Incident.incident_key == key)
                .order_by(models.Incident.last_seen_at.desc())
                .limit(1)
            ).first()
            return self._to_incident(row) if row else None

    def get_incident(self, incident_id: str) -> Incident | None:
        with self.session() as s:
            row = s.get(models.Incident, incident_id)
            return self._to_incident(row) if row else None

    def insert_incident(self, inc: Incident) -> None:
        with self.session() as s:
            s.add(models.Incident(incident_id=inc.incident_id, **self._incident_fields(inc)))

    def update_incident(self, inc: Incident) -> None:
        """Persist count, severity, confidence, timestamps and sensor ids.
        Does not affect the explained_* columns (set_explained handles those)."""
        with self.session() as s:
            row = s.get(models.Incident, inc.incident_id)
            if row is None:
                raise LookupError(f"incident {inc.incident_id} not found")
            for name, value in self._incident_fields(inc).items():
                setattr(row, name, value)

    def list_by_key(self, site_id: str, key: str, since: datetime,
                    exclude_id: str | None, limit: int) -> list[Incident]:
        """Other incidents with the same key at this site since 'since'."""
        since = self._utc(since)
        stmt = (
            select(models.Incident)
            .where(models.Incident.site_id == site_id,
                   models.Incident.incident_key == key,
                   models.Incident.last_seen_at >= since)
            .order_by(models.Incident.last_seen_at.desc())
            .limit(limit)
        )
        if exclude_id:
            stmt = stmt.where(models.Incident.incident_id != exclude_id)
        with self.session() as s:
            return [self._to_incident(r) for r in s.scalars(stmt)]

    def list_high_severity(self, site_id: str, since: datetime, min_severity: int,
                           exclude_id: str | None, limit: int) -> list[Incident]:
        """Incidents at this site with max_severity >= min_severity since 'since'."""
        since = self._utc(since)
        stmt = (
            select(models.Incident)
            .where(models.Incident.site_id == site_id,
                   models.Incident.max_severity >= min_severity,
                   models.Incident.last_seen_at >= since)
            .order_by(models.Incident.max_severity.desc(),
                      models.Incident.last_seen_at.desc())
            .limit(limit)
        )
        if exclude_id:
            stmt = stmt.where(models.Incident.incident_id != exclude_id)
        with self.session() as s:
            return [self._to_incident(r) for r in s.scalars(stmt)]

    def set_explained(self, incident_id: str, alert_id: str, lang: str,
                      severity: int, event_count: int, at: datetime) -> None:
        """Record which alert explains the incident (The write-back for ALT PATH 3)."""
        with self.session() as s:
            row = s.get(models.Incident, incident_id)
            if row is None:
                raise LookupError(f"incident {incident_id} not found")
            row.explained_alert_id = alert_id
            row.explained_lang = lang
            row.explained_severity = severity
            row.explained_event_count = event_count
            row.explained_at = self._utc(at)