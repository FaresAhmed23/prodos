# Prodos

AI-powered wireless security assistant for small businesses. ESP32 sensors sniff
802.11 traffic and publish over MQTT; a backend stores frames, a detection engine
flags attacks, and detected events become plain-language alerts on a live
dashboard — "Someone is trying to knock customers off your WiFi", not "deauth
flood, 63 frames/sec".

- `AGENTS.md` — full project context: architecture, data contracts, task backlog.
  Read this before changing anything.
- `docs/API.md` — the REST/WebSocket guide for frontend work.

## Pilot deployment

Single host: a Raspberry Pi 4 (4GB) or a small cloud VM. Everything the repo
owns runs in Docker Compose. By Feb this is what the 2-week pilot runs on.

### Bring-up

On a clean machine, from the repo root:

```bash
cp .env.example .env
# set POSTGRES_PASSWORD (required) and LLM_API_KEY if you want live LLM text
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

Then verify, in this order — each step is a real dependency of the next:

```bash
docker compose -f docker-compose.prod.yml ps               # all three "healthy"
curl -fsS http://localhost:8000/health                    # {"status":"ok"}
docker compose -f docker-compose.prod.yml exec db \
  psql -U prodos -d prodos -c '\dt'                        # frames/events/alerts/...
```

`POSTGRES_PASSWORD` is required by the compose file itself
(`${POSTGRES_PASSWORD:?...}`), so a missing one aborts `up` with a clear message
rather than deploying the dev `prodos:prodos` credential.

### Point sensors at the host

Sensors and the detection engine publish to `MQTT_HOST`. Find the host's LAN
address (`ip addr` on Linux, `ipconfig` on Windows) and configure:

```bash
# ESP32 firmware: broker host/port = the pilot host's LAN address, port 1883
python scripts/fake_sensor.py --host <PILOT_HOST_LAN_IP>          # benign beacons
python scripts/fake_sensor.py --host <PILOT_HOST_LAN_IP> --deauth # attack sim
```

Then confirm frames are arriving at all:

```bash
curl -fsS "http://localhost:8000/frames/recent?limit=5"
```

Empty means the sensor is not reaching the broker. Check in this order:
`docker compose ... logs mosquitto` (is it accepting the connection?), then the
sensor's own serial/log output for its configured host.

Only MQTT (1883) and the backend (8000) are published to the LAN. Postgres is
deliberately not — reach it with `docker compose ... exec db psql`.

### Sizing a Raspberry Pi 4

Idle is comfortable. Under attack simulation, `--deauth` generates ~60 frames/sec
per sensor and the backend writes every one, so expect the Postgres volume — not
RAM — to be the binding constraint. Two controls, both already in place:
`RETENTION_DAYS=7` (default) and Mosquitto's `max_queued_messages` in
`infra/mosquitto/mosquitto.prod.conf`. Lower `RETENTION_DAYS` first if the SD
card fills; the frame table is by far the largest.

### Known gaps before a real pilot

- **The detection engine is not in the compose file.** `detection/` is owned by
  Zaki and Omar and has no Dockerfile yet, so it runs as a separate process
  against `MQTT_HOST=<pilot host>`. Until it ships an image, a pilot host runs
  four processes, not three, and compose is not the whole system. Adding it is a
  few lines once a Dockerfile exists.
- **QoS 1 is implemented end-to-end (PRO-16 closed).** The backend subscribes
  `prodos/events` at QoS 1 and `detection/main.py` publishes at QoS 1. QoS 1
  redelivery survives a broker restart because Mosquitto persists sessions.
- **Mosquitto allows anonymous connections.** The ESP32 firmware has nowhere to
  store a credential, so the broker trusts the local network. Do not expose the
  pilot host to the internet. See the comment in `mosquitto.prod.conf`.
- **No authentication or TLS on the API.** Port 8000 is plain HTTP.
- **No automated backup.** `pgdata` is a named volume and nothing snapshots it.
  Alerts and the `explanation_logs` fine-tuning dataset are the irreplaceable
  part; a nightly `pg_dump` is the obvious next step.

## Local development

See `AGENTS.md` §6. Short version on Windows:

```powershell
docker compose up -d db mosquitto
cd backend
.\.venv\Scripts\python.exe run.py --reload     # NOT `uvicorn app.main:app`
```

Tests need no broker and no database:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```
