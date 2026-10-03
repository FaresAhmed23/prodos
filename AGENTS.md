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
- `GET /events?limit=50&event_type=<opt>&cursor=<event_id>` · `GET /alerts?status=new&limit=50&cursor=<alert_id>` · `GET /alerts/stats?window_hours=24` · `PATCH /alerts/{alert_id}` with `{"status": "acknowledged" | "resolved"}` · `WS /ws/alerts` → live alerts
- Auto-generated OpenAPI docs at `/docs`; `docs/API.md` is the frontend-facing guide (pagination, timestamp format, WebSocket lifecycle)

F-8 added `cursor` and `window_hours` as **optional** query params, one new read-only endpoint
(`/alerts/stats`), and two response headers. All additive: every pre-existing call returns exactly
what it did before, and `GET /alerts` / `GET /events` still return a bare JSON array rather than an
envelope, so nothing in the dashboard had to change.

## 6. Current Repository State (as of this document)

> **Note (verified Oct 2 2026):** §6 previously claimed this backend was implemented when the repo
> was in fact empty. It has since been rebuilt. Verified working: M0 vertical slice, sensors
> registry (F-1), frame retention (F-2), detection skeleton (F-3), and the event→alert pipeline
> (F-4) — all exercised against the real thing: **PostgreSQL 16.10**, **Mosquitto 2.1.2**, every
> service a separate process. SQLite + in-process amqtt remain supported for dependency-free runs.

