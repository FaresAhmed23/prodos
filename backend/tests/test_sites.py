"""F-19 foundation: sites CRUD, sensor assignment, checklist, admin gate."""

import pytest

from app.admin import warn_if_admin_key_unset
from app.config import settings
from app.models import ChecklistAnswer, Sensor
from app.scoring.config import CHECKLIST_QUESTIONS


@pytest.fixture(autouse=True)
def _owner_endpoints_open(monkeypatch):
    """A developer's .env must not turn a CRUD test into a 401."""
    monkeypatch.setattr(settings, "admin_api_key", None)


def site_payload(**over):
    payload = {
        "site_id": "cafe-1",
        "business_name": "Cafe One",
        "wifi_ssids": ["CafeWiFi"],
        "known_access_points": ["AA:BB:CC:DD:EE:FF"],
    }
    payload.update(over)
    return payload


# --- sites CRUD ------------------------------------------------------------


def test_create_site_roundtrip(client):
    res = client.post("/sites", json=site_payload())
    assert res.status_code == 201
    assert res.json()["site_id"] == "cafe-1"
    assert client.get("/sites/cafe-1").json()["business_name"] == "Cafe One"
    assert [s["site_id"] for s in client.get("/sites").json()] == ["cafe-1"]


def test_duplicate_site_is_409(client):
    client.post("/sites", json=site_payload())
    assert client.post("/sites", json=site_payload()).status_code == 409


def test_unknown_site_is_404(client):
    assert client.get("/sites/nope").status_code == 404
    assert client.patch("/sites/nope", json={"notes": "x"}).status_code == 404


def test_patch_cannot_null_a_required_field(client):
    client.post("/sites", json=site_payload())
    res = client.patch("/sites/cafe-1", json={"primary_language": None})
    assert res.json()["primary_language"] == "en"


def test_patch_null_clears_optional_field(client):
    client.post(
        "/sites",
        json=site_payload(notes="back door router", router_model="TP-Link X20"),
    )
    res = client.patch(
        "/sites/cafe-1", json={"notes": None, "router_model": None}
    )
    assert res.status_code == 200
    assert res.json()["notes"] is None
    assert res.json()["router_model"] is None


def test_patch_keeps_untouched_fields(client):
    client.post("/sites", json=site_payload())
    res = client.patch("/sites/cafe-1", json={"notes": "back door router"})
    assert res.status_code == 200
    body = res.json()
    assert body["notes"] == "back door router"
    assert body["business_name"] == "Cafe One"
    assert body["wifi_ssids"] == ["CafeWiFi"]


# --- sensor assignment -----------------------------------------------------


def seed_sensor(session, sensor_id="sensor-1"):
    row = Sensor(sensor_id=sensor_id)
    session.add(row)
    session.commit()
    return row


def test_assign_sets_site_id(client, session):
    client.post("/sites", json=site_payload())
    seed_sensor(session)
    res = client.patch("/sites/cafe-1/sensors/sensor-1")
    assert res.status_code == 200
    session.expire_all()
    assert session.get(Sensor, "sensor-1").site_id == "cafe-1"


def test_unassign_sets_null(client, session):
    client.post("/sites", json=site_payload())
    sensor = seed_sensor(session)
    sensor.site_id = "cafe-1"
    session.commit()

    res = client.delete("/sites/cafe-1/sensors/sensor-1")
    assert res.status_code == 200
    session.expire_all()
    assert session.get(Sensor, "sensor-1").site_id is None


@pytest.mark.parametrize(
    "method,path",
    [
        ("patch", "/sites/cafe-1/sensors/missing"),
        ("patch", "/sites/missing/sensors/sensor-1"),
        ("delete", "/sites/missing/sensors/sensor-1"),
    ],
)
def test_assignment_unknown_ids_are_404(client, session, method, path):
    client.post("/sites", json=site_payload())
    seed_sensor(session)
    assert getattr(client, method)(path).status_code == 404


# --- checklist -------------------------------------------------------------


def test_checklist_put_persists(client, session):
    client.post("/sites", json=site_payload())
    res = client.put(
        "/sites/cafe-1/checklist",
        json={"answers": {"wpa2_or_wpa3": True, "guest_network_separate": None}},
    )
    assert res.status_code == 200
    assert res.json()["answers"] == {
        "wpa2_or_wpa3": True,
        "guest_network_separate": None,
    }

    session.expire_all()
    row = session.get(ChecklistAnswer, "cafe-1")
    assert row.answers == {"wpa2_or_wpa3": True, "guest_network_separate": None}


def test_checklist_put_replaces_answers(client, session):
    client.post("/sites", json=site_payload())
    client.put("/sites/cafe-1/checklist", json={"answers": {"wpa2_or_wpa3": True}})
    client.put("/sites/cafe-1/checklist", json={"answers": {"wpa2_or_wpa3": False}})

    session.expire_all()
    assert session.query(ChecklistAnswer).count() == 1
    assert session.get(ChecklistAnswer, "cafe-1").answers == {"wpa2_or_wpa3": False}


def test_checklist_unknown_key_is_422_with_valid_keys(client):
    client.post("/sites", json=site_payload())
    res = client.put("/sites/cafe-1/checklist", json={"answers": {"banana": True}})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["unknown_keys"] == ["banana"]
    assert set(detail["valid_keys"]) == set(CHECKLIST_QUESTIONS)


def test_checklist_unknown_site_is_404(client):
    res = client.put("/sites/nope/checklist", json={"answers": {}})
    assert res.status_code == 404


# --- admin key -------------------------------------------------------------


def test_owner_endpoints_open_when_admin_key_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", None)
    assert client.get("/sites").status_code == 200


def test_admin_key_is_enforced_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "secret")
    assert client.get("/sites").status_code == 401
    assert client.get("/sites", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/sites", headers={"X-Admin-Key": "secret"}).status_code == 200


def test_startup_warns_when_admin_key_unset(monkeypatch, caplog):
    monkeypatch.setattr(settings, "admin_api_key", None)
    with caplog.at_level("WARNING", logger="app.admin"):
        warn_if_admin_key_unset()
    assert "ADMIN_API_KEY is unset" in caplog.text


def test_startup_is_quiet_when_admin_key_set(monkeypatch, caplog):
    monkeypatch.setattr(settings, "admin_api_key", "secret")
    with caplog.at_level("WARNING", logger="app.admin"):
        warn_if_admin_key_unset()
    assert "ADMIN_API_KEY" not in caplog.text
