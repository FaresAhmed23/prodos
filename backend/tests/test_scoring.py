"""F-20: ShieldScore computation, daily upsert, and score endpoints (spec §3, §9)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Alert, ChecklistAnswer, Event, Frame, ScoreSnapshot, Sensor, SiteProfile
from app.scoring import engine
from app.scoring.config import CHECKLIST_QUESTIONS

# Noon UTC: the day-replace tests can add hours without crossing midnight.
NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _owner_endpoints_open(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", None)


def seed_site(session, site_id="cafe-1", ssids=("CafeWiFi",), aps=("AA:BB:CC:DD:EE:01",)):
    site = SiteProfile(
        site_id=site_id,
        business_name="Cafe One",
        wifi_ssids=list(ssids),
        known_access_points=list(aps),
    )
    session.add(site)
    session.commit()
    return site


def seed_sensor(session, sensor_id="sensor-1", site_id="cafe-1"):
    session.add(Sensor(sensor_id=sensor_id, site_id=site_id))
    session.commit()


def seed_frame(
    session,
    received_at,
    sensor_id="sensor-1",
    frame_type="beacon",
    bssid=None,
    ssid=None,
):
    session.add(
        Frame(
            sensor_id=sensor_id,
            received_at=received_at,
            batch_seq=1,
            channel=6,
            frame_type=frame_type,
            src_mac="AA:BB:CC:DD:EE:99",
            dst_mac="FF:FF:FF:FF:FF:FF",
            bssid=bssid,
            ssid=ssid,
            rssi=-50,
        )
    )


def seed_event(session, event_id, sensor_ids, severity=10, detected_at=NOW):
    session.add(
        Event(
            event_id=event_id,
            event_type="deauth_flood",
            detected_at=detected_at,
            severity=severity,
            confidence=0.9,
            sensor_ids=list(sensor_ids),
            details={},
        )
    )


def seed_alert(session, alert_id, event_id, status="new", created_at=NOW):
    session.add(
        Alert(
            alert_id=alert_id,
            event_id=event_id,
            created_at=created_at,
            severity=5,
            title="seeded",
            explanation="seeded",
            recommended_action="seeded",
            status=status,
        )
    )


def seed_golden(session):
    """Half of every ratio, so each component has one unambiguous expected value."""
    site = seed_site(session)
    seed_sensor(session)

    # 504 of the 1008 buckets covered -> coverage 0.5.
    for k in range(504):
        seed_frame(session, NOW - timedelta(seconds=k * 600))

    # Two BSSIDs on the site SSID, one known -> hygiene 0.5. Both reuse
    # covered buckets so coverage stays exactly 504.
    seed_frame(session, NOW, bssid="AA:BB:CC:DD:EE:01", ssid="CafeWiFi")
    seed_frame(session, NOW - timedelta(seconds=600), bssid="AA:BB:CC:DD:EE:02", ssid="CafeWiFi")

    # One acknowledged, one open -> response 0.5. Severity 10 + 10 -> 20/40.
    seed_event(session, "event-1", ["sensor-1"], severity=10)
    seed_event(session, "event-2", ["sensor-1"], severity=10)
    seed_alert(session, "alert-1", "event-1", status="acknowledged")
    seed_alert(session, "alert-2", "event-2", status="new")

    # Belongs to no site: must not count anywhere, but must be visible.
    seed_event(session, "event-ghost", ["ghost-sensor"], severity=9)

    four_yes = list(CHECKLIST_QUESTIONS)[:4]
    session.add(
        ChecklistAnswer(site_id="cafe-1", answers={key: True for key in four_yes})
    )
    session.commit()
    return site


# --- golden computation ----------------------------------------------------


def test_golden_components_and_total(session):
    site = seed_golden(session)

    result = engine.compute_site_score(session, site, NOW)

    assert result["components"] == {
        "monitoring_coverage": 15.0,
        "alert_response": 15.0,
        "network_hygiene": 7.5,
        "practices_checklist": 7.5,
        "threat_exposure": 5.0,
    }
    assert result["score"] == 50
    assert result["band"] == "needs attention"
    assert result["window_days"] == 7
    assert result["details"]["flags"] == []
    assert result["details"]["monitoring_coverage"]["buckets_covered"] == 504
    assert result["details"]["siteless_events_excluded"] == 1


def test_unacked_over_72h_caps_alert_response(session):
    seed_site(session)
    seed_sensor(session)
    old = NOW - timedelta(hours=100)
    for i in range(3):
        seed_event(session, f"event-{i}", ["sensor-1"], severity=1, detected_at=old)
        seed_alert(session, f"alert-{i}", f"event-{i}", status="acknowledged", created_at=old)
    seed_event(session, "event-stale", ["sensor-1"], severity=1, detected_at=old)
    seed_alert(session, "alert-stale", "event-stale", status="new", created_at=old)
    session.commit()

    result = engine.compute_site_score(session, session.get(SiteProfile, "cafe-1"), NOW)

    # 3/4 would be 22.5 points; the >72h cap pulls it to 0.5 -> 15.
    assert result["details"]["alert_response"]["ratio"] == 0.5
    assert result["details"]["alert_response"]["unacked_over_72h"] is True
    assert result["components"]["alert_response"] == 15.0


def test_no_alerts_scores_full_response(session):
    seed_site(session)
    seed_sensor(session)
    session.commit()

    result = engine.compute_site_score(session, session.get(SiteProfile, "cafe-1"), NOW)

    assert result["components"]["alert_response"] == 30.0


def test_siteless_events_excluded_and_counted(session):
    seed_site(session)
    seed_sensor(session)
    seed_event(session, "event-ghost", ["ghost-sensor"], severity=10)
    session.commit()

    result = engine.compute_site_score(session, session.get(SiteProfile, "cafe-1"), NOW)

    assert result["details"]["siteless_events_excluded"] == 1
    assert result["components"]["threat_exposure"] == 10.0


def test_threat_exposure_is_capped_at_zero_points(session):
    seed_site(session)
    seed_sensor(session)
    for i in range(4):
        seed_event(session, f"event-{i}", ["sensor-1"], severity=10)
    session.commit()

    result = engine.compute_site_score(session, session.get(SiteProfile, "cafe-1"), NOW)

    # 40 severity / 40 cap = 1.0 -> floor, never negative.
    assert result["components"]["threat_exposure"] == 0.0


def test_flags_when_unmonitored_and_unconfigured(session):
    site = seed_site(session, ssids=(), aps=())

    result = engine.compute_site_score(session, site, NOW)

    assert result["components"]["monitoring_coverage"] == 0.0
    assert result["components"]["network_hygiene"] == 0.0
    assert result["details"]["flags"] == ["no_sensors_assigned", "ssids_not_configured"]


def test_known_access_points_normalized_on_write_and_compared(client, session):
    res = client.post(
        "/sites",
        json={
            "site_id": "cafe-1",
            "wifi_ssids": ["CafeWiFi"],
            "known_access_points": ["aa-bb-cc-dd-ee-01"],
        },
    )
    assert res.status_code == 201
    assert res.json()["known_access_points"] == ["AA:BB:CC:DD:EE:01"]
    bad = client.post(
        "/sites", json={"site_id": "bad", "known_access_points": ["nope"]}
    )
    assert bad.status_code == 422
    patched = client.patch(
        "/sites/cafe-1", json={"known_access_points": ["aa:bb:cc:dd:ee:01"]}
    )
    assert patched.json()["known_access_points"] == ["AA:BB:CC:DD:EE:01"]

    # A row written before F-20 can still hold lowercase; the engine must
    # compare normalized copies, not raw strings. Separate SSID, because
    # hygiene counts every BSSID on the site's SSID regardless of sensor.
    seed_site(session, "legacy-1", ssids=("LegacyWiFi",), aps=("aa:bb:cc:dd:ee:02",))
    seed_sensor(session, "sensor-1", "cafe-1")
    seed_sensor(session, "sensor-2", "legacy-1")
    seed_frame(
        session, NOW, sensor_id="sensor-1", bssid="AA:BB:CC:DD:EE:01", ssid="CafeWiFi"
    )
    seed_frame(
        session, NOW, sensor_id="sensor-2", bssid="AA:BB:CC:DD:EE:02", ssid="LegacyWiFi"
    )
    session.commit()

    cafe = engine.compute_site_score(session, session.get(SiteProfile, "cafe-1"), NOW)
    legacy = engine.compute_site_score(session, session.get(SiteProfile, "legacy-1"), NOW)
    assert cafe["components"]["network_hygiene"] == 15.0
    assert legacy["components"]["network_hygiene"] == 15.0


def test_hygiene_sensor_scoped_when_sites_share_ssid(session):
    seed_site(session, "cafe-1", ssids=("CafeWiFi",), aps=("AA:BB:CC:DD:EE:01",))
    seed_site(session, "cafe-2", ssids=("CafeWiFi",), aps=("AA:BB:CC:DD:EE:02",))
    seed_sensor(session, "sensor-1", "cafe-1")
    seed_sensor(session, "sensor-2", "cafe-2")
    seed_frame(
        session, NOW, sensor_id="sensor-1", bssid="AA:BB:CC:DD:EE:01", ssid="CafeWiFi"
    )
    seed_frame(
        session, NOW, sensor_id="sensor-2", bssid="AA:BB:CC:DD:EE:02", ssid="CafeWiFi"
    )
    # Not assigned to any site: its frames count toward nobody.
    seed_frame(
        session, NOW, sensor_id="sensor-roam", bssid="AA:BB:CC:DD:EE:03", ssid="CafeWiFi"
    )
    session.commit()

    for site_id in ("cafe-1", "cafe-2"):
        result = engine.compute_site_score(
            session, session.get(SiteProfile, site_id), NOW
        )
        assert result["components"]["network_hygiene"] == 15.0
        assert result["details"]["network_hygiene"]["bssids"] == 1


@pytest.mark.parametrize(
    "score,band",
    [
        (0, "needs attention"),
        (59, "needs attention"),
        (60, "fair"),
        (79, "fair"),
        (80, "good"),
        (100, "good"),
    ],
)
def test_band_boundaries(score, band):
    assert engine.band_for(score) == band


# --- snapshot upsert -------------------------------------------------------


def test_second_run_same_day_replaces_snapshot(session):
    site = seed_golden(session)
    engine.upsert_snapshot(session, site, NOW)

    session.get(ChecklistAnswer, "cafe-1").answers = {
        key: True for key in CHECKLIST_QUESTIONS
    }
    session.commit()
    engine.upsert_snapshot(session, site, NOW + timedelta(hours=1))

    rows = list(session.execute(select(ScoreSnapshot)).scalars())
    assert len(rows) == 1
    assert rows[0].details["practices_checklist"]["yes"] == 8
    assert rows[0].score == 58  # 50 + 7.5 checklist, rounded


def test_next_day_adds_a_second_snapshot(session):
    site = seed_site(session)
    engine.upsert_snapshot(session, site, NOW)
    engine.upsert_snapshot(session, site, NOW + timedelta(days=1))

    assert len(list(session.execute(select(ScoreSnapshot)).scalars())) == 2


def test_snapshot_job_writes_one_row_per_site(session, session_factory, monkeypatch):
    seed_site(session, "cafe-1")
    seed_site(session, "cafe-2", ssids=(), aps=())
    monkeypatch.setattr(engine, "SessionLocal", session_factory)

    assert engine.snapshot_all_sites(NOW) == 2
    engine.snapshot_all_sites(NOW + timedelta(hours=2))

    session.expire_all()
    rows = list(session.execute(select(ScoreSnapshot)).scalars())
    assert len(rows) == 2
    assert {row.site_id for row in rows} == {"cafe-1", "cafe-2"}


# --- /score and /score/history --------------------------------------------


def test_score_endpoint_returns_latest_snapshot(client, session):
    site = seed_golden(session)
    engine.upsert_snapshot(session, site, NOW)

    res = client.get("/sites/cafe-1/score")

    assert res.status_code == 200
    body = res.json()
    assert body["score"] == 50
    assert body["band"] == "needs attention"
    assert body["components"]["monitoring_coverage"] == 15.0
    assert body["details"]["siteless_events_excluded"] == 1
    assert body["window_days"] == 7


def test_score_404_when_no_snapshot_yet(client, session):
    seed_site(session)

    res = client.get("/sites/cafe-1/score")

    assert res.status_code == 404
    assert res.json()["detail"] == "no snapshot yet"


def test_score_404_when_site_unknown(client):
    assert client.get("/sites/nope/score").status_code == 404
    assert client.get("/sites/nope/score/history").status_code == 404


def test_score_history_oldest_to_newest_and_limited(client, session):
    site = seed_site(session)
    for days in (2, 0, 1):
        engine.upsert_snapshot(session, site, NOW - timedelta(days=days))

    res = client.get("/sites/cafe-1/score/history", params={"limit": 2})

    assert res.status_code == 200
    stamps = [row["computed_at"] for row in res.json()]
    assert len(stamps) == 2
    assert stamps == sorted(stamps)
    assert stamps[-1].startswith("2026-11-20")


def test_score_history_default_limit_returns_all_recent(client, session):
    site = seed_site(session)
    for days in range(3):
        engine.upsert_snapshot(session, site, NOW - timedelta(days=days))

    assert len(client.get("/sites/cafe-1/score/history").json()) == 3


def test_score_endpoints_ride_the_admin_gate(client, session, monkeypatch):
    site = seed_site(session)
    engine.upsert_snapshot(session, site, NOW)
    monkeypatch.setattr(settings, "admin_api_key", "secret")

    assert client.get("/sites/cafe-1/score").status_code == 401
    assert client.get("/sites/cafe-1/score/history").status_code == 401
    headers = {"X-Admin-Key": "secret"}
    assert client.get("/sites/cafe-1/score", headers=headers).status_code == 200
    assert client.get("/sites/cafe-1/score/history", headers=headers).status_code == 200
