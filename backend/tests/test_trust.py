"""F-21: public trust page, QR, and owner enroll/rotate/revoke (spec §3-§6)."""

import io
from datetime import datetime, timezone

import pytest
import segno

from app.config import settings
from app.models import ScoreSnapshot, Sensor, SiteProfile
from app.routers.trust import DISCLAIMER

NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_PHRASES = (
    "guaranteed",
    "risk-free",
    "100% safe",
    "completely safe",
    "protected by prodos",
)


@pytest.fixture(autouse=True)
def _owner_endpoints_open(monkeypatch):
    """A developer's .env must not turn a CRUD test into a 401."""
    monkeypatch.setattr(settings, "admin_api_key", None)


def create_site(client, **over):
    payload = {
        "site_id": "cafe-1",
        "business_name": "Cafe One",
        "wifi_ssids": ["CafeWiFi"],
        "known_access_points": ["AA:BB:CC:DD:EE:01"],
        "notes": "SECRET-NOTE-7f3a",
        "router_model": "SECRET-ROUTER-9c1d",
        "primary_language": "zz",
    }
    payload.update(over)
    res = client.post("/sites", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def enroll(client, site_id="cafe-1"):
    res = client.post(f"/sites/{site_id}/trust")
    assert res.status_code == 200, res.text
    return res.json()["trust_token"]


def seed_snapshot(session, site_id="cafe-1", computed_at=NOW, score=82, band="good"):
    session.add(
        ScoreSnapshot(
            site_id=site_id,
            computed_at=computed_at,
            score=score,
            band=band,
            components={},
            details={},
            window_days=7,
        )
    )
    session.commit()


# --- owner side ------------------------------------------------------------


def test_enroll_returns_32_char_token_and_created_stamp(client, session):
    create_site(client)

    res = client.post("/sites/cafe-1/trust")

    assert res.status_code == 200
    assert res.json()["site_id"] == "cafe-1"
    token = res.json()["trust_token"]
    assert len(token) == 32
    row = session.get(SiteProfile, "cafe-1")
    assert row.trust_token == token
    assert row.trust_token_created_at is not None
    assert row.trust_token_rotated_at is None


def test_rotate_kills_old_token_and_stamps_rotation(client, session):
    create_site(client)
    seed_snapshot(session)
    old = enroll(client)
    assert client.get(f"/trust/{old}").status_code == 200

    new = enroll(client)

    assert new != old
    assert client.get(f"/trust/{old}").status_code == 404
    assert client.get(f"/trust/{new}").status_code == 200
    row = session.get(SiteProfile, "cafe-1")
    assert row.trust_token == new
    assert row.trust_token_rotated_at is not None


def test_revoke_nulls_token_and_kills_page(client, session):
    create_site(client)
    token = enroll(client)

    res = client.delete("/sites/cafe-1/trust")

    assert res.status_code == 204
    assert session.get(SiteProfile, "cafe-1").trust_token is None
    assert client.get(f"/trust/{token}").status_code == 404


def test_owner_trust_routes_404_for_unknown_site(client):
    assert client.post("/sites/nope/trust").status_code == 404
    assert client.delete("/sites/nope/trust").status_code == 404


def test_owner_trust_routes_ride_the_admin_gate(client, monkeypatch):
    create_site(client)
    monkeypatch.setattr(settings, "admin_api_key", "secret-key")

    assert client.post("/sites/cafe-1/trust").status_code == 401
    assert client.delete("/sites/cafe-1/trust").status_code == 401
    ok = client.post(
        "/sites/cafe-1/trust", headers={"X-Admin-Key": "secret-key"}
    )
    assert ok.status_code == 200


# --- public side -----------------------------------------------------------


def test_public_page_shows_whitelisted_fields_and_cache_header(client, session):
    create_site(client)
    seed_snapshot(session)
    token = enroll(client)

    res = client.get(f"/trust/{token}")

    assert res.status_code == 200
    text = res.text
    assert "Cafe One" in text
    assert "good" in text
    assert "82" in text
    assert "Last checked: 2026-11-20 12:00 UTC" in text
    assert "Monitored since: 2026-11-20" in text
    assert DISCLAIMER in " ".join(text.split())
    assert res.headers["cache-control"] == "public, max-age=300"


def test_page_without_snapshot_says_monitoring_not_started(client):
    create_site(client)
    token = enroll(client)

    res = client.get(f"/trust/{token}")

    assert res.status_code == 200
    text = " ".join(res.text.split())
    assert "Monitoring has not started yet." in text
    assert "Monitored since" not in text
    assert DISCLAIMER in text


def test_404_body_is_exact_for_missing_and_revoked(client):
    create_site(client)
    missing = client.get("/trust/never-issued")
    assert missing.status_code == 404
    assert missing.json() == {"error": "verification unavailable"}

    token = enroll(client)
    client.delete("/sites/cafe-1/trust")
    revoked = client.get(f"/trust/{token}")
    assert revoked.status_code == 404
    assert revoked.json() == {"error": "verification unavailable"}

    qr = client.get(f"/trust/{token}/qr.png")
    assert qr.status_code == 404
    assert qr.json() == {"error": "verification unavailable"}


def test_forbidden_phrases_absent_from_normalized_html(client, session):
    create_site(client)
    seed_snapshot(session)
    token = enroll(client)

    text = " ".join(client.get(f"/trust/{token}").text.split()).lower()

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text


def test_owner_fields_and_sensor_ids_never_reach_the_page(client, session):
    create_site(client)
    session.add(
        Sensor(sensor_id="SENSOR-SECRET-4e2b", name="Hidden", site_id="cafe-1")
    )
    seed_snapshot(session)
    token = enroll(client)

    text = client.get(f"/trust/{token}").text.lower()

    assert "secret-note-7f3a" not in text
    assert "secret-router-9c1d" not in text
    assert "sensor-secret-4e2b" not in text
    assert "zz" not in text


def test_qr_png_matches_the_public_url_bytes(client):
    create_site(client)
    token = enroll(client)
    expected_url = f"http://testserver/trust/{token}"
    buffer = io.BytesIO()
    segno.make(expected_url, error="m").save(buffer, kind="png", scale=6, border=2)

    res = client.get(f"/trust/{token}/qr.png")

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.headers["cache-control"] == "public, max-age=300"
    assert res.content == buffer.getvalue()


def test_business_name_is_html_escaped(client):
    create_site(client, business_name="<script>alert(1)</script> & Cafe")
    token = enroll(client)

    text = client.get(f"/trust/{token}").text

    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&amp; Cafe" in text
