"""The Context object handed to the prompt builder."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas import DetectionEvent
from app.ai.Context_builder.types import (
    ExplainedAlert, Incident, SiteState, ensure_utc,
)


def _iso(dt: datetime | None) -> str | None:
    return ensure_utc(dt).isoformat() if dt else None


@dataclass
class Context:
    event: DetectionEvent
    site_id: str
    lang: str
    current: Incident
    related: list[Incident]
    site: SiteState
    explained_alert: ExplainedAlert | None # caller should skip the LLM call
    is_new_incident: bool
    warnings: list[str] = field(default_factory=list)
    # business_not_found, sensor_without_site, sensors_span_sites, db_degraded

    built_at: datetime | None = None

    # helpers
    def _now(self) -> datetime:
        return ensure_utc(self.built_at) if self.built_at else datetime.now(timezone.utc)

    def _same_key_related(self) -> list[Incident]:
        return [i for i in self.related if i.incident_key == self.current.incident_key]

    def _affected_sensors(self) -> list[dict]: #return the sensors involved/affected to/by an incident
        by_id = {s["id"]: s for s in self.site.sensors}
        out = []
        for sid in self.current.sensor_ids:
            s = by_id.get(sid)
            out.append({"id": sid,
                        "name": s["name"] if s else None,
                        "location": s["location"] if s else None})
        return out

    # public
    def facts(self) -> dict:
        """
        Pre-digested facts: code does the arithmetic, not the model.
        repeat_count_7d is capped by IncidentConfig.max_related, think of it as 'at least this many'.
        """

        inc = self.current
        return {
            "incident_event_count": inc.event_count,
            "ongoing_minutes": inc.duration_s // 60,
            "first_seen_utc": _iso(inc.first_seen_at),
            "last_seen_utc": _iso(inc.last_seen_at),
            "is_new_incident": self.is_new_incident,
            "severity": self.event.severity,
            "max_severity": inc.max_severity,
            "confidence": self.event.confidence,
            "repeat_count_7d": len(self._same_key_related()),
        }

    def evidence(self) -> dict:
        """
        Every value the model may cite, for the checker's grounding rule.
        Returns {"strings": [...], "numbers": [...]}.
        """

        strings: set[str] = set()
        numbers: set[float] = set()

        def add(value) -> None:
            if isinstance(value, bool) or value is None:
                return
            if isinstance(value, (int, float)):
                numbers.add(value)
            elif isinstance(value, str) and value.strip():
                strings.add(value.strip())

        for value in (self.event.details or {}).values():
            add(value)

        f = self.facts()
        for name in ("incident_event_count", "ongoing_minutes", "severity",
                     "max_severity", "repeat_count_7d"):
            add(f[name])

        add(self.site.name)
        for ssid in self.site.wifi_ssids:
            add(ssid)
        for ap in self.site.known_access_points:
            add(ap.get("bssid"))
            add(ap.get("label"))
        for s in self.site.sensors:
            add(s.get("id"))
            add(s.get("name"))
            add(s.get("location"))

        for inc in self.related:
            add(inc.event_count)
            add(inc.max_severity)

        return {"strings": sorted(strings), "numbers": sorted(numbers)}

    def to_prompt_dict(self, max_chars: int) -> dict:
        """
        JSON-convertable context for the prompt. Trims related incidents
        first, then the full sensor list, then site notes, until it fits or is as small as possible.
        NOTE: SSIDs and names are attacker-controllable; the prompt builder
        should handle that some way.
        """

        n_related = len(self.related)
        all_sensors, notes = True, True
        while True:
            d = self._prompt(n_related, all_sensors, notes)
            if len(json.dumps(d, ensure_ascii=False, default=str)) <= max_chars:
                return d
            if n_related > 0:
                n_related -= 1
            elif all_sensors:
                all_sensors = False
            elif notes:
                notes = False
            else: # NOTE: KEEP THIS IN MIND IF THE CONTEXT WINDOW IS EXCEEDED AND YOU DON'T KNOW WHY
                return d  # cannot shrink further

    # actually build context data
    def _prompt(self, n_related: int, all_sensors: bool, notes: bool) -> dict:
        now = self._now()
        ev = self.event
        related = []
        for inc in self.related[:n_related]:
            hours = int((now - ensure_utc(inc.last_seen_at)).total_seconds() // 3600)
            related.append({
                "event_type": inc.event_type,
                "same_source": inc.incident_key == self.current.incident_key,
                "event_count": inc.event_count,
                "max_severity": inc.max_severity,
                "hours_ago": max(0, hours),
            })

        site = {
            "name": self.site.name,
            "type": self.site.business_type,
            "known_found": self.site.found,
            "wifi_names": self.site.wifi_ssids,
            "known_access_points": self.site.known_access_points,
        }
        if notes and self.site.notes:
            site["notes"] = self.site.notes
        if all_sensors:
            site["sensors"] = [
                {"name": s["name"], "location": s["location"], "status": s["status"]}
                for s in self.site.sensors
            ]

        return {
            "language": self.lang,
            "event": {
                "type": ev.event_type,
                "detected_at_utc": _iso(ev.detected_at),
                "severity": ev.severity,
                "confidence": ev.confidence,
                "details": ev.details,
            },
            "incident": self.facts(),
            "affected_sensors": self._affected_sensors(),
            "related_incidents": related,
            "site": site,
            "data_warnings": list(self.warnings),
        }