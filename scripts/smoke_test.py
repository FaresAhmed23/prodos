"""End-to-end smoke test. One command, no Docker, no Postgres.

Runs the whole pipeline as separate OS processes, talking only over MQTT and
HTTP -- the same way the team runs it in dev:

    fake_sensor.py --deauth  ->  broker  ->  backend (uvicorn)
                                       ->  detection engine
    detection -> prodos/events
    backend   -> SQLite + /frames/recent + /ws/frames

Uses SQLite and an in-process amqtt broker in place of Postgres/Mosquitto, so it
runs on a bare Windows box. It proves the wiring and the payload contracts; it
does NOT prove Postgres-specific SQL. Run the real stack for that.

    pip install -r backend/requirements-dev.txt
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_test.py
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
PY = sys.executable
DB = os.path.join(BACKEND, "_smoke.db")
BASE = "http://127.0.0.1:8123"
RUN_S = 25  # fake_sensor --deauth waits 10s before flooding

failures: list[str] = []
children: list[subprocess.Popen] = []


def reap() -> None:
    """Kill every child we started. Windows keeps the SQLite file locked until
    the process exits, so a stray uvicorn breaks the next run."""
    for p in children:
        if p.poll() is None:
            p.terminate()
    for p in children:
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
    children.clear()


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + label + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def http(method: str, path: str, body=None, timeout: float = 5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def run_broker(config, ready, state) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    broker = None

    async def boot():
        # Broker() grabs the running loop in __init__, so it must be built here.
        from amqtt.broker import Broker
        b = Broker(config)
        await b.start()
        return b

    try:
        broker = loop.run_until_complete(boot())
        state["ok"] = True
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        ready.set()
    if broker is None:
        return
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(broker.shutdown())
        loop.close()


async def main() -> int:
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        import amqtt.broker  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        print("Missing dev deps. Run:\n"
              "    backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements-dev.txt")
        return 2

    if os.path.exists(DB):
        os.remove(DB)

    ready, state = asyncio.Event(), {}
    threading.Thread(target=run_broker, args=({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:1883"}},
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    }, ready, state), daemon=True).start()
    while not ready.is_set():
        await asyncio.sleep(0.05)
    if not state.get("ok"):
        check("broker up", False)
        return 1
    check("broker: amqtt on 127.0.0.1:1883", True)

    env = dict(os.environ, DATABASE_URL=f"sqlite:///{DB}",
               MQTT_HOST="127.0.0.1", MQTT_PORT="1883", PORT="8123")

    log_path = os.path.join(REPO, "_smoke_server.log")
    with open(log_path, "w+", encoding="utf-8") as logf:
        api = subprocess.Popen([PY, "run.py"], cwd=BACKEND, env=env,
                               stdout=logf, stderr=subprocess.STDOUT)
        children.append(api)

        up = False
        for _ in range(60):
            await asyncio.sleep(0.5)
            try:
                if http("GET", "/health", timeout=2)[0] == 200:
                    up = True
                    break
            except (urllib.error.URLError, OSError):
                pass
        if not up:
            logf.seek(0)
            check("backend serving on :8123", False, logf.read()[-1500:])
            return 1
        check("backend serving on :8123 (real uvicorn, real HTTP)", True)

        st, s1 = http("POST", "/sensors", {"sensor_id": "smoke-01", "name": "Front",
                                           "location": "Cafe", "channels": [1, 6, 11]})
        check("POST /sensors -> 201", st == 201, f"status={st}")
        check("new sensor starts offline", s1["status"] == "offline")
        check("duplicate POST /sensors -> 409",
              http("POST", "/sensors", {"sensor_id": "smoke-01"})[0] == 409)
        st, patched = http("PATCH", "/sensors/smoke-01", {"name": "Front door"})
        check("PATCH /sensors/{id} keeps untouched fields",
              st == 200 and patched["name"] == "Front door" and patched["channels"] == [1, 6, 11],
              str(patched))

        pushed: list[dict] = []
        pushed_alerts: list[dict] = []

        async def listen(url: str, sink: list[dict]) -> None:
            try:
                async with websockets.connect(BASE.replace("http", "ws") + url) as ws:
                    end = time.monotonic() + RUN_S
                    while time.monotonic() < end:
                        try:
                            sink.append(json.loads(await asyncio.wait_for(ws.recv(), 0.5)))
                        except asyncio.TimeoutError:
                            pass
            except Exception as exc:
                print(f"      {url} client stopped: {type(exc).__name__}: {exc}")

        ws_frames = asyncio.create_task(listen("/ws/frames", pushed))
        ws_alerts = asyncio.create_task(listen("/ws/alerts", pushed_alerts))

        det = subprocess.Popen([PY, "main.py"], cwd=os.path.join(REPO, "detection"), env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        children.append(det)
        await asyncio.sleep(2)  # let detection subscribe before frames start flowing

        sen = subprocess.Popen([PY, os.path.join(REPO, "scripts", "fake_sensor.py"),
                                "--deauth", "--host", "127.0.0.1", "--sensor", "smoke-01"],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        children.append(sen)
        print(f"      sensor + detection running, waiting {RUN_S}s...")
        await asyncio.sleep(RUN_S)  # fixed sleep: a dead WS client must not truncate the run
        ws_frames.cancel()
        ws_alerts.cancel()

        st, frames = http("GET", "/frames/recent?limit=50")
        check("frames ingested and served over real HTTP", st == 200 and len(frames) > 0,
              f"count={len(frames)}")
        if frames:
            f = frames[0]
            check("MAC normalized to upper colon form",
                  bool(re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", f["src_mac"])), f["src_mac"])
            check("SSID captured from the air", f["ssid"] == "CafeWiFi", str(f["ssid"]))
            check("deauth frames present", any(x["frame_type"] == "deauth" for x in frames))
            check("received_at is JSON-safe string", isinstance(f["received_at"], str),
                  f["received_at"])

        st, s2 = http("GET", "/sensors/smoke-01")
        check("ingest flips registered sensor online", s2["status"] == "online", s2["status"])
        check("last_seen_at is fresh", bool(s2["last_seen_at"]), str(s2["last_seen_at"]))
        check("registered metadata survives ingest", s2["name"] == "Front door", str(s2["name"]))

        st, filt = http("GET", "/frames/recent?frame_type=beacon&limit=5")
        check("frame_type filter works", st == 200 and all(x["frame_type"] == "beacon" for x in filt),
              f"n={len(filt)}")

        check("WS /ws/frames pushed live frames", len(pushed) > 0, f"pushed={len(pushed)}")
        if pushed:
            check("WS payload matches REST shape",
                  {"id", "sensor_id", "received_at", "frame_type"} <= set(pushed[0]),
                  str(sorted(pushed[0]))[:80])

        # --- F-4: detection event -> alert, over the same real processes ---
        st, events = http("GET", "/events")
        check("detection events ingested into the backend", st == 200 and len(events) > 0,
              f"n={len(events) if events else 0}")
        st, alerts = http("GET", "/alerts")
        check("alerts generated from those events", st == 200 and len(alerts) > 0,
              f"n={len(alerts) if alerts else 0}")
        if alerts:
            a = alerts[0]
            check("alert explanation is non-empty plain language",
                  bool(a["explanation"]) and bool(a["recommended_action"]))
            check("alert starts with status new", a["status"] == "new", a["status"])
            st, acked = http("PATCH", f"/alerts/{a['alert_id']}", {"status": "acknowledged"})
            check("PATCH /alerts/{id} -> acknowledged", st == 200 and acked["status"] == "acknowledged",
                  f"{st}")
            st, _ = http("PATCH", f"/alerts/{a['alert_id']}", {"status": "new"})
            check("PATCH rejects transition back to new (422)", st == 422, f"got {st}")
        check("WS /ws/alerts pushed live alerts", len(pushed_alerts) > 0,
              f"pushed={len(pushed_alerts)}")
        if pushed_alerts:
            check("alert push matches REST shape",
                  {"alert_id", "event_id", "severity", "title", "status"}
                  <= set(pushed_alerts[0]), str(sorted(pushed_alerts[0]))[:80])

    return 1 if failures else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        reap()
        for _ in range(20):
            if not os.path.exists(DB):
                break
            time.sleep(0.25)
        if os.path.exists(DB):
            try:
                os.remove(DB)
            except OSError:
                pass
        print(f"\nserver log: {os.path.join(REPO, '_smoke_server.log')}")
    print("ALL PASS" if not code else f"{len(failures)} FAILED: {failures}")
    sys.exit(code)