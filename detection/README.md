# Detection engine

**Owned by Omar Ahmed Fathy and Mohamed Zaki Ibrahim.** Fares created this skeleton for task
F-3 (AGENTS.md §9) as a hand-off. From that point it is yours — do not wait for further direction
to change anything here.

Standalone Python service. Subscribes to `prodos/sensors/+/frames`, publishes `DetectionEvent`
JSON to `prodos/events`. The backend picks those up and turns them into dashboard alerts (F-4).

## Run it

```powershell
# from the repo root, with a broker up
docker compose up -d mosquitto

cd detection
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Watch what it publishes, from the repo root:

```powershell
docker exec -it prodos-mosquitto mosquitto_sub -t "prodos/events" -v
```

Feed it an attack:

```powershell
cd ..
python scripts\fake_sensor.py --deauth
```

The demo detector fires once, a second or two after the flood starts. `fake_sensor --evil-twin`
currently produces nothing — no evil-twin rule exists yet.

Env overrides: `MQTT_HOST`, `MQTT_PORT`, `TOPIC_FRAMES`, `TOPIC_EVENTS`.

## The contract

`schemas.py` is a **byte-identical copy** of `backend/app/schemas.py`. Do not edit either one on
your own. It is a team-wide signed-off schema (AGENTS.md §5); changing a field name or type breaks
the sensor firmware, the backend, and the dashboard simultaneously. If a rule needs a field that
does not exist, raise it with Fares — it becomes a CONTRACT CHANGE across all three teams.

Check the copy still matches after any backend schema work:

```powershell
(Get-FileHash ..\backend\app\schemas.py).Hash -eq (Get-FileHash .\schemas.py).Hash
```

## Adding a rule

1. Subclass `Detector` and implement
   `process_batch(self, sensor_id: str, frames: list[WiFiFrame]) -> list[DetectionEvent]`.
2. Append an instance to `DETECTORS` in `main.py`.
3. Reuse the sliding-window idea from `DemoDeauthDetector` if your rule is rate-based.

`event_type` must be one of `evil_twin`, `rogue_ap`, `deauth_flood`, `anomaly` — the schema rejects
anything else. Put rule-specific context in `details`; the backend passes it straight through to the
alert and the AI explanation layer.

Keep state in memory, per process. Nothing here survives a restart, which is fine for M1 but is the
first thing to revisit if you move to three sensors and need cross-sensor correlation.

## What is deliberately fake

- `severity` in `DemoDeauthDetector` is a placeholder (`1 + count // 10`). Real severity scoring is
  M2 and lands in the backend.
- **No de-duplication across batches.** `fake_sensor --deauth` runs at a sustained 60 deauths/sec,
  so after the window clears it re-accumulates within one more batch and fires again — roughly one
  `deauth_flood` event per second for as long as the attack lasts. That is fine for a stub and
  wrong for production. Before M1 lands a real rule, decide the cooldown or dedup-by-`src_mac`
  policy, otherwise F-4 will generate an alert per second and the dashboard will be unusable.
- Single-sensor only. No correlation across sensors.
- No persistence, no replay, no pcap ingest. AWID validation is M4.