Prodos demo — runbook (F-25)

Status: harness written, not yet run by its author. The integrator runs it and pastes the result.

One command starts the whole stack on one laptop, live, and one Ctrl+C stops it. No Docker and no
external services: the broker runs inside the harness process (the same amqtt engine
`scripts/smoke_test.py` uses) and the database is a throwaway SQLite file. Everything else is the
real thing — real uvicorn, real detection engine, real fake sensor, real Vite dev server — talking
over MQTT and HTTP.

## What runs

| Component | Process | Port | Notes |
| --- | --- | --- | --- |
| MQTT broker | amqtt, inside `run_demo.py` | 1883 | Reuses a broker already listening there (e.g. Docker mosquitto) instead of starting one. |
| Backend | `backend/run.py`, real uvicorn | 8000 | `/docs`, `/health`, `/ws/frames`, `/ws/alerts`. `backend/_demo.db`. |
| Detection engine | `detection/main.py` | — | Subscribes to frames, publishes `prodos/events`. One rule: deauth flood. |
| Fake sensor | `scripts/fake_sensor.py` | — | Publishes 1 batch/sec as `sensor-01`. |
| Dashboard | `npm run dev` | 5173 | Vite prints its real URL; 5174 if 5173 is taken. |

Log lines are prefixed and interleaved in this one terminal: `[backend]`, `[detection]`, `[sensor]`,
`[frontend]`. Nothing is written to a log file, so closing the window loses it — that is deliberate,
the demo is meant to be watched, not exhumed.

## Prerequisites, once

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

cd ..\frontend
npm install
```

`requirements-dev.txt` supplies amqtt (the broker) and pytest. The sensor needs `paho-mqtt`, which
arrives with `aiomqtt`.

Stop stray backends first. A leftover `python run.py` keeps port 8000 and may keep `_demo.db` open,
and the harness refuses to start rather than attaching to it:

```powershell
Stop-Process -Name python -Force
```

## Run it

From the repo root, with the backend venv's interpreter (not a global `python`):

```powershell
backend\.venv\Scripts\python.exe scripts\run_demo.py
```

| Flag | Effect |
| --- | --- |
| `--scenario deauth` | Default. Deauth flood starts 10s after the sensor boots. |
| `--scenario evil-twin` | `CafeWiFi` clone beacon at 15s. **No alert** — see Known limits. |
| `--scenario both` | Both of the above. |
| `--scenario idle` | Normal beacon traffic only. |
| `--no-frontend` | Pipeline only; no Vite, no dashboard. |
| `--keep` | Reuse the previous `backend/_demo.db` instead of wiping it. |

The harness seeds the demo shop through the REST API, then restarts the backend once — see
[Why the restart](#why-the-restart).

## What to watch, in order

Boot takes roughly 10–15 seconds. Then:

1. `[backend]` runs `alembic upgrade head`, connects to MQTT, and `[detection]` logs
   `Connected. Listening on prodos/sensors/+/frames`.
2. The banner prints. Open <http://localhost:5173>.
3. Within a second: **Backend API → Online**, **Front counter → online** (the seeded sensor name),
   and **Live Frame Activity** counting (~10 beacons/sec).
4. ~10 seconds after the sensor started: `[sensor] [sensor-01] DEAUTH FLOOD STARTED`, then
   `[detection] ... Event sent: deauth_flood (severity 6)`. The alert card appears on the dashboard in
   well under a second — the measured path is 0.02–0.25s from `created_at` to the WebSocket push.
5. Press **Acknowledge**, then **Mark resolved**. `[backend]` logs the `PATCH`, the badge changes.
   `new → acknowledged → resolved` is the only legal direction.
6. **Sites** shows `Demo Cafe` with the seeded WiFi name and three known access points,
   `sensor-01` assigned. **Checklist** is already 8/8 yes. **Trust** has a public link and QR.
   **Score** shows the snapshot from the restart.

The seeded values match what the fake sensor broadcasts, so network hygiene scores full marks:
`CafeWiFi` from `AA:BB:CC:00:00:01..03`.

## Why the restart

`score_loop` (`backend/app/scoring/engine.py`) computes at backend startup and then once a day. A
site created *after* startup has no snapshot until the next sweep, and the Score view would say "No
snapshot yet" for the whole demo. So the harness seeds, waits for frames, and restarts the backend
once. That is the only reason the demo boots the backend twice.

A fresh database scores **~70 "fair"**, and that is the feature working:

| Component | Fresh-demo value | Why |
| --- | --- | --- |
| Monitoring coverage | ~0 / 30 | The window is 1008 ten-minute buckets; a demo fills the current one. |
| Alert response | 30 / 30 | No alerts had been attributed at snapshot time (`total == 0` counts as 1.0). |
| Network hygiene | 15 / 15 | Three known APs broadcasting a configured SSID, nothing unknown. |
| Practices checklist | 15 / 15 | The harness answered all eight yes. |
| Threat exposure | 10 / 10 | No events yet. |

Two useful demonstrations follow from that:

- Restart with `--keep` **before** acknowledging the deauth alert: alert response drops to 0/30 and
  the score falls to ~40 "needs attention". Restart **after** acknowledging it: 30/30, back to ~70.
- Monitoring coverage is the one component a short demo cannot honestly fill. Leave the stack
  running (or seed a week of real frames) and it climbs. Do not fabricate frames to make the number
  look better — the score measures observed coverage, which is the point of it.

## Teardown

`Ctrl+C` in the terminal running the harness. It kills every child with `taskkill /PID <pid> /T /F`
on Windows, so the node process behind `npm run dev` dies with its `cmd.exe` wrapper and 5173 is free
for the next run. The broker thread dies with the process.

The database is left on disk at `backend/_demo.db` (git-ignored). The next run wipes it unless you
pass `--keep`.

## Attack scenarios and what detection actually sees

The fake sensor broadcasts three `CafeWiFi` APs (`AA:BB:CC:00:00:01..03`) and, per flag, either
60 deauth frames/sec from `11:22:33:44:55:66` or a single clone beacon from `DE:AD:BE:EF:00:99`
carrying the same SSID.

`detection/detectors/deauth.py` fires one `deauth_flood` event when a single `src_mac` contributes
≥30 deauth frames inside a 10-second sliding window. The event is then published at QoS 1, stored by
the backend, and turned into an alert.

- **One alert per flood, not one per second.** The detector re-arms as soon as that sender has
  fewer than 30 deauth frames in the last 10s, so a continuous flood yields exactly one alert.
- `--scenario evil-twin` produces the rogue beacon in `/frames/recent` (filter `frame_type=beacon`,
  look for `DE:AD:BE:EF:00:99`) but **no alert**, because the evil-twin / rogue-AP rule belongs to
  the detection team and is not implemented yet. Say that out loud in a demo; do not imply the
  clone was caught.

## Live-key run (integrator)

The harness never sets `LLM_*`; it inherits your shell and `backend/.env`. With no key the
explanation layer uses the offline template provider, which is the floor. To exercise the LLM path,
set all three variables — a key alone is a misconfiguration and logs
`LLM_API_KEY set but LLM_API_BASE/LLM_MODEL missing; using template provider`:

```powershell
$env:LLM_API_KEY  = "sk-..."
$env:LLM_MODEL    = "gpt-4o-mini"                        # any model the endpoint serves
$env:LLM_API_BASE = "https://api.openai.com/v1"          # OpenAI-compatible root, no trailing /chat/completions
backend\.venv\Scripts\python.exe scripts\run_demo.py
```

Wait for the deauth alert, then check which provider wrote it:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "import sqlite3; print(sqlite3.connect('_demo.db').execute('select id, provider_used, prompt is not null, substr(output, 1, 60) from explanation_logs order by id desc limit 3').fetchall())"
```

