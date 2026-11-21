"""ShieldScore computation and the daily snapshot job (spec §3, §4, §7).

Pure Python on top of the stored frames/events/alerts: no new dependency, no
dialect-specific SQL. The daily job is idempotent by construction — a second
run on the same UTC day replaces that day's row instead of adding one.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Alert, ChecklistAnswer, Event, Frame, ScoreSnapshot, Sensor, SiteProfile, utcnow
from ..schemas import normalize_mac
from .config import (
    BANDS,
    BUCKET_SECONDS,
    BUCKETS_PER_WINDOW,
    CHECKLIST_QUESTIONS,
    EXPOSURE_CAP_WEIGHT,
    UNACKED_CAP_AFTER_HOURS,
    UNACKED_CAP_RATIO,
    WEIGHTS,
    WINDOW_DAYS,
)

log = logging.getLogger(__name__)

SCORE_INTERVAL_S = 24 * 3600


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on the way out; stored values are always UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _site_sensor_map(session: Session) -> dict[str, str | None]:
    return dict(session.execute(select(Sensor.sensor_id, Sensor.site_id)).all())


def _owners(sensor_ids, sensor_site: dict[str, str | None]) -> set[str]:
    return {sensor_site.get(sid) for sid in (sensor_ids or [])} - {None}


def _mac_key(value: str) -> str:
    """Frame BSSIDs are normalized at ingest; stored APs may predate F-20."""
    try:
        return normalize_mac(value)
    except ValueError:
        return value.strip().upper()


def band_for(score: int) -> str:
    for low, high, name in BANDS:
        if low <= score <= high:
            return name
    return BANDS[0][2]


def compute_site_score(
    session: Session, site: SiteProfile, now: datetime | None = None
) -> dict:
    """Return the snapshot fields for one site. Nothing is written here."""
    now = _as_utc(now or utcnow())
    cutoff = now - timedelta(days=WINDOW_DAYS)
    sensor_site = _site_sensor_map(session)
    site_sensors = [sid for sid, owner in sensor_site.items() if owner == site.site_id]
    flags: list[str] = []

    # Monitoring coverage: distinct 10-minute buckets holding any frame from a
    # sensor assigned to this site. Streamed so memory stays at 1008 bucket ids.
    if not site_sensors:
        coverage = 0.0
        monitoring = {
            "ratio": 0.0,
            "buckets_covered": 0,
            "buckets_total": BUCKETS_PER_WINDOW,
            "sensors": 0,
        }
        flags.append("no_sensors_assigned")
    else:
        buckets: set[int] = set()
        stmt = (
            select(Frame.received_at)
            .where(Frame.sensor_id.in_(site_sensors), Frame.received_at >= cutoff)
            .execution_options(yield_per=10_000)
        )
        for received_at in session.execute(stmt).scalars():
            buckets.add(int(_as_utc(received_at).timestamp()) // BUCKET_SECONDS)
        coverage = min(1.0, len(buckets) / BUCKETS_PER_WINDOW)
        monitoring = {
            "ratio": coverage,
            "buckets_covered": len(buckets),
            "buckets_total": BUCKETS_PER_WINDOW,
            "sensors": len(site_sensors),
        }

    # Alert response: an alert is attributed through its event's sensors.
    # shortcut: Alert stores only a status, no acknowledgement timestamp, so
    # any status other than "new" counts as acknowledged and the 24h bound in
    # §3 cannot be enforced; add acknowledged_at before trusting the ratio.
    stale_before = now - timedelta(hours=UNACKED_CAP_AFTER_HOURS)
    rows = session.execute(
        select(Alert.created_at, Alert.status, Event.sensor_ids)
        .select_from(Alert)
        .join(Event, Event.event_id == Alert.event_id)
        .where(Alert.created_at >= cutoff)
    ).all()
    alerts_total = alerts_acked = 0
    unacked_over_72h = False
    for created_at, status, sensor_ids in rows:
        if site.site_id not in _owners(sensor_ids, sensor_site):
            continue
        alerts_total += 1
        if status != "new":
            alerts_acked += 1
        elif _as_utc(created_at) < stale_before:
            unacked_over_72h = True
    response_ratio = 1.0 if alerts_total == 0 else alerts_acked / alerts_total
    if unacked_over_72h:
        response_ratio = min(response_ratio, UNACKED_CAP_RATIO)

    # Network hygiene: distinct BSSIDs heard by the site's own sensors,
    # broadcasting one of the site's SSIDs, and how many are declared known.
    # Sensorless site -> empty universe. Unassigned sensors count toward
    # nobody. total==0 -> 0 and ssids_not_configured.
    ssids = list(site.wifi_ssids or [])
    if ssids and site_sensors:
        bssids = set(
            session.execute(
                select(Frame.bssid).where(
                    Frame.frame_type == "beacon",
                    Frame.received_at >= cutoff,
                    Frame.sensor_id.in_(site_sensors),
                    Frame.bssid.is_not(None),
                    Frame.ssid.in_(ssids),
                )
            ).scalars()
        )
    else:
        bssids = set()
    allowed = len({_mac_key(bssid) for bssid in bssids} & {
        _mac_key(mac) for mac in (site.known_access_points or [])
    })
    if not bssids:
        hygiene_ratio = 0.0
        flags.append("ssids_not_configured")
    else:
        hygiene_ratio = allowed / len(bssids)

    # Practices checklist: yes / 8; unanswered and null both count as no.
    answer_row = session.get(ChecklistAnswer, site.site_id)
    answers = (answer_row.answers if answer_row else None) or {}
    yes = sum(1 for key in CHECKLIST_QUESTIONS if answers.get(key) is True)
    checklist_ratio = yes / len(CHECKLIST_QUESTIONS)

    # Threat exposure, and the siteless count, from the same event scan.
    severity_weighted = 0
    events_attributed = 0
    siteless_events = 0
    for sensor_ids, severity in session.execute(
        select(Event.sensor_ids, Event.severity).where(Event.detected_at >= cutoff)
    ):
        owners = _owners(sensor_ids, sensor_site)
        if not owners:
            siteless_events += 1
        elif site.site_id in owners:
            severity_weighted += severity
            events_attributed += 1
    exposure_ratio = 1.0 - min(1.0, severity_weighted / EXPOSURE_CAP_WEIGHT)

    ratios = {
        "monitoring_coverage": coverage,
        "alert_response": response_ratio,
        "network_hygiene": hygiene_ratio,
        "practices_checklist": checklist_ratio,
        "threat_exposure": exposure_ratio,
    }
    components = {
        name: round(WEIGHTS[name] * ratio, 2) for name, ratio in ratios.items()
    }
    score = max(0, min(100, round(sum(components.values()))))

    details = {
        "monitoring_coverage": monitoring,
        "alert_response": {
            "ratio": response_ratio,
            "alerts": alerts_total,
            "acknowledged": alerts_acked,
            "unacked_over_72h": unacked_over_72h,
        },
        "network_hygiene": {
            "ratio": hygiene_ratio,
            "bssids": len(bssids),
            "allowed": allowed,
            "configured_ssids": ssids,
        },
        "practices_checklist": {
            "ratio": checklist_ratio,
            "yes": yes,
            "total": len(CHECKLIST_QUESTIONS),
        },
        "threat_exposure": {
            "ratio": exposure_ratio,
            "events": events_attributed,
            "severity_weighted": severity_weighted,
            "cap": EXPOSURE_CAP_WEIGHT,
        },
        "flags": flags,
        "siteless_events_excluded": siteless_events,
    }
    return {
        "score": score,
        "band": band_for(score),
        "components": components,
        "details": details,
        "window_days": WINDOW_DAYS,
    }


def upsert_snapshot(
    session: Session, site: SiteProfile, now: datetime | None = None
) -> ScoreSnapshot:
    """Compute and write the site's snapshot, replacing the same UTC day's row."""
    now = _as_utc(now or utcnow())
    result = compute_site_score(session, site, now)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    row = session.execute(
        select(ScoreSnapshot).where(
            ScoreSnapshot.site_id == site.site_id,
            ScoreSnapshot.computed_at >= day_start,
            ScoreSnapshot.computed_at < day_end,
        )
    ).scalars().first()
    if row is None:
        row = ScoreSnapshot(site_id=site.site_id)
        session.add(row)
    row.computed_at = now
    row.score = result["score"]
    row.band = result["band"]
    row.components = result["components"]
    row.details = result["details"]
    row.window_days = result["window_days"]
    session.commit()
    return row


def snapshot_all_sites(now: datetime | None = None) -> int:
    """One snapshot per site. Returns how many were written."""
    now = _as_utc(now or utcnow())
    scored = 0
    with SessionLocal() as session:
        sites = list(session.execute(select(SiteProfile)).scalars())
        for site in sites:
            try:
                upsert_snapshot(session, site, now)
                scored += 1
            except Exception:
                # One bad site must not cost every other site its daily score.
                session.rollback()
                log.exception("shieldscore failed for site %s", site.site_id)
    return scored


async def score_loop() -> None:
    while True:
        try:
            scored = await asyncio.to_thread(snapshot_all_sites)
            log.info("shieldscore: wrote %s site snapshots", scored)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("shieldscore sweep failed")
        await asyncio.sleep(SCORE_INTERVAL_S)
