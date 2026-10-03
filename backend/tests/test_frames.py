"""GET /frames/recent filtering -- the query the dashboard polls."""

from datetime import timedelta

from app.models import Frame, utcnow


def seed(session, **over):
    row = Frame(
        sensor_id=over.pop("sensor_id", "sensor-1"),
        received_at=over.pop("received_at", utcnow()),
        batch_seq=1,
        channel=6,
        frame_type=over.pop("frame_type", "beacon"),
        src_mac="AA:BB:CC:DD:EE:FF",
        dst_mac="11:22:33:44:55:66",
        bssid=None,
        ssid=None,
        rssi=-50,
        seq_num=None,
        **over,
    )
    session.add(row)
    return row


def test_empty_when_no_frames(client):
    assert client.get("/frames/recent").json() == []


def test_returns_stored_frames(client, session):
    seed(session)
    session.commit()
    body = client.get("/frames/recent").json()
    assert len(body) == 1
    assert body[0]["frame_type"] == "beacon"


def test_newest_first(client, session):
    now = utcnow()
    seed(session, received_at=now - timedelta(seconds=30), frame_type="beacon")
    seed(session, received_at=now, frame_type="deauth")
    session.commit()
    types = [f["frame_type"] for f in client.get("/frames/recent").json()]
    assert types == ["deauth", "beacon"]


def test_seconds_window_excludes_older_frames(client, session):
    now = utcnow()
    seed(session, received_at=now - timedelta(seconds=10))
    seed(session, received_at=now - timedelta(seconds=600))
    session.commit()
    body = client.get("/frames/recent", params={"seconds": 60}).json()
    assert len(body) == 1, "the 10-minute-old frame must be outside a 60s window"


def test_widening_the_window_brings_old_frames_back(client, session):
    now = utcnow()
    seed(session, received_at=now - timedelta(seconds=600))
    session.commit()
    assert client.get("/frames/recent", params={"seconds": 60}).json() == []
    assert len(client.get("/frames/recent", params={"seconds": 3600}).json()) == 1


def test_limit_is_respected(client, session):
    now = utcnow()
    for i in range(10):
        seed(session, received_at=now - timedelta(seconds=i))
    session.commit()
    assert len(client.get("/frames/recent", params={"limit": 3}).json()) == 3


def test_frame_type_filter(client, session):
    seed(session, frame_type="beacon")
    seed(session, frame_type="deauth")
    seed(session, frame_type="deauth")
    session.commit()
    body = client.get("/frames/recent", params={"frame_type": "deauth"}).json()
    assert len(body) == 2
    assert {f["frame_type"] for f in body} == {"deauth"}


def test_frame_type_filter_combines_with_window(client, session):
    now = utcnow()
    seed(session, frame_type="deauth", received_at=now - timedelta(seconds=5))
    seed(session, frame_type="deauth", received_at=now - timedelta(seconds=900))
    session.commit()
    body = client.get("/frames/recent", params={"frame_type": "deauth", "seconds": 60}).json()
    assert len(body) == 1


def test_unknown_frame_type_filter_is_422(client):
    assert client.get("/frames/recent", params={"frame_type": "wormhole"}).status_code == 422


def test_limit_bounds_enforced(client):
    assert client.get("/frames/recent", params={"limit": 0}).status_code == 422
    assert client.get("/frames/recent", params={"limit": 501}).status_code == 422


def test_payload_shape_matches_schema(client, session):
    seed(session)
    session.commit()
    assert set(client.get("/frames/recent").json()[0]) == {
        "id", "sensor_id", "received_at", "batch_seq", "channel", "frame_type",
        "src_mac", "dst_mac", "bssid", "ssid", "rssi", "seq_num",
    }