```text
prodos/
├── docker-compose.yml            # db (postgres:16, :5432) + mosquitto (:1883) + backend (build ./backend)
├── infra/mosquitto/mosquitto.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt          # fastapi, uvicorn[standard], sqlalchemy, psycopg[binary], pydantic, pydantic-settings, aiomqtt, httpx
│   ├── requirements-dev.txt      # amqtt + websockets (scripts/smoke_test.py) + pytest (backend/tests/)
│   ├── pytest.ini                # testpaths=tests, pythonpath=. — the pytest entrypoint is `python -m pytest` from backend/
│   ├── tests/                    # F-6 suite: conftest (in-memory SQLite, bare-app client, loopback LLM stub)
│   │                             #   + test_schemas / test_frames / test_alerts / test_explanation. 99 checks, no broker.
│   ├── run.py                    # Windows-safe uvicorn entrypoint (selector event loop) — use this
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI app: lifespan (create_all + mqtt tasks), CORS, /health, /ws/frames, /ws/alerts
│       ├── config.py             # Settings: database_url, mqtt_host/port, mqtt_topic_frames, mqtt_topic_events, llm_api_base/model/key/timeout
│       ├── schemas.py            # contracts above (WiFiFrame, FrameBatch, DetectionEvent, Alert, EventOut, AlertUpdate)
│       ├── database.py           # engine + SessionLocal (pins the Postgres session to UTC)
│       ├── models.py             # Frame, Event, Alert, Sensor, ExplanationLog SQLAlchemy tables
│       ├── mqtt.py               # mqtt_ingest_loop() + events_ingest_loop() + Broadcaster fan-out
│       ├── alerts.py             # DetectionEvent -> stored Event -> generated Alert + explanation_logs row
│       ├── ai/                   # co-owned with Mohamed Ahmed — explanation layer
│       │   ├── explanation.py    # Explanation dataclass + ExplanationProvider protocol
│       │   ├── template_provider.py  # offline, deterministic, jargon-free (the floor)
│       │   └── llm_provider.py   # any OpenAI-compatible endpoint (base URL + model + key from env); raises, never falls back itself
│       ├── pagination.py        # keyset cursor paging shared by /alerts and /events
│       └── routers/              # frames.py, sensors.py, events.py, alerts.py
├── docs/API.md                  # frontend-facing guide for Arsany (F-8)
├── scripts/fake_sensor.py        # simulated ESP32; flags: --evil-twin (clone after 15s), --deauth (60 deauth/s after 10s), --sensor ID, --host
├── scripts/smoke_test.py         # Docker-free end-to-end check; SMOKE_DATABASE_URL / SMOKE_BROKER swap in the real deps
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
`/ws/frames` live stream, `/sensors` registry, hourly frame retention, `prodos/events` subscription,
`/events`, `/alerts`, `/alerts/stats`, `PATCH /alerts/{id}`, `/ws/alerts` live push, cursor
pagination on both feeds, offline template explanations, template-or-LLM provider selection,
`explanation_logs` audit trail, detection skeleton, fake sensor with attack simulation modes,
`docs/API.md` frontend guide.

### AI explanation layer (F-5)

Two providers behind one `ExplanationProvider` protocol. `alerts.build_provider()` picks the LLM
when `LLM_API_KEY` is set and the offline template otherwise, so the key is the only switch — there
is no way to end up calling a model nobody configured. `llm_provider.py` talks to any
OpenAI-compatible `/chat/completions` endpoint over a raw `httpx` POST (base URL + model + key),
which keeps it vendor-neutral without a dependency per vendor. It deliberately has **no** fallback
logic of its own: every failure raises, and `handle_detection_event` catches, logs a warning and
falls back to the template. The rule that makes this safe is "an unreachable model costs tone, not
the alert".

`explanation_logs` (event JSON, `provider_used`, `prompt`, `output` JSON, `created_at`) is written
in the *same transaction* as the alert, and only on the path that actually creates one — a replayed
`event_id` must not inflate the fine-tuning dataset. `prompt` is null for template rows, which is
how a reviewer later separates real LLM output from offline text.

Expect a full traceback in the log per alert if a key is set but the endpoint is unreachable. That
is deliberate (`exc_info=True`) and loud on purpose: it means a configured provider is broken and
should be fixed, and it stops once the provider works.

Verified three ways, all against real processes: no key → template with `prompt` NULL; key + a stub
chat-completions server → LLM output used, `Bearer` key sent, prompt stored; key + a closed port →
template text delivered anyway with a warning. `explanation_logs` held 1:1 with alerts in every
mode. Regression: `smoke_test.py` 25/25 on Mosquitto 2.1.2 + PostgreSQL 16.10 and the F-4 suite
green. Note for F-6 (now done): the LLM path needed the stub server as a fixture, since there was no
pytest coverage of it and no real key in the repo. It is the `stub_llm` fixture in
`backend/tests/conftest.py`, and the fallback contract "an unreachable model costs tone, not the
alert" is asserted there rather than only described here.

Windows note (do not "clean this up"): `aiomqtt` drives its socket via `add_reader`/`add_writer`,
which `ProactorEventLoop` does not implement, so MQTT ingest dies with `NotImplementedError` and
every connection silently times out. uvicorn 0.54 hardcodes `ProactorEventLoop` on Windows and
ignores the event-loop policy entirely, so the two entrypoints fix it differently and both fixes
are required:

- `backend/run.py` passes `loop="run:selector_or_default"` to uvicorn.
- `detection/main.py` calls `asyncio.run()` itself, so it sets `WindowsSelectorEventLoopPolicy`.

Run instructions (Windows hybrid mode):

```powershell
docker compose up -d db mosquitto
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python run.py --reload            # NOT `uvicorn app.main:app` — see Windows note

# second terminal, repo root, venv active:
python scripts/fake_sensor.py          # or --deauth / --evil-twin

# verify:
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod "http://localhost:8000/frames/recent?limit=5"
```

### Verifying without Docker

Docker Desktop is not required to check the wiring. This runs the real backend (uvicorn), the real
detection engine, and the real fake sensor as separate processes over MQTT/HTTP, using SQLite and
an in-process broker in place of Postgres/Mosquitto:

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
python ..\scripts\smoke_test.py        # ~30s, prints PASS/FAIL per check
```

It covers sensor CRUD, ingest, MAC normalization, the retention-compatible frame query, the live
`/ws/frames` push, and the full F-4 chain (event ingested → alert generated → `PATCH` transition →
`/ws/alerts` push).

