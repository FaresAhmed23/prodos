# Prodos API — frontend guide

Written for the React dashboard. **`/docs` (Swagger UI) is the source of truth** for
request/response schemas — this file covers the things `/docs` can't tell you: pagination,
timestamp format, WebSocket lifecycle, and the mistakes that actually bite.

Base URL in development: `http://localhost:8000` · CORS already allows
`http://localhost:5173` and `http://localhost:3000`.

**No user accounts.** The pipeline endpoints (`/alerts`, `/events`, `/frames`, `/sensors`, the two
WebSockets) are open, because the pilot is a LAN-only café network. The owner-side `/sites` group has
one optional gate, `X-Admin-Key`, described in [Owner tools](#owner-tools-sites-checklist-score-trust).
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
| GET | `/sites` | array of `SiteOut` |
| POST | `/sites` | the created `SiteOut` |
| GET | `/sites/{site_id}` | one `SiteOut` |
| PATCH | `/sites/{site_id}` | the updated `SiteOut` |
| PATCH | `/sites/{site_id}/sensors/{sensor_id}` | the assigned `SensorOut` |
| DELETE | `/sites/{site_id}/sensors/{sensor_id}` | the unassigned `SensorOut` |
| GET | `/sites/{site_id}/checklist` | `ChecklistOut` (`answers: {}` before the first save) |
| PUT | `/sites/{site_id}/checklist` | the saved `ChecklistOut` |
| GET | `/sites/{site_id}/score` | the latest `ScoreOut` |
| GET | `/sites/{site_id}/score/history` | array of `ScoreOut`, oldest first |
| POST | `/sites/{site_id}/trust` | `TrustOut` (enrolls, or rotates) |
| DELETE | `/sites/{site_id}/trust` | **204**, no body |
| GET | `/trust/{token}` | server-rendered HTML, public and ungated |
| GET | `/trust/{token}/qr.png` | PNG QR code, public and ungated |

`POST /sensors` returns **409** if that `sensor_id` already exists — registering is not an upsert.
Everything under `/sites` is owner-side and may require `X-Admin-Key`; `/trust/*` is public. Details
in [Owner tools](#owner-tools-sites-checklist-score-trust).

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

## Owner tools: sites, checklist, score, trust

The surface behind the dashboard's Sites, Checklist, Score, Trust and Settings views.

### The admin gate

Every `/sites*` request may carry `X-Admin-Key: <key>`.

- `ADMIN_API_KEY` unset (the dev default) → the gate is open. The backend logs
  `ADMIN_API_KEY is unset: owner-side /sites endpoints are open. LAN pilot only.` at startup.
- `ADMIN_API_KEY` set → a missing or wrong header is **401** `{"detail":"invalid admin key"}`.

`/trust/{token}` and `/trust/{token}/qr.png` are **not** gated — the token in the URL is the
capability. Neither are `/alerts`, `/events`, `/frames`, `/sensors`, or the two WebSockets.

One key per installation, not per user. The dashboard keeps it in `sessionStorage` (it dies with the
tab) and sends it on every request; a 401 is surfaced as "admin key rejected".

### Sites

```json
POST /sites
{
  "site_id": "cafe-1",
  "business_name": "Cafe One",
  "business_type": "cafe",
  "wifi_ssids": ["CafeWiFi"],
  "known_access_points": ["aa:bb:cc:dd:ee:ff"],
  "router_model": "TP-Link Archer C6",
  "primary_language": "en",
  "notes": "Router is behind the counter."
}
```

- `site_id` is required, 1–64 characters, and **409** if it already exists.
- Everything else is optional at creation.
- `known_access_points` is normalized on write: `aa:bb:cc:dd:ee:ff` → `AA:BB:CC:DD:EE:FF` (the same
  form frames carry). The response holds the normalized value — display that, not what was typed.
  An invalid MAC is **422**, naming the index: `known_access_points.0: invalid MAC address: '...'`.
- `wifi_ssids` must match the SSIDs your sensors actually see, or network hygiene scores 0 and the
  snapshot carries the `ssids_not_configured` flag.

`PATCH /sites/{site_id}` is a partial update:

- An **omitted** field is untouched.
- An explicit `null` **clears** `business_name`, `business_type`, `router_model`, `notes`.
- `null` on `wifi_ssids`, `known_access_points` or `primary_language` is **ignored**, because those
  columns are NOT NULL. Send `[]` to empty a list, or a real language code.
- Unknown `site_id` → **404**.

### Sensor assignment

```
PATCH  /sites/{site_id}/sensors/{sensor_id}   → SensorOut with site_id set
DELETE /sites/{site_id}/sensors/{sensor_id}   → SensorOut with site_id null
```

Both return the full `SensorOut`. `SensorOut.site_id` is the only way to know which site owns a
sensor — without it a reload cannot render assignments. A sensor belongs to at most one site, so
assigning one that already belongs elsewhere moves it. Either endpoint 404s on an unknown site or
sensor.

### Checklist

```json
PUT /sites/cafe-1/checklist
{ "answers": { "wpa2_or_wpa3": true, "router_physically_secured": false } }
```

- `GET` returns `answers: {}` before the first save. That is a real state, not a 404: **every
  unanswered question counts as "no"** in scoring.
- `PUT` replaces the whole map. Send all keys, or the missing ones become unanswered.
- Values are `true`, `false`, or `null`.
- An unknown key is **422** with the reason and the legal keys:

```json
{ "detail": {
    "message": "unknown checklist keys",
    "unknown_keys": ["wifi_is_fast"],
    "valid_keys": ["router_admin_password_changed", "wpa2_or_wpa3", "..."]
} }
```

The eight keys: `router_admin_password_changed`, `wpa2_or_wpa3`, `guest_network_separate`,
`firmware_updated_12m`, `password_rotated_6m`, `router_physically_secured`, `no_unmanaged_extenders`,
`staff_share_password_in_person_only`. Wording lives in `backend/app/scoring/config.py` and is
mirrored once in `frontend/src/i18n.ts`; do not retype a key in a component.

### Score

- `GET /sites/{site_id}/score` → the latest snapshot. **404** `{"detail":"no snapshot yet"}` before
  the first compute.
- `GET /sites/{site_id}/score/history?limit=30` → oldest first, `limit` 1–365.
- Snapshots are written at backend startup and then **once a day**; a second compute on the same day
  replaces that day's snapshot. A site created after startup has no snapshot until the next sweep —
  that is why a working demo may show "No snapshot yet" until the backend restarts.

`components` holds already-weighted points, not ratios: `value / weight` is the meter fill.

| Component | Weight |
| --- | --- |
| `monitoring_coverage` | 30 |
| `alert_response` | 30 |
| `network_hygiene` | 15 |
| `practices_checklist` | 15 |
| `threat_exposure` | 10 |

Bands: 0–59 `needs attention`, 60–79 `fair`, 80–100 `good`. `details.flags` is a list of machine
strings (`no_sensors_assigned`, `ssids_not_configured`) — render a sentence, never the raw token.

### Trust page

```
POST   /sites/cafe-1/trust   → { "site_id": "cafe-1", "trust_token": "..." }   enroll or rotate
DELETE /sites/cafe-1/trust   → 204
```

- `POST` enrolls the site, or **rotates** if it is already enrolled. Rotating invalidates the old URL
  immediately; an old QR starts returning the 404 below.
- `DELETE` revokes: 204, token nulled, public page 404s.
- `SiteOut.trust_token` carries the token on the owner endpoint, so the QR card still renders after a
  page reload. That endpoint is admin-gated; the public page never reads it.
- The public page is `GET /trust/{token}`: server-rendered HTML, `Cache-Control: public, max-age=300`,
  and it shows **only** the business name, band, score, last checked, monitored-since date, and the
  disclaimer. Notes, router model, language, sensors and tokens never reach it.
- An unknown token and a revoked token are indistinguishable on purpose:
  **404** `{"error":"verification unavailable"}`.
- `GET /trust/{token}/qr.png` is the QR image, encoding the public URL. The card language follows the
  site's `primary_language`; the frontend only links to it.

### F-24 contract changes

All three are additive — nothing renamed, removed, or retyped, and `/alerts`, `/events`, `/frames` are
unchanged:

1. `SensorOut.site_id` added (null = unassigned).
2. `SiteOut.trust_token` added (null = not enrolled).
3. `GET /sites/{site_id}/checklist` added.

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

interface SiteOut {
  site_id: string;
  business_name: string | null;
  business_type: string | null;
  wifi_ssids: string[];
  known_access_points: string[];          // normalized: AA:BB:CC:DD:EE:FF
  router_model: string | null;
  primary_language: string;               // "en" | "ar"
  notes: string | null;
  trust_token: string | null;             // null = public page not enrolled
  created_at: string; updated_at: string;
}

interface SensorOut {
  sensor_id: string;
  site_id: string | null;                 // null = unassigned
  name: string | null; location: string | null;
  channels: number[]; last_seen_at: string | null;
  registered_at: string; status: SensorStatus;
}

interface ChecklistOut {
  site_id: string;
  answers: Record<string, boolean | null>;
  updated_at: string;
}

interface ScoreOut {
  site_id: string; computed_at: string;
  score: number;                          // 0-100
  band: string;                           // "needs attention" | "fair" | "good"
  components: Record<string, number>;     // weighted points; value / weight = meter fill
  details: Record<string, unknown>;       // details.flags is a string[]
  window_days: number;
}

interface TrustOut { site_id: string; trust_token: string; }
```

`details` is rule-specific and **you should not hard-code its keys** — for `deauth_flood` it is
`{src_mac, rate_per_sec, window_s, count}`, for `evil_twin` `{ssid, known_bssid, rogue_bssid}`.
Render `title` / `explanation` / `recommended_action` and treat `details` as debug detail. That is
the whole point of the explanation layer: the frontend never has to understand WiFi to be useful.

MAC addresses arrive normalised as `AA:BB:CC:DD:EE:FF` (upper-case, colon-separated).

---

## Known gaps (so you do not build on them)

- **No user auth.** One optional owner-side `X-Admin-Key`; no users, no sessions, single shared view.
- **No alerts/stats by severity over time** — no chart endpoint yet.
- `frames/recent` takes `seconds` and `limit` but is **not** cursor-paginated; it is bounded by the
  7-day retention sweep.
- QoS 1 is implemented end-to-end on `prodos/events` (PRO-16 closed). It does not change any
  payload shape.
