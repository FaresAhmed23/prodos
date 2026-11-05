"""Creates data/context_test.db and fills it from data/test_data.json.

Run:  python seed_db.py
Re-run it whenever the "already explained" cases expire (reuse window is
15 minutes by default), or just before a test session.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.context_builder_tester.init_db import DATA_DIR, DB_PATH, create_tables, make_engine

from app import models
from app.schemas import DetectionEvent
from app.ai.Context_builder.Incidents import incident_key

JSON_PATH = DATA_DIR / "sample.json"
META_PATH = DATA_DIR / "seed_meta.json"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def build_rows(data: dict, now: datetime) -> dict:
    """JSON -> lists of ORM objects. No database access."""
    # sites and sensors
    sites, sensors = [], []
    sensor_site: dict[str, str] = {}
    for b in data["businesses"]:
        sites.append(models.SiteProfile(
            site_id=b["site_id"],
            business_name=b["business_name"],
            business_type=b["business_type"],
            wifi_ssids=b["wifi_ssids"],
            known_access_points=b["known_access_points"],
            router_model=b["router_model"],
            primary_language=b["primary_language"],
            notes=b["notes"],
            created_at=now,
            updated_at=now,
        ))
        for s in b["sensors"]:
            sensor_site[s["sensor_id"]] = b["site_id"]
            sensors.append(models.Sensor(
                sensor_id=s["sensor_id"],
                name=s["name"],
                location=s["location"],
                channels=s["channels"],
                last_seen_at=now - timedelta(seconds=s["last_seen_seconds_ago"]),
                registered_at=now - timedelta(days=30),
                status=s["status"],
                site_id=b["site_id"],
            ))

    # events, oldest first, grouped by incident_ref
    events = []
    for e in data["events"]:
        events.append({**e, "detected_at": now - timedelta(minutes=e["minutes_ago"])})
    events.sort(key=lambda e: e["detected_at"])

    groups: dict[str, list[dict]] = {}
    for e in events:
        # validate the event against the real contract
        DetectionEvent(event_id=e["event_id"], event_type=e["event_type"],
                       detected_at=e["detected_at"], severity=e["severity"],
                       confidence=e["confidence"], sensor_ids=e["sensor_ids"],
                       details=e["details"])
        groups.setdefault(e["incident_ref"], []).append(e)

    # Incidents: aggregated by hand, independent of the code under test
    incidents: dict[str, dict] = {}
    for ref, evs in groups.items():
        first = evs[0]
        site_id = sensor_site[first["sensor_ids"][0]]
        key = incident_key(DetectionEvent(
            event_id=first["event_id"], event_type=first["event_type"],
            detected_at=first["detected_at"], severity=first["severity"],
            confidence=first["confidence"], sensor_ids=first["sensor_ids"],
            details=first["details"]))
        sensor_union: list[str] = []
        for e in evs:
            for sid in e["sensor_ids"]:
                if sid not in sensor_union:
                    sensor_union.append(sid)
        incidents[ref] = dict(
            incident_id=f"inc-{ref}",
            site_id=site_id,
            incident_key=key,
            event_type=first["event_type"],
            first_seen_at=evs[0]["detected_at"],
            last_seen_at=evs[-1]["detected_at"],
            event_count=len(evs),
            max_severity=max(e["severity"] for e in evs),
            max_confidence=max(e["confidence"] for e in evs),
            sensor_ids=sensor_union,
            explained_alert_id=None, explained_at=None, explained_lang=None,
            explained_severity=None, explained_event_count=None,
        )

    # alerts + explanation logs
    event_by_id = {e["event_id"]: e for e in events}
    alerts, logs = [], []
    for a in data["alerts"]:
        ev = event_by_id[a["event_id"]]
        created = ev["detected_at"] + timedelta(seconds=a.get("created_seconds_after_event", 1))
        ref = ev["incident_ref"]

        if a.get("explains_incident"):
            incidents[ref].update(
                explained_alert_id=a["alert_id"],
                explained_at=created,
                explained_lang=a["lang"],
                explained_severity=a["severity"],
                explained_event_count=sum(
                    1 for x in groups[ref] if x["detected_at"] <= ev["detected_at"]),
            )

        alerts.append(models.Alert(
            alert_id=a["alert_id"], event_id=a["event_id"], created_at=created,
            severity=a["severity"], title=a["title"], explanation=a["explanation"],
            recommended_action=a["recommended_action"], status=a["status"],
            lang=a["lang"],
        ))

        provider = a["provider"]  # "llm" | "template" | "reused"
        event_json = {
            "event_id": ev["event_id"], "event_type": ev["event_type"],
            "detected_at": _iso(ev["detected_at"]), "severity": ev["severity"],
            "confidence": ev["confidence"], "sensor_ids": ev["sensor_ids"],
            "details": ev["details"],
        }
        logs.append(models.ExplanationLog(
            event=event_json,
            provider_used=provider,
            prompt=(f"Detected event:\n{json.dumps(event_json)}\n\nWrite the alert."
                    if provider == "llm" else None),
            output={"title": a["title"], "explanation": a["explanation"],
                    "recommended_action": a["recommended_action"]},
            created_at=created,
            lang=a["lang"],
            site_id=incidents[ref]["site_id"],
            latency_ms=2400 if provider == "llm" else None,
            fallback_reason="no_llm_configured" if provider == "template" else None,
            attempts=1 if provider == "llm" else None,
        ))

    incident_rows = [models.Incident(**v) for v in incidents.values()]
    event_rows = [
        models.Event(
            event_id=e["event_id"], event_type=e["event_type"],
            detected_at=e["detected_at"], severity=e["severity"],
            confidence=e["confidence"], sensor_ids=e["sensor_ids"],
            details=e["details"],
            received_at=e["detected_at"] + timedelta(milliseconds=100),
            incident_id=incidents[e["incident_ref"]]["incident_id"],
        )
        for e in events
    ]
    return dict(sites=sites, sensors=sensors, incidents=incident_rows,
                events=event_rows, alerts=alerts, logs=logs)


def seed(engine, data: dict, now: datetime) -> dict:
    rows = build_rows(data, now)
    with Session(engine) as s:
        # insert in FK order, flushing between stages
        for name in ("sites", "sensors", "alerts", "incidents", "events", "logs"):
            s.add_all(rows[name])
            s.flush()
        s.commit()
    return rows


def summary(engine) -> None:
    with Session(engine) as s:
        print("\nRow counts:")
        for m in (models.SiteProfile, models.Sensor, models.Incident,
                  models.Event, models.Alert, models.ExplanationLog):
            n = s.scalar(select(func.count()).select_from(m))
            print(f"  {m.__tablename__:<18} {n}")

        print("\nIncidents:")
        for i in s.scalars(select(models.Incident).order_by(models.Incident.site_id,
                                                           models.Incident.last_seen_at)):
            print(f"  {i.incident_id:<28} site={i.site_id:<13} count={i.event_count} "
                  f"maxsev={i.max_severity} explained_by={i.explained_alert_id}")


def set_up_database() -> None:
    """Create a fresh, seeded database."""
    if not JSON_PATH.exists():
        raise SystemExit(f"Missing {JSON_PATH}. Put test_data.json in the data folder.")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc).replace(microsecond=0)
    engine = make_engine(reset=True)
    create_tables(engine)
    seed(engine, data, now)

    META_PATH.write_text(json.dumps({"seeded_at": _iso(now), "db": str(DB_PATH)}, indent=2))
    print(f"Seeded {DB_PATH} at {now.isoformat()}")
    summary(engine)


if __name__ == "__main__":
    set_up_database()