### Running the same checks against the real dependencies

SQLite + in-process amqtt is the default because it needs nothing installed. Two env vars swap in
the real thing, and they can be combined — this is the configuration the pilot will run:

```powershell
$env:SMOKE_BROKER = "mosquitto"     # use a broker already listening on 1883
$env:SMOKE_DATABASE_URL = "postgresql+psycopg://prodos@127.0.0.1:5433/prodos"
backend\.venv\Scripts\python.exe scripts\smoke_test.py
```

The script drops and recreates the `public` schema when pointed at Postgres, so use a scratch
database only. With `SMOKE_BROKER` set it skips spawning amqtt and just checks that 1883 accepts
connections, so start the broker yourself first:

```powershell
mosquitto -c infra\mosquitto\mosquitto.conf -v
```

No admin rights and no Docker? Both dependencies can be had without either. Mosquitto installs
user-level via scoop (it extracts the installer rather than running it, so no UAC):
`scoop install mosquitto`. For Postgres use EDB's portable binaries zip — no Windows service:

```powershell
$bin = "$env:TEMP\opencode\pgsql\pgsql\bin"
Invoke-WebRequest -Uri https://get.enterprisedb.com/postgresql/postgresql-16.10-1-windows-x64-binaries.zip -OutFile "$env:TEMP\pg16.zip"
Expand-Archive "$env:TEMP\pg16.zip" "$env:TEMP\pgsql" -Force
& "$bin\initdb.exe" -D "$env:TEMP\pgdata" -U prodos --auth=trust --encoding=UTF8 --locale=C
Start-Process "$bin\postgres.exe" -ArgumentList "-D","$env:TEMP\pgdata","-p","5433" -WindowStyle Hidden
& "$bin\createdb.exe" -h 127.0.0.1 -p 5433 -U prodos prodos
```

Start Postgres with `Start-Process`, not `pg_ctl start`: `pg_ctl` leaves the server attached to the
console, so PowerShell blocks on it and killing the shell kills the database.

Verified green on Mosquitto 2.1.2 + Postgres 16.10: `smoke_test.py` 25/25 and the F-4 acceptance
suite 23/23, including the replay-dedup and status-transition checks. Re-ran on SQLite + amqtt
afterwards to confirm the defaults are untouched.

### Two things the real brokers disagreed about

**Timezone.** `database.py` passes `connect_args={"options": "-c timezone=UTC"}` for Postgres URLs.
Postgres renders `TIMESTAMPTZ` in the *session's* TimeZone, so on this Cairo host the API returned
`2026-10-02T17:25:14.123669+03:00` — the correct instant, but a different string than a UTC host
would produce, and a violation of the timezone-aware-UTC convention. SQLite never showed it,
because it has no `timestamptz` and was returning naive values all along.

Note this is set as a libpq connect option on purpose. An
`event.listens_for(Engine, "connect")` hook that runs `SET TIME ZONE` *looks* correct — it passes a
`SHOW timezone` check taken inside the hook — and is then silently undone, because psycopg opens an
implicit transaction for the statement and the pool's rollback-on-return reverts it.

**QoS: the backend half is done, the detection half is still open (PRO-16).** `fake_sensor.py`
publishes frames at `qos=0` and `detection/main.py` publishes `prodos/events` at the aiomqtt
default of QoS 0. The backend now subscribes `prodos/events` at `qos=1` (`mqtt.py`,
`events_ingest_loop`) while deliberately leaving the frame subscription at QoS 0 — ~200 frames/sec
per sensor is high-rate best-effort, a lost batch is tolerable, and QoS 1 would make the broker
queue against a slow consumer. A lost `DetectionEvent` is a silently dropped security alert, so it
is worth the retry.

