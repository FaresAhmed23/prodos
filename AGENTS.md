# PRODOS — Project Specification & Agent Context

Document version: 1.0 (Oct 2026) · Maintainer: Fares Ahmad · Status: M0 in progress

You are an AI coding agent working on the Prodos repository. Read this document fully before writing any code. It contains the complete project context, architecture, data contracts, current repository state, conventions, and the assigned task backlog.

## 1. Project Overview

Prodos is an AI-powered wireless security assistant for small businesses (cafés, clinics, small hotels, retail stores) that offer customer WiFi but have no security expertise or budget for enterprise Wireless Intrusion Detection Systems (WIDS).

Pipeline: ESP32 sensors sniff 802.11 frames in monitor mode → streamed over MQTT → backend stores frames → detection engine analyzes for attacks (evil twin APs, deauth floods) → detected events get severity scores → AI explanation layer converts technical events into plain-language alerts with recommended actions → pushed to a real-time React dashboard.

Primary attack detections:

- **Evil twin / rogue AP** — same SSID broadcast from a different BSSID; inconsistent signal characteristics
- **Deauthentication flood** — abnormal rate of deauth/disassoc frames from one source

Measurable success criteria (binding, from the approved proposal):

- ≥90% detection rate for simulated evil-twin attacks
- ≥85% deauth detection accuracy with <10% false-positive rate over 48h
- ≥90% of non-technical users understand and act on AI explanations
- Alert visible on dashboard within 5 seconds of backend detection
- 2-week continuous real-world pilot without critical failure

Strategy: thin vertical slice first (sensor → backend → dashboard), then iterate in depth. Ship weekly demos every Thursday.

## 2. Team & Code Ownership (CRITICAL — do not violate)

| Member | Owns | Repo directories |
| --- | --- | --- |
| Fares Ahmad (you work for him) | Backend, API, data contracts, AI layer integration | `backend/`, `scripts/`, `infra/` |
| Mohamed Ahmed Abdelmoneim (Team Leader) | AI quality, prompts, evaluation, fine-tuning dataset reviews | `backend/app/ai/` |
| Arsany Medhat | Frontend | `frontend/` — DO NOT MODIFY |
| Omar Ahmed Fathy + Mohamed Zaki Ibrahim | Detection engine | `detection/` — DO NOT MODIFY (you may create the initial skeleton stub, see task F-3) |
| Ammar Tarek | ESP32 firmware | `firmware/` — DO NOT MODIFY |

Agent rule: unless a task explicitly says otherwise, only create/modify files under `backend/`, `scripts/`, `infra/`, and root-level config. `detection/`, `firmware/`, `frontend/` belong to other humans.

## 3. Architecture

```text
ESP32 sensors (x3, promiscuous mode)
│  publish FrameBatch (1 msg/sec)
▼
MQTT broker (Mosquitto, port 1883)
│  topic: prodos/sensors/{sensor_id}/frames
├────────────────────► Backend (FastAPI, port 8000)
│   • validates + stores frames (PostgreSQL)
│   • WebSocket live stream /ws/frames
│   • REST API /frames/recent
│
└────────────────────► Detection Engine (separate Python service)
   topic: prodos/sensors/+/frames (subscribe)
   • rule-based detection
   • publishes DetectionEvent to topic: prodos/events
   │
   ▼
Backend ◄───────────────────────┘ (subscribes prodos/events)
   • stores event
   • generates Alert (template + LLM explanation layer)
   • WebSocket push /ws/alerts ──► React dashboard (Vite, port 5173)
```

Key design decisions (already made — do not revisit):

- MQTT, not raw HTTP, from sensors: lightweight, decouples detection from API
- Frames batched (1 msg/sec, ≤200 frames/msg), never per-frame
- Detection engine is an independent service subscribing to the broker — not part of the backend
- Sensor clocks are untrusted; backend stamps `received_at`
- LLM explanations start as templates + prompt-engineered API calls; fine-tuning is a v2 goal after collecting (event → explanation) pairs in production

