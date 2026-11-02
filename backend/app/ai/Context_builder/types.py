"""Shared dataclasses used by every part of the package.

No logic that imports database/incidents/contextbuilding lives here, so
there are no circular imports.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas import DetectionEvent
from app.ai.Context_builder.config import SiteConfig


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Naive -> aware UTC (SQLite returns naive); aware -> converted to UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class Incident:
    """Aggregation of related events: same site, same key, no gap > gap_minutes."""
    incident_id: str
    site_id: str
    incident_key: str
    event_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    event_count: int
    max_severity: int
    max_confidence: float
    sensor_ids: list[str] = field(default_factory=list)
    explained_alert_id: str | None = None # points to the last explanation of the last event linked to an Incident
    explained_at: datetime | None = None
    explained_lang: str | None = None
    explained_severity: int | None = None
    explained_event_count: int | None = None   # event_count when text was generated

    @property
    def duration_s(self) -> int:
        """Seconds between first_seen_at and last_seen_at (never negative)."""
        delta = ensure_utc(self.last_seen_at) - ensure_utc(self.first_seen_at)
        return max(0, int(delta.total_seconds()))

    def is_active(self, now: datetime, gap_minutes: int) -> bool:
        """True if last_seen_at is within gap_minutes of now."""
        silence = ensure_utc(now) - ensure_utc(self.last_seen_at)
        return silence.total_seconds() <= gap_minutes * 60

    def absorb(self, event: DetectionEvent) -> None:
        """Fold an event in: count+1, max severity/confidence, min/max
        timestamps (handles out-of-order events), union of sensor ids."""
        when = ensure_utc(event.detected_at)
        self.event_count += 1
        self.max_severity = max(self.max_severity, event.severity)
        self.max_confidence = max(self.max_confidence, event.confidence)
        self.first_seen_at = min(ensure_utc(self.first_seen_at), when)
        self.last_seen_at = max(ensure_utc(self.last_seen_at), when)
        for sensor_id in event.sensor_ids:
            if sensor_id not in self.sensor_ids:
                self.sensor_ids.append(sensor_id)

    @classmethod
    def create_from_event(cls, event: DetectionEvent, site_id: str, key: str) -> Incident:
        """Create a brand-new incident (count=1) from its first event."""
        when = ensure_utc(event.detected_at)
        return cls(
            incident_id=str(uuid.uuid4()),
            site_id=site_id,
            incident_key=key,
            event_type=event.event_type,
            first_seen_at=when,
            last_seen_at=when,
            event_count=1,
            max_severity=event.severity,
            max_confidence=event.confidence,
            sensor_ids=list(dict.fromkeys(event.sensor_ids)),  # dedupe, keep order
        )


@dataclass
class ExplainedAlert:
    """A previously generated explanation that can be reused."""
    alert_id: str
    title: str
    explanation: str
    recommended_action: str
    severity: int
    lang: str
    created_at: datetime
    status: str


@dataclass
class SiteState:
    """Snapshot of the business/site the event belongs to."""
    site_id: str
    found: bool
    name: str | None = None
    business_type: str | None = None
    wifi_ssids: list[str] = field(default_factory=list)
    known_access_points: list[dict] = field(default_factory=list)
    router_model: str | None = None
    primary_language: str = "en"
    notes: str | None = None
    sensors: list[dict] = field(default_factory=list)  # id, name, location, status, last_seen_at

    @classmethod
    def unknown(cls, site_id: str, cfg: SiteConfig) -> SiteState:
        """ALT PATH 2.2: generic filler when the site is not in the database."""
        return cls(
            site_id=site_id,
            found=False,
            name=cfg.unknown_site_name,
            notes=cfg.unknown_filler,
        )


@dataclass
class IncidentResolution:
    """What the INCIDENTS part returns to the builder."""
    current: Incident
    created: bool                          # True = ALT PATH 1
    related: list[Incident]
    reusable: ExplainedAlert | None        # ALT PATH 3