**This is still inert end-to-end, and that is not a bug in the change.** MQTT delivers at
`min(publish QoS, granted QoS)` and a SUBSCRIBE can only lower delivery, never raise it, so a q1
subscription over a q0 publisher still arrives at q0. Verified both halves separately: the backend's
SUBSCRIBE is granted at QoS 1 (`Mosquitto -v` prints `prodos/events (QoS 1)`), and a probe
publishing at q1 is forwarded to the backend at `q1` and produces an alert. The moment
`detection/main.py` publishes at QoS 1, delivery is guaranteed with no further backend work. That
file belongs to Zaki and Omar, so it is left alone and raised as PRO-16. §5 should pin the intended
QoS per topic either way.

### Running the smoke test: it needs the broker to itself

`smoke_test.py` assumes no other backend is subscribed to `prodos/events`. If a stray `run.py` is
still connected to the same broker and database, it wins the insert race for each event, the smoke
test's own backend hits the `event_id` dedup and returns `None`, and the check fails as
`WS /ws/alerts pushed live alerts pushed=0`. That is the dedup behaving correctly against a second
consumer, not a regression — but it looks exactly like one. Stop stray backends first:

```powershell
Stop-Process -Name python -Force
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

### F-4 · Event ingestion + alerts pipeline + /ws/alerts — Priority: HIGH (this is M2 core) — **DONE**

**Why:** completes the backend's second data path; this is where the <5s alert latency is earned.

Do:

- In `backend/app/mqtt.py`: add a second subscription `prodos/events`; validate payload as `DetectionEvent`, store into `events` table (use the existing `Event` model).
- New module `backend/app/alerts.py`: on each stored event, generate an `Alert` and persist it. Explanation/recommendation come from the explanation layer (F-5); wire it in.
- Extend `Broadcaster` pattern: new `/ws/alerts` WebSocket endpoint pushing new alerts as JSON.
- REST: `GET /events?limit=50`, `GET /alerts?status=new&limit=50`, `PATCH /alerts/{alert_id}` with body `{"status": "acknowledged" | "resolved"}` (Pydantic input model, validate the literal).
- New routers: `backend/app/routers/events.py`, `backend/app/routers/alerts.py`.

Accept: run fake sensor `--deauth` + detection stub → alert row exists in Postgres, `GET /alerts` returns it, a connected `/ws/alerts` client receives it within 5 seconds of the event's `detected_at`.

Met: measured 0.02–0.25s from `created_at` to `/ws/alerts` delivery, every service running as its
own process. `scripts/smoke_test.py` now asserts this chain (25 checks). `GET /alerts` filters by
status; `PATCH /alerts/{id}` accepts only `acknowledged`/`resolved` and rejects `new` with 422;
unknown id is 404. Replaying a `DetectionEvent` with a duplicate `event_id` does not create a
second alert. Verified on PostgreSQL 16.10 and Mosquitto 2.1.2.

### F-5 · AI explanation layer v1 (template + LLM behind one interface) — Priority: HIGH (M3 core, co-owned with Mohamed Ahmed) — **DONE**

**Why:** proposal objective #3 — plain-language explanations a café owner understands.

Do:

- New package `backend/app/ai/` with:
  - `explanation.py`: an `ExplanationProvider` protocol: `async def explain(event: DetectionEvent) -> Explanation(title: str, explanation: str, recommended_action: str)`. **Already done in F-4.**
  - `template_provider.py`: deterministic, offline fallback. Plain language, zero jargon, severity-aware phrasing. **Already done in F-4**, which also wired it in behind `alerts.provider`. Titles it produces:
    - `deauth_flood`: "Someone is trying to knock customers off your WiFi"
    - `evil_twin`: "A copy of your WiFi network has appeared"
    - `rogue_ap`: "An unknown wireless network appeared nearby"
  - `llm_provider.py`: same interface; calls an LLM chat-completions API. Provider-agnostic: base URL + model + key from env (`LLM_API_BASE`, `LLM_MODEL`, `LLM_API_KEY`). System prompt encodes: audience is a non-technical small-business owner; ≤3 short sentences; no technical jargon (never say "deauthentication frame", "BSSID", "802.11"); always end with one concrete recommended action; severity 1–3 calm tone, 8–10 urgent but not panic.
  - Selection logic: set `alerts.provider` to the LLM provider when `LLM_API_KEY` is present. The `try/except` around `provider.explain` already exists in `alerts.py` and falls back to the template, so alert delivery never blocks on AI.
- F-4's alert generation already calls this provider.
- Logging for future fine-tuning (important — Mohamed Ahmed needs this): every generated explanation is appended to table `explanation_logs` (new model): `event` (JSON), `provider_used`, `prompt` (text, null for template), `output` (JSON), `created_at`. This is the v2 fine-tuning dataset.

Accept: with no API key, alerts carry template explanations matching the tone above; with key set, LLM output used; with key set but server unreachable, alerts still delivered with template text and a warning logged; `explanation_logs` grows one row per alert.

Met: all four cases verified with real processes and a stub chat-completions server (no key needed in
the repo). Provider selection, `Bearer` auth header, prompt capture, the fallback-with-warning path
and the 1:1 log-to-alert ratio all assert green. One real defect found and fixed: the deauth
template ran to four sentences while the LLM prompt caps at three, so the same owner could tell
which provider wrote an alert from the length alone — folded into three.

⚠️ **For Mohamed Ahmed:** `SYSTEM_PROMPT` in `ai/llm_provider.py` is the thing to tune, and it is
the only part of F-5 that needs your judgement rather than mine. The provider requires the model to
answer with a JSON object of exactly `title` / `explanation` / `recommended_action`; change the
wording freely, keep those three keys. `explanation_logs` starts collecting the (event → explanation)
dataset from the moment this merges, so real traffic begins filling it before any prompt tuning.

### F-6 · Backend test suite — Priority: MEDIUM — **DONE**

Do: pytest under `backend/tests/`: schema validation (valid/invalid FrameBatch, MAC normalization), `/frames/recent` filtering, alert PATCH transitions, explanation fallback path. Use an in-memory SQLite engine for DB tests (models are portable) and monkeypatch MQTT.

Accept: pytest green from `backend/`; no network/broker required.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

99 checks, ~5s. `pytest.ini` sets `pythonpath = .` and `-p no:cacheprovider` so the run needs no
`PYTHONPATH` and leaves no cache in the repo.

Met: 99/99 green. **Hermetic by construction, and verified that way** — the run was repeated with
every `python` process killed and nothing listening on 1883, with `DATABASE_URL` and all `LLM_*`
unset. No test imports `aiomqtt` or names a broker, which `Select-String` over `backend/tests/`
confirms mechanically.

**Two deliberate choices worth not "fixing" later.**

*The real routers, not `app.main`.* `conftest.py` mounts the four actual routers on a bare FastAPI
app and overrides `get_db`. Importing the real `app.main` would mean running its lifespan, which
opens an MQTT connection and spawns both ingest tasks — precisely what the acceptance criterion says
must not happen. Every route exercised is the shipped one; only the lifespan is skipped. MQTT is
excluded by never starting it rather than by monkeypatching a symbol, which is the stronger form of
"monkeypatch MQTT": there is no mock to be misconfigured.

*The LLM stub is a real loopback server.* F-5 asked for the stub as a fixture, and mocking
`httpx.AsyncClient.post` would have satisfied that sentence while verifying almost nothing — the URL
construction, the `Bearer` header and the response parser would all be bypassed. `stub_llm` runs
`HTTPServer` on `127.0.0.1` port 0 (OS-assigned, so no fixed port to collide on) and records the
request bodies. One socket on loopback, no external network, no broker.

In-memory SQLite needs `poolclass=StaticPool` together with `check_same_thread=False`; a bare
`sqlite://` gives each connection its own empty database and the tests fail confusingly.