Pass: at least one row with `provider_used = 'llm'` and `prompt is not null`. Template rows read
`provider_used = 'template'` with `prompt` NULL — that is how the two are told apart in the
fine-tuning dataset.

Then the failure path, which is the contract that matters: keep the key, point the base at a closed
port

```powershell
$env:LLM_API_BASE = "http://127.0.0.1:9/v1"
```

and rerun. The alert still arrives with template wording, `[backend]` shows
`explanation provider failed (...); falling back to template` with a traceback, and the
`explanation_logs` row for that alert says `provider_used = 'template'`. An unreachable model costs
tone, not the alert.

Unset the three variables when finished. They persist for the PowerShell session.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `Something already answers on :8000` | A stray backend. `Stop-Process -Name python -Force`. |
| `Cannot delete ... _demo.db` | Same thing, still holding the file. Kill it, or run `--keep`. |
| Frontend never appears | `[frontend]` says why. Usually `npm install` was never run in `frontend/`, or npm is not on PATH. The rest of the demo still works with `--no-frontend`. |
| No frames, no alerts | Check `[sensor]` and `[detection]` for connection errors. If 1883 was already in use, the harness reused that broker — make sure it really is an MQTT broker. |
| Alert never appears on the dashboard | The WS client reconnects with backoff. Reload the tab; `/alerts` still has the row. |
| Score view empty | The restart after seeding failed. `[backend]` lines around the second start say why. |

## Known limits (state them, do not paper over them)

- **Detection has one rule.** Deauth flood only; evil twin / rogue AP are the detection team's
  (Zaki, Omar).
- **Score monitoring coverage needs real uptime.** A 30-second demo cannot fill a 7-day window.
- **No auth, no TLS.** The harness deliberately blanks `ADMIN_API_KEY` so the owner views are open;
  it does not change the code's behaviour, only this run's environment. LAN demo only.
- **SQLite.** Timestamps come back without a zone locally; the dashboard appends `Z`. Production and
  the pilot run PostgreSQL.
- **Not the pilot path.** Pilot deployment is `docker-compose.prod.yml` plus the README section.
  This harness is for a laptop and a 90-second story.