## 4. Tech Stack & Conventions

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync ORM + asyncio.to_thread for writes), aiomqtt |
| Database | PostgreSQL 16 |
| Messaging | Mosquitto 2.x (MQTT) |
| Frontend | React + Vite + TypeScript (Arsany's domain) |
| Firmware | ESP32, Arduino/C++ (Ammar's domain) |
| Dev environment | Windows 11 host, PowerShell — use PowerShell-compatible commands; venv at `backend/.venv`; Docker Desktop runs db + mosquitto only (hybrid mode); backend runs locally with `uvicorn --reload` |
| Testing | pytest |

Conventions:

- All datetimes are timezone-aware UTC
- MAC addresses normalized to `AA:BB:CC:DD:EE:FF` (upper, colon-separated) at ingest
- IDs are UUID strings; frames use biginteger surrogate keys
- Env config via pydantic-settings (`backend/app/config.py`), overridable by env vars
- CORS allows `http://localhost:5173` and `http://localhost:3000`
- No secrets in code; LLM API keys come from env var `LLM_API_KEY`
- Tables created via `Base.metadata.create_all` during M0 (Alembic migrations are a later task)

## 5. Data Contracts (BINDING — these are the team-wide signed-off schemas)

Canonical source: `backend/app/schemas.py`. Duplicate here for reference.

### MQTT topics

| Topic | Direction | Payload |
| --- | --- | --- |
| `prodos/sensors/{sensor_id}/frames` | sensor → broker | FrameBatch JSON |
| `prodos/events` | detection engine → broker | DetectionEvent JSON |

### FrameBatch / WiFiFrame (sensor → backend)

```python
FrameType = Literal["beacon", "probe_req", "probe_resp", "deauth", "disassoc", "other"]

class WiFiFrame(BaseModel):
    uptime_ms: int | None          # sensor monotonic clock (untrusted)
    timestamp: datetime | None     # only if sensor NTP-synced
    channel: int                   # 1–14
    frame_type: FrameType
    src_mac: str                   # normalized upper-case on ingest
    dst_mac: str
    bssid: str | None
    ssid: str | None
    rssi: int                      # -128..0 dBm
    seq_num: int | None            # 0..4095

class FrameBatch(BaseModel):
    sensor_id: str                 # 1–64 chars
    batch_seq: int                 # gaps = dropped batches
    frames: list[WiFiFrame]        # 1–200
```

### DetectionEvent (detection engine → backend)

```python
EventType = Literal["evil_twin", "rogue_ap", "deauth_flood", "anomaly"]

class DetectionEvent(BaseModel):
    event_id: str                  # uuid, generated by engine
    event_type: EventType
    detected_at: datetime
    severity: int                  # 1–10
    confidence: float              # 0.0–1.0
    sensor_ids: list[str]
    details: dict                  # rule-specific, e.g.
      # deauth_flood: {"src_mac": "...", "rate_per_sec": 63, "window_s": 30}
      # evil_twin:    {"ssid": "CafeWiFi", "known_bssid": "...", "rogue_bssid": "..."}
```

### Alert (backend → dashboard)

```python
class Alert(BaseModel):
    alert_id: str
    event_id: str
    created_at: datetime
    severity: int                  # 1–10
    title: str                     # "Deauthentication flood detected"
    explanation: str               # plain language, no jargon
    recommended_action: str
    status: Literal["new", "acknowledged", "resolved"] = "new"
```

### REST/WebSocket surface (backend → frontend)

- `GET /health` → `{"status": "ok"}`
- `GET /frames/recent?seconds=300&limit=50&frame_type=<opt>` → list of stored frames (newest first)
- `WS /ws/frames` → live JSON frames as they're ingested
- Planned (Fares's tasks): `GET/POST /sensors`, `GET /events`, `GET /alerts`, `PATCH /alerts/{id}` (acknowledge/resolve), `WS /ws/alerts`
- Auto-generated OpenAPI docs at `/docs`

## 6. Current Repository State (as of this document)

> **Note (verified Oct 2 2026):** §6 previously claimed this backend was implemented when the repo
> was in fact empty. It has since been rebuilt. Verified working: M0 vertical slice, sensors
> registry (F-1), frame retention (F-2), and the detection skeleton (F-3) — all exercised against a
> real MQTT broker and SQLite. Still unverified on Postgres itself; no Docker on the dev host.

```text
prodos/
├── docker-compose.yml            # db (postgres:16, :5432) + mosquitto (:1883) + backend (build ./backend)
├── infra/mosquitto/mosquitto.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt          # fastapi, uvicorn[standard], sqlalchemy, psycopg[binary], pydantic, pydantic-settings, aiomqtt
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI app: lifespan (create_all + mqtt task), CORS, /health, /ws/frames
│       ├── config.py             # Settings: database_url, mqtt_host/port, mqtt_topic_frames
│       ├── schemas.py            # contracts above (WiFiFrame, FrameBatch, DetectionEvent, Alert)
│       ├── database.py           # engine + SessionLocal
│       ├── models.py             # Frame, Event, Alert SQLAlchemy tables
│       ├── mqtt.py               # mqtt_ingest_loop() + Broadcaster (WebSocket fan-out)
│       └── routers/frames.py     # GET /frames/recent
├── scripts/fake_sensor.py        # simulated ESP32; flags: --evil-twin (clone after 15s), --deauth (60 deauth/s after 10s), --sensor ID, --host
├── .env.example                  # every Settings variable, documented
├── detection/                    # F-3 skeleton — OWNED BY ZAKI & OMAR, do not modify
│   ├── main.py                   # Detector base + DemoDeauthDetector; subscribes frames, publishes prodos/events
│   ├── schemas.py                # byte-identical copy of backend/app/schemas.py
│   ├── requirements.txt          # aiomqtt, pydantic only
│   └── README.md                 # how to run + extend
├── firmware/README.md            # placeholder — Ammar's ESP32 code
└── frontend/README.md            # placeholder — Arsany's React app
```

Implemented and working: monorepo, docker-compose, MQTT ingestion → Postgres, `/frames/recent`,
`/ws/frames` live stream, `/sensors` registry, hourly frame retention, detection skeleton, fake
sensor with attack simulation modes.

Windows note: `aiomqtt` needs `add_reader`/`add_writer`, which the default ProactorEventLoop does
not implement. Both `backend/app/main.py` and `detection/main.py` set the selector event loop
policy at startup. Do not remove those lines — without them MQTT silently times out.

Run instructions (Windows hybrid mode):

```powershell
docker compose up -d db mosquitto
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt paho-mqtt
uvicorn app.main:app --reload

# second terminal, repo root, venv active:
python scripts/fake_sensor.py          # or --deauth / --evil-twin

# verify:
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod "http://localhost:8000/frames/recent?limit=5"
```

## 7. Milestones

| ID | Milestone | Target | Status |
| --- | --- | --- | --- |
| M0 | Vertical slice: 1 sensor → MQTT → backend → live dashboard | Oct 8, 2026, 20:00 | In progress (backend done, frontend pending Arsany) |
| M1 | 3 sensors, full storage, deauth-rate rule + duplicate-SSID/BSSID rule | Nov 15 | Detection team |
| M2 | Severity scoring, events → alerts pipeline, WebSocket push (<5s end-to-end) | Dec 15 | Fares-led |
| M3 | AI explanation layer (templates → LLM), alert history UI, usability pass | Jan 15 | Fares + Mohamed Ahmed |
| M4 | Attack test harness, AWID baseline validation, pilot prep | Feb 15 | Zaki + Omar |
| Pilot | 2-week real deployment at one small business | Feb–Mar | All |

## 8. Open Decisions (blocking others — chase these)

- **Sensor timestamping:** `uptime_ms` only, or NTP-sync at boot + `timestamp`? (Ammar)
- **Channel strategy:** hop channels or pin each of 3 sensors to fixed channels? (Ammar + Zaki)
- **LLM provider** for explanation layer v1 (Mohamed Ahmed + Fares)

## 9. FARES'S TASK BACKLOG — execute in this order

Each task: description, files, acceptance criteria. Complete one task per session; commit after each with a message referencing the task ID.

### F-1 · Sensors CRUD + registry — Priority: HIGH

**Why:** the dashboard needs a device registry; sensors need identity beyond a free-text string.

Do:

- New model `Sensor` in `backend/app/models.py`: `sensor_id` (PK, string), `name`, `location`, `channels` (JSON, e.g. `[1,6,11]`), `last_seen_at`, `registered_at`, `status` (online/offline/retired).
- Router `backend/app/routers/sensors.py`: `GET /sensors`, `POST /sensors`, `GET /sensors/{id}`, `PATCH /sensors/{id}`.
- Update `mqtt.py` `_handle_message` to upsert `last_seen_at` and set `status` online for any `sensor_id` seen on the frames topic.
- Optional small background task: mark sensors offline if `last_seen_at` older than 60s.

Accept: POST `/sensors` then GET `/sensors` returns it; running fake sensor flips a registered sensor to online with fresh `last_seen_at`.

### F-2 · Frame retention job — Priority: HIGH

**Why:** beacon traffic (~10/sec per AP × hours × 3 sensors) will fill Postgres within days; the pilot must survive 2 weeks.

Do:

- Background asyncio task in `main.py` lifespan (or separate `backend/app/retention.py`): hourly, `DELETE FROM frames WHERE received_at < now() - interval '7 days'`. Make the retention days configurable via `Settings`.
- Batch the delete (e.g. `LIMIT 10000` in a loop) so it never locks the table.

Accept: with retention set to 0 days via env var in a test, old frames are purged and new ingestion continues without error.

### F-3 · Detection engine skeleton stub (hand-off to Zaki & Omar) — Priority: HIGH

**Why:** give the detection team a running skeleton, not a README. They own it after hand-off.

Do (one-time skeleton inside `detection/` — this is the ONLY permitted write to that directory):

- `detection/main.py`: asyncio loop subscribing to `prodos/sensors/+/frames` via aiomqtt, validating with an imported copy of the same schemas (duplicate `detection/schemas.py` — keep byte-identical to `backend/app/schemas.py`; add a comment in both files: "CONTRACT — must stay in sync").
- Structure: a `Detector` base class with `def process_batch(self, sensor_id, frames) -> list[DetectionEvent]`, plus a `DemoDeauthDetector` that fires a `deauth_flood` event when it sees ≥30 deauth frames from one `src_mac` within a 10s window (sliding window, in-memory).
- Publishes `DetectionEvent` JSON to `prodos/events`.
- `detection/requirements.txt` (aiomqtt, pydantic only) and a short `detection/README.md` explaining how to run + extend.
- Test with `python scripts/fake_sensor.py --deauth`: events must appear on `prodos/events` (verify with `mosquitto_sub -t "prodos/events" -v` in Docker: `docker exec -it prodos-mosquitto mosquitto_sub -t "prodos/events" -v`).

Accept: fake sensor `--deauth` produces `DetectionEvent` messages on the topic within seconds of the flood starting.

### F-4 · Event ingestion + alerts pipeline + /ws/alerts — Priority: HIGH (this is M2 core)

**Why:** completes the backend's second data path; this is where the <5s alert latency is earned.

Do:

- In `backend/app/mqtt.py`: add a second subscription `prodos/events`; validate payload as `DetectionEvent`, store into `events` table (use the existing `Event` model).
- New module `backend/app/alerts.py`: on each stored event, generate an `Alert` and persist it. Explanation/recommendation come from the explanation layer (F-5); wire it in.
- Extend `Broadcaster` pattern: new `/ws/alerts` WebSocket endpoint pushing new alerts as JSON.
- REST: `GET /events?limit=50`, `GET /alerts?status=new&limit=50`, `PATCH /alerts/{alert_id}` with body `{"status": "acknowledged" | "resolved"}` (Pydantic input model, validate the literal).
- New routers: `backend/app/routers/events.py`, `backend/app/routers/alerts.py`.

Accept: run fake sensor `--deauth` + detection stub → alert row exists in Postgres, `GET /alerts` returns it, a connected `/ws/alerts` client receives it within 5 seconds of the event's `detected_at`.

### F-5 · AI explanation layer v1 (template + LLM behind one interface) — Priority: HIGH (M3 core, co-owned with Mohamed Ahmed)

**Why:** proposal objective #3 — plain-language explanations a café owner understands.

Do:

- New package `backend/app/ai/` with:
  - `explanation.py`: an `ExplanationProvider` protocol: `async def explain(event: DetectionEvent) -> Explanation(title: str, explanation: str, recommended_action: str)`.
  - `template_provider.py`: deterministic, offline fallback. Plain language, zero jargon, severity-aware phrasing. Examples to match tone:
    - `deauth_flood`: title "Someone is trying to knock customers off your WiFi", explanation "A device near your premises is repeatedly sending disconnect signals to your WiFi. This is often done to force customers to reconnect to a fake network copy. We are monitoring it closely.", action "Check the list of alerts. If customers complain they keep getting disconnected, consider temporarily changing your WiFi password."
    - `evil_twin`: title "A copy of your WiFi network has appeared", explanation "Someone nearby is broadcasting a network with the same name as yours. Customers connecting to it by mistake could have their data exposed.", action "Ask staff to warn customers to verify the network name before connecting. We will keep tracking the fake network."
  - `llm_provider.py`: same interface; calls an LLM chat-completions API. Provider-agnostic: base URL + model + key from env (`LLM_API_BASE`, `LLM_MODEL`, `LLM_API_KEY`). System prompt encodes: audience is a non-technical small-business owner; ≤3 short sentences; no technical jargon (never say "deauthentication frame", "BSSID", "802.11"); always end with one concrete recommended action; severity 1–3 calm tone, 8–10 urgent but not panic.
  - Selection logic: use LLM if `LLM_API_KEY` set, else template. LLM failure (timeout 5s, error) must fall back to template — alert delivery never blocks on AI.
- F-4's alert generation calls this provider.
- Logging for future fine-tuning (important — Mohamed Ahmed needs this): every generated explanation is appended to table `explanation_logs` (new model): `event` (JSON), `provider_used`, `prompt` (text, null for template), `output` (JSON), `created_at`. This is the v2 fine-tuning dataset.

Accept: with no API key, alerts carry template explanations matching the tone above; with key set, LLM output used; with key set but server unreachable, alerts still delivered with template text and a warning logged; `explanation_logs` grows one row per alert.

### F-6 · Backend test suite — Priority: MEDIUM

Do: pytest under `backend/tests/`: schema validation (valid/invalid FrameBatch, MAC normalization), `/frames/recent` filtering, alert PATCH transitions, explanation fallback path. Use an in-memory SQLite engine for DB tests (models are portable) and monkeypatch MQTT.

Accept: pytest green from `backend/`; no network/broker required.

### F-7 · Pilot deployment mode — Priority: MEDIUM (needed by Feb)

Do:

- `docker-compose.prod.yml`: single-host (Raspberry Pi 4 or cloud VM), all services in Docker, backend without `--reload`, restart policies, Mosquitto with persistence volume, Postgres data volume, env file for secrets.
- `.env.example` documenting every variable.
- README section: "Pilot deployment" — bring-up steps and how to point sensors at the host.

Accept: on a clean machine, `docker compose -f docker-compose.prod.yml --env-file .env up -d` yields a working system (verifiable with fake sensor pointed `--host` at it).

### F-8 · API polish for Arsany — Priority: MEDIUM

Do: pagination on `/alerts` and `/events` (cursor or offset), `GET /alerts/stats` (counts by status + severity, last 24h) for dashboard summary cards, and a short `docs/API.md` for the frontend dev. Keep `/docs` OpenAPI as source of truth.

Accept: `/alerts/stats` returns correct counts against seeded data.

### F-9 · Alembic migrations — Priority: LOW (after M3)

Replace `create_all` with Alembic; one initial migration matching current models.

### F-10 · v2 backlog (do NOT start until M0–M4 done)

Fine-tuning pipeline on collected `explanation_logs`; ML anomaly detection over stored frames; Telegram/email notifications; historical analytics endpoints; OTA sensor updates.

## 10. Hard constraints for the agent

- Never modify `frontend/`, `firmware/`, or `detection/` beyond the F-3 one-time skeleton.
- Never change `schemas.py` field names/types without flagging it in the commit message as a CONTRACT CHANGE — other teams build against it.
- Windows/PowerShell host: no bash-only syntax in scripts or docs.
- No secrets in code. No `--reload` in prod compose.
- Timezone-aware UTC everywhere. MAC normalization stays in the schema validator.
- Alert delivery must never depend on the LLM being reachable — templates are the floor.
- Commit per task, message format: `F-<n>: <summary>`.