Regression: `smoke_test.py` 25/25 on SQLite + in-process amqtt, twice.

Three defects the suite found while being written, all in the tests rather than the product, which
is the useful outcome: a miscounted hex digit in an expected MAC, a wrong assumption that
`event_type="meteor"` is a legal `EventType` — it is not, and the template's unknown-type fallback
is reached via `anomaly`, a *valid* `EventType` with no dedicated builder — and a fallback
assertion that had been written as a tautology (`assert x and "system" not in x or x` is always
true) and would have passed no matter what the log row contained.

One caveat carried over from F-8 and now asserted knowingly: SQLite does not round-trip tzinfo, so
`/alerts` returns naive datetimes under these tests while PostgreSQL returns `Z`. The tests compare
values and ordering, never the tz suffix, so this is invisible here — but do not "fix" a naive
datetime by loosening an assertion.

### F-7 · Pilot deployment mode — Priority: MEDIUM (needed by Feb)

Do:

- `docker-compose.prod.yml`: single-host (Raspberry Pi 4 or cloud VM), all services in Docker, backend without `--reload`, restart policies, Mosquitto with persistence volume, Postgres data volume, env file for secrets.
- `.env.example` documenting every variable.
- README section: "Pilot deployment" — bring-up steps and how to point sensors at the host.

