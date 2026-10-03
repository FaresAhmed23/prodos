# Prodos API — frontend guide

Written for the React dashboard. **`/docs` (Swagger UI) is the source of truth** for
request/response schemas — this file covers the things `/docs` can't tell you: pagination,
timestamp format, WebSocket lifecycle, and the mistakes that actually bite.

Base URL in development: `http://localhost:8000` · CORS already allows
`http://localhost:5173` and `http://localhost:3000`.

**No authentication yet.** Every endpoint is open, because the pilot is a LAN-only café network.
Do not build anything that assumes a session exists. Auth lands with TLS before the pilot.

---

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/health` | `{"status":"ok"}` |
| GET | `/frames/recent` | array of `FrameOut`, newest first |
| WS | `/ws/frames` | one `FrameOut` per frame, live |
| GET | `/events` | array of `EventOut`, newest first |
| GET | `/alerts` | array of `Alert`, newest first |
| GET | `/alerts/stats` | summary counts for dashboard cards |
| PATCH | `/alerts/{alert_id}` | the updated `Alert` |
| GET | `/sensors` | array of `SensorOut` |
| POST | `/sensors` | the created `SensorOut` |
| GET | `/sensors/{sensor_id}` | one `SensorOut` |
| PATCH | `/sensors/{sensor_id}` | the updated `SensorOut` |

`POST /sensors` returns **409** if that `sensor_id` already exists — registering is not an upsert.

---

## Pagination

`/alerts` and `/events` are **cursor-paginated, newest first**. The cursor is simply the
`alert_id` / `event_id` of the **last item you already have**, so you never have to parse
anything — just keep the id from the final row of the previous page.

Both endpoints return a **bare JSON array**. The pagination state comes back in response
headers, not in an envelope:

```js
async function fetchAlerts({ status, cursor, limit = 50 } = {}) {
  const params = new URLSearchParams({ limit });
  if (status) params.set("status", status);
  if (cursor) params.set("cursor", cursor);

  const res = await fetch(`/alerts?${params}`);
  if (!res.ok) throw new Error(await res.text());

  return {
    items: await res.json(),
    hasMore: res.headers.get("X-Has-More") === "true",
    nextCursor: res.headers.get("X-Next-Cursor"), // null when there is no next page
  };
}
```

First page:

```js
const page1 = await fetchAlerts();
// page1.nextCursor === null  means that is the whole feed right now
```

Next page:

```js
const page2 = await fetchAlerts({ cursor: page1.nextCursor });
```

Then `page2.nextCursor` and so on. Stop when `X-Next-Cursor` is absent — **do not** loop until a
page comes back empty, because the last page can be full.

An unknown `cursor` returns **400**. That happens if the row it pointed at has been deleted.

### Why not `?offset=`

Because `/alerts` grows while you are reading it. Offset paging shifts the window under a polling
client, so it silently repeats and skips rows — a new alert landing at the top while you are on
page 2 pushes everything down by one. Keyset paging anchors on a row you have already seen, so
inserts cannot disturb the window. The anchor row was verified to stay stable across an insert
mid-page.

### Gotcha: filtering plus paging

`?status=new` combined with `?cursor=` is supported, but an alert whose status changes from `new`
to `acknowledged` while you are paging **leaves the filter** and you will not see it again on
later pages. That is correct behaviour, not a bug. For a "new alerts" view, prefer polling page 1
and reacting to `/ws/alerts`.

---

## `/alerts/stats`

For summary cards. Counts only alerts created in the last `window_hours` (default **24**, max 2160).

```json
{
  "window_hours": 24,
  "total": 25,
  "by_status": { "new": 9, "acknowledged": 8, "resolved": 8 },
  "by_severity": { "low": 10, "medium": 10, "high": 5 },
  "newest_alert_at": "2026-10-03T09:33:13.491198Z"
}
```

- `by_severity` bands are `low` = 1–3, `medium` = 4–7, `high` = 8–10. These are the **same bands
  the explanation text uses**, so a card labelled "high" and an alert that reads urgent are one
  judgement, not two.
- `by_severity` always contains all three keys, so a card can render `0` without special-casing a
  missing key. `by_status` only contains statuses that actually occurred.
- `newest_alert_at` is `null` when nothing happened in the window — handle that before rendering a
  "last updated" line.

---

## Timestamps

**Every datetime is timezone-aware UTC and serialised with a `Z` suffix** — for example
`2026-10-03T09:33:13.491198Z`. Parse with `new Date(...)` and it just works.

Two fields worth knowing about:

- `Frame.received_at` is stamped **by the backend**, not the sensor. Sensor clocks are untrusted
  (`uptime_ms` only), so this is the field to sort and filter frames on.
- `Event.detected_at` comes from the detection engine; `Event.received_at` is when the backend got
  it. The gap between them is your end-to-end latency.

> SQLite note, so you are not surprised locally: if you run the backend against SQLite, datetimes
> come back **without** a timezone. That is a SQLite limitation, not a contract change — against
> PostgreSQL (production, and what the pilot runs) they are always `Z`-suffixed.

---

## WebSockets

Two streams, same lifecycle rules:

- `ws://localhost:8000/ws/frames` — one `FrameOut` per frame. **High volume** (~10/sec per AP per
  sensor). Throttle in the UI; do not render every frame.
