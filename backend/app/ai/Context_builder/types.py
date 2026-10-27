"""Shared dataclasses used by every part of the package.

No logic that imports database/incidents/contextbuilding lives here, so
there are no circular imports.
"""



from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas import DetectionEvent
from app.ai.Context_builder.config import SiteConfig


@dataclass
class Incident:
    """Aggregate of related events: same site, same key, no gap > gap_minutes."""
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
    explained_alert_id: str | None = None
    explained_at: datetime | None = None
    explained_lang: str | None = None
    explained_severity: int | None = None
    explained_event_count: int | None = None   # event_count when text was generated

    @property
    def duration_s(self) -> int:
        """Seconds between first_seen_at and last_seen_at."""
        raise NotImplementedError

    def is_active(self, now: datetime, gap_minutes: int) -> bool:
        """True if last_seen_at is within gap_minutes of now."""
        raise NotImplementedError

    def absorb(self, event: DetectionEvent) -> None:
        """Fold an event in: count+1, max severity/confidence, min/max
        timestamps (handles out-of-order events), union of sensor ids."""
        raise NotImplementedError

    @classmethod
    def from_event(cls, event: DetectionEvent, site_id: str, key: str) -> Incident:
        """Create a brand-new incident (count=1) from its first event."""
        raise NotImplementedError


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
        raise NotImplementedError


@dataclass
class IncidentResolution:
    """What the INCIDENTS part returns to the builder."""
    current: Incident
    created: bool                          # True = ALT PATH 1
    related: list[Incident]
    reusable: ExplainedAlert | None        # ALT PATH 3