Accept: on a clean machine, `docker compose -f docker-compose.prod.yml --env-file .env up -d` yields a working system (verifiable with fake sensor pointed `--host` at it).

### F-8 · API polish for Arsany — Priority: MEDIUM — **DONE**

Do: pagination on `/alerts` and `/events` (cursor or offset), `GET /alerts/stats` (counts by status + severity, last 24h) for dashboard summary cards, and a short `docs/API.md` for the frontend dev. Keep `/docs` OpenAPI as source of truth.

Accept: `/alerts/stats` returns correct counts against seeded data.

Met: cursor paging on both feeds, `/alerts/stats`, and `docs/API.md`.

**Cursor, not offset, and the bug that decided it.** `/alerts` grows while you read it, so offset
paging shifts the window under a polling client and silently repeats and skips rows — a new alert
landing at the top mid-scroll pushes everything down by one. Keyset paging anchors on a row the
client already has, so inserts cannot disturb it. Verified by inserting a brand-new alert *between*
pages and asserting zero overlap. The cursor is just the `alert_id`/`event_id` of the last row you
already hold, so there is nothing to parse; ordering is on `(timestamp, id)` because timestamp alone
leaves ties unordered and paging can then repeat or skip.

**Deliberately non-breaking.** `GET /alerts` and `GET /events` still return a **bare JSON array**; the
cursor comes back in `X-Next-Cursor` / `X-Has-More` headers rather than wrapping the response in an
envelope. Arsany is building against the array shape and the checkpoint is days away, so he should
not have to change working code. `cursor` and `window_hours` are optional, so every pre-existing
call returns exactly what it did before.

`AlertStats` is defined in `routers/alerts.py`, **not** in `schemas.py`: it is a REST-only
convenience, not the team-wide contract in §5, and putting it in `schemas.py` would have forced
another `detection/schemas.py` re-sync for no benefit. Its severity bands (`low` 1–3, `medium` 4–7,
`high` 8–10) reuse the same thresholds as `ai/template_provider.py`, so a card labelled "high" and an
alert that reads urgent are one judgement rather than two. `by_severity` always returns all three
keys so a card can render a zero without special-casing.

Verified against seeded data with known counts, on **both** backends: status counts, severity counts
including the 3/4 and 7/8 band boundaries, the 24h window excluding older alerts, 1h-vs-24h, full
feed coverage with no duplicates, cursor-plus-filter, unknown cursor → 400, and that the array shape
is unchanged. Regression: `smoke_test.py` 25/25 twice and the F-4 suite green on Mosquitto 2.1.2 +
PostgreSQL 16.10.

One check passes on PostgreSQL and fails on SQLite, and it is **not** an F-8 defect: SQLite's
`DATETIME` does not round-trip tzinfo, so datetimes come back naive. `/alerts` behaves identically —
the naive value is pre-existing and platform-wide, which is why the F-4 fix pinned the Postgres
session rather than the model. Production and the pilot both run PostgreSQL, where every datetime is
`Z`-suffixed. Noted in `docs/API.md` so Arsany is not surprised by a SQLite dev machine.

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