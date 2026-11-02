"""Rules deciding which other incidents are relevant to the current one."""
from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from app.ai.Context_builder.config import IncidentConfig
from app.ai.Context_builder.database import Database
from app.ai.Context_builder.types import Incident


class RelatedRule(Protocol):
    def find(self, db: Database, current: Incident, cfg: IncidentConfig) -> list[Incident]:
        """Return candidate related incidents (same site, excluding current)."""
        ...


def _since(current: Incident, cfg: IncidentConfig):
    """see how recent an event in within a certain period of time"""
    return current.last_seen_at - timedelta(days=cfg.related_window_days)


class SameKeyHistoryRule:
    """Earlier incidents with the same key within related_window_days."""
    def find(self, db: Database, current: Incident, cfg: IncidentConfig) -> list[Incident]:
        return db.list_by_key(current.site_id, current.incident_key,
                              _since(current, cfg), current.incident_id,
                              cfg.max_candidates_scanned)


class HighSeverityRule:
    """Recent incidents of any type with max_severity >= threshold."""
    def find(self, db: Database, current: Incident, cfg: IncidentConfig) -> list[Incident]:
        return db.list_high_severity(current.site_id, _since(current, cfg),
                                     cfg.high_severity_threshold,
                                     current.incident_id,
                                     cfg.max_candidates_scanned)


class RelatedSelector:
    """Runs all rules, dedupes by incident_id, ranks, and caps the list."""

    def __init__(self, db: Database, cfg: IncidentConfig,
                 rules: list[RelatedRule] | None = None) -> None:
        self._db = db
        self._cfg = cfg
        self._rules = rules or [SameKeyHistoryRule(), HighSeverityRule()]

    def select(self, current: Incident) -> list[Incident]:
        """Rank by max_severity desc then last_seen_at desc; cap at max_related."""
        merged: dict[str, Incident] = {}
        for rule in self._rules:
            for inc in rule.find(self._db, current, self._cfg):
                if inc.incident_id != current.incident_id:
                    merged.setdefault(inc.incident_id, inc)
        ranked = sorted(merged.values(),
                        key=lambda i: (-i.max_severity, -i.last_seen_at.timestamp()))
        return ranked[: self._cfg.max_related]