- `ws://localhost:8000/ws/alerts` — one `Alert` per new alert. Low volume. This is your live feed.

Payloads are **byte-identical in shape to the REST equivalents**, so one component can render either
source.

```js
const ws = new WebSocket(`ws://${location.host}/ws/alerts`);
ws.onmessage = (e) => setAlerts((prev) => [JSON.parse(e.data), ...prev]);
ws.onclose = () => setTimeout(connect, 2000); // the backend restarts; reconnect with backoff
```

Notes that will save you time:

- **Reconnect is mandatory.** The backend restarts during development and every connection drops.
  Add backoff, or your dashboard silently stops updating and looks fine.
- Slow WebSocket clients are **dropped, not queued** — you will never build a backlog. Reconnect
  and re-fetch page 1 to catch up.
- On reconnect, **re-fetch `/alerts`**. Anything that happened while you were disconnected was not
  buffered for you.
- Duplicate alerts are impossible: MQTT is at-least-once, but `event_id` is deduplicated server
  side, so the same event never produces two alerts.

---

## Alert lifecycle

```
new ──► acknowledged ──► resolved
 └────────────────────► resolved
```

`PATCH /alerts/{alert_id}` accepts **only** `acknowledged` or `resolved`:

```json
{ "status": "acknowledged" }
```

- `{"status": "new"}` → **422**. There is no way to un-resolve an alert.
- Unknown `alert_id` → **404**.
- There is **no `DELETE`** and no alert deletion endpoint. Alerts are an audit trail.

`status` on `Event` does not exist — events are immutable detections, alerts are the thing a human
acts on. Track acknowledgement on the alert.

---

## Types cheat-sheet

```ts
type AlertStatus = "new" | "acknowledged" | "resolved";
type EventType   = "evil_twin" | "rogue_ap" | "deauth_flood" | "anomaly";
type FrameType   = "beacon" | "probe_req" | "probe_resp" | "deauth" | "disassoc" | "other";
type SensorStatus = "online" | "offline" | "retired";

interface Alert {
  alert_id: string; event_id: string; created_at: string;
  severity: number;            // 1-10
  title: string;               // plain language, safe to show as a headline
  explanation: string;         // <=3 sentences, jargon-free, from the AI layer
  recommended_action: string;  // one concrete action
  status: AlertStatus;
}

interface EventOut {
  event_id: string; event_type: EventType; detected_at: string;
  severity: number; confidence: number;   // 0.0-1.0
  sensor_ids: string[]; details: Record<string, unknown>; received_at: string;
}
```

`details` is rule-specific and **you should not hard-code its keys** — for `deauth_flood` it is
`{src_mac, rate_per_sec, window_s, count}`, for `evil_twin` `{ssid, known_bssid, rogue_bssid}`.
Render `title` / `explanation` / `recommended_action` and treat `details` as debug detail. That is
the whole point of the explanation layer: the frontend never has to understand WiFi to be useful.

MAC addresses arrive normalised as `AA:BB:CC:DD:EE:FF` (upper-case, colon-separated).

---

## Known gaps (so you do not build on them)

- **No auth**, no per-user anything. Single shared view.
- **No alerts/stats by severity over time** — no chart endpoint yet.
- `frames/recent` takes `seconds` and `limit` but is **not** cursor-paginated; it is bounded by the
  7-day retention sweep.
- QoS on `prodos/events` is still being finalised (PRO-16). It does not change any payload shape.
