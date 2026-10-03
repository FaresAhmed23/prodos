"""Alert status transitions, cursor pagination and /alerts/stats."""

import uuid
from datetime import timedelta

import pytest

from app.models import Alert, utcnow


def seed(session, *, status="new", severity=5, minutes_ago=0):
    row = Alert(
        alert_id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        created_at=utcnow() - timedelta(minutes=minutes_ago),
        severity=severity,
        title="seeded",
        explanation="seeded",
        recommended_action="seeded",
        status=status,
    )
    session.add(row)
    return row


# --- PATCH transitions -----------------------------------------------------


def test_patch_to_acknowledged(client, session):
    alert = seed(session)
    session.commit()
    res = client.patch(f"/alerts/{alert.alert_id}", json={"status": "acknowledged"})
    assert res.status_code == 200
    assert res.json()["status"] == "acknowledged"


def test_patch_to_resolved(client, session):
    alert = seed(session, status="acknowledged")
    session.commit()
    res = client.patch(f"/alerts/{alert.alert_id}", json={"status": "resolved"})
    assert res.json()["status"] == "resolved"


@pytest.mark.parametrize("start", ["new", "acknowledged"])
def test_both_live_statuses_are_reachable(client, session, start):
    alert = seed(session, status=start)
    session.commit()
    assert client.patch(f"/alerts/{alert.alert_id}", json={"status": "resolved"}).status_code == 200


def test_cannot_transition_back_to_new(client, session):
    alert = seed(session, status="acknowledged")
    session.commit()
    assert client.patch(f"/alerts/{alert.alert_id}", json={"status": "new"}).status_code == 422


def test_nonsense_status_rejected(client, session):
    alert = seed(session)
    session.commit()
    assert client.patch(f"/alerts/{alert.alert_id}", json={"status": "banana"}).status_code == 422


def test_unknown_alert_is_404(client):
    assert client.patch(f"/alerts/{uuid.uuid4()}", json={"status": "resolved"}).status_code == 404


def test_patch_persists(client, session):
    alert = seed(session)
    session.commit()
    client.patch(f"/alerts/{alert.alert_id}", json={"status": "resolved"})
    session.expire_all()
    assert session.get(Alert, alert.alert_id).status == "resolved"


# --- listing + cursor pagination ------------------------------------------


def test_list_is_a_bare_array(client, session):
    seed(session)
    session.commit()
    body = client.get("/alerts").json()
    assert isinstance(body, list) and len(body) == 1


def test_status_filter(client, session):
    seed(session, status="new")
    seed(session, status="resolved")
    session.commit()
    body = client.get("/alerts", params={"status": "resolved"}).json()
    assert len(body) == 1 and body[0]["status"] == "resolved"


def test_paging_covers_the_feed_without_duplicates(client, session):
    for i in range(25):
        seed(session, minutes_ago=i * 3)
    session.commit()

    seen, cursor = [], None
    for _ in range(20):
        params = {"limit": 7}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/alerts", params=params)
        seen += [a["alert_id"] for a in res.json()]
        cursor = res.headers.get("X-Next-Cursor")
        if not cursor:
            break

    assert len(seen) == 25
    assert len(set(seen)) == 25, "cursor paging repeated a row"


def test_cursor_order_matches_unpaged_order(client, session):
    for i in range(12):
        seed(session, minutes_ago=i * 5)
    session.commit()

    seen, cursor = [], None
    while True:
        params = {"limit": 5}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/alerts", params=params)
        seen += [a["alert_id"] for a in res.json()]
        cursor = res.headers.get("X-Next-Cursor")
        if not cursor:
            break

    assert seen == [a["alert_id"] for a in client.get("/alerts", params={"limit": 500}).json()]


def test_new_alert_mid_paging_does_not_shift_the_window(client, session):
    for i in range(10):
        seed(session, minutes_ago=i * 3)
    session.commit()

    first = client.get("/alerts", params={"limit": 4})
    page1 = [a["alert_id"] for a in first.json()]

    seed(session, minutes_ago=-1)  # newer than everything: lands at the top
    session.commit()

    rest, cursor = [], first.headers["X-Next-Cursor"]
    while cursor:
        res = client.get("/alerts", params={"limit": 4, "cursor": cursor})
        rest += [a["alert_id"] for a in res.json()]
        cursor = res.headers.get("X-Next-Cursor")

    assert not set(page1) & set(rest), "offset-style paging would have repeated a row here"


def test_has_more_header_reflects_remaining_rows(client, session):
    for i in range(3):
        seed(session, minutes_ago=i)
    session.commit()
    res = client.get("/alerts", params={"limit": 2})
    assert res.headers["X-Has-More"] == "true"
    assert res.headers.get("X-Next-Cursor")


def test_last_page_has_no_more(client, session):
    seed(session)
    session.commit()
    res = client.get("/alerts", params={"limit": 50})
    assert res.headers["X-Has-More"] == "false"
    assert "X-Next-Cursor" not in res.headers


def test_unknown_cursor_is_400(client):
    assert client.get("/alerts", params={"cursor": str(uuid.uuid4())}).status_code == 400


def test_paging_combines_with_status_filter(client, session):
    for i in range(6):
        seed(session, status="new" if i % 2 else "resolved", minutes_ago=i)
    session.commit()
    seen, cursor = [], None
    while True:
        params = {"limit": 2, "status": "new"}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/alerts", params=params)
        seen += [a["alert_id"] for a in res.json()]
        cursor = res.headers.get("X-Next-Cursor")
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 3


# --- /alerts/stats ---------------------------------------------------------


def test_stats_counts_by_status(client, session):
    for status in ("new", "new", "acknowledged", "resolved"):
        seed(session, status=status)
    session.commit()
    body = client.get("/alerts/stats").json()
    assert body["total"] == 4
    assert body["by_status"] == {"new": 2, "acknowledged": 1, "resolved": 1}


def test_stats_severity_bands(client, session):
    for severity in (1, 3, 4, 7, 8, 10):
        seed(session, severity=severity)
    session.commit()
    bands = client.get("/alerts/stats").json()["by_severity"]
    assert bands == {"low": 2, "medium": 2, "high": 2}, "3/4 and 7/8 must fall in different bands"


def test_stats_always_reports_all_three_bands(client, session):
    seed(session, severity=9)
    session.commit()
    assert set(client.get("/alerts/stats").json()["by_severity"]) == {"low", "medium", "high"}


def test_stats_window_excludes_old_alerts(client, session):
    seed(session, minutes_ago=1)
    seed(session, minutes_ago=60 * 24 + 60)  # a day and an hour ago
    session.commit()
    assert client.get("/alerts/stats").json()["total"] == 1


def test_stats_window_is_configurable(client, session):
    seed(session, minutes_ago=30)
    seed(session, minutes_ago=90)
    session.commit()
    assert client.get("/alerts/stats", params={"window_hours": 1}).json()["total"] == 1
    assert client.get("/alerts/stats", params={"window_hours": 24}).json()["total"] == 2


def test_stats_empty_window(client):
    body = client.get("/alerts/stats").json()
    assert body["total"] == 0
    assert body["newest_alert_at"] is None
    assert body["by_severity"] == {"low": 0, "medium": 0, "high": 0}


def test_stats_statuses_sum_to_total(client, session):
    for i in range(7):
        seed(session, status=("new", "acknowledged", "resolved")[i % 3])
    session.commit()
    body = client.get("/alerts/stats").json()
    assert sum(body["by_status"].values()) == body["total"]


def test_stats_route_not_shadowed(client, session):
    seed(session)
    session.commit()
    assert client.get("/alerts/stats").json()["total"] == 1
