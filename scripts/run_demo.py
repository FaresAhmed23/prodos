"""One-command demo harness: broker -> backend -> detection -> sensor -> dashboard.

    python scripts/run_demo.py                  # deauth flood, 10s after sensor boot
    python scripts/run_demo.py --scenario both  # deauth flood + evil-twin beacon
    python scripts/run_demo.py --scenario idle  # normal traffic, no simulated attack
    python scripts/run_demo.py --no-frontend    # pipeline only, no Vite
    python scripts/run_demo.py --keep           # reuse the previous _demo.db

Ctrl+C stops every child. No Docker: the broker is amqtt inside this process,
the same engine scripts/smoke_test.py uses. Everything else is the real thing --
real uvicorn, real detection engine, real fake sensor, real Vite dev server --
talking over MQTT and HTTP the way the team runs the stack.

Demo database: backend/_demo.db (SQLite), wiped at start unless --keep.
Owner endpoints are deliberately open (ADMIN_API_KEY="") so the dashboard needs
no key. Runbook: docs/plans/demo.md
"""

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
DETECTION = os.path.join(REPO, "detection")
FRONTEND = os.path.join(REPO, "frontend")
SENSOR_SCRIPT = os.path.join(REPO, "scripts", "fake_sensor.py")
PY = sys.executable
DB = os.path.join(BACKEND, "_demo.db")
BASE = "http://127.0.0.1:8000"

SITE = "demo-cafe"
SENSOR = "sensor-01"

# The demo seeds the same eight questions the backend scores, so the keys
# cannot drift from scoring/config.py. That module is constants only.
sys.path.insert(0, BACKEND)
from app.scoring.config import CHECKLIST_QUESTIONS

children: list[subprocess.Popen] = []


def pump(name: str, stream) -> None:
    for line in iter(stream.readline, ""):
        line = line.rstrip()
        if line:
            print(f"[{name}] {line}", flush=True)


def spawn(name: str, args: list[str], cwd: str, env: dict) -> subprocess.Popen:
    print(f"  starting {name}", flush=True)
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    threading.Thread(target=pump, args=(name, proc.stdout), daemon=True).start()
    children.append(proc)
    return proc


def stop(proc: subprocess.Popen) -> None:
    """Kill a child and its children. `npm run dev` is a cmd.exe wrapper around
    node, so /T is what actually frees port 5173."""
    if proc not in children:
        return
    children.remove(proc)
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def reap() -> None:
    for proc in list(children):
        stop(proc)


def http(method: str, path: str, body=None, timeout: float = 5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None)


def broker_thread(config: dict, ready: threading.Event, state: dict) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    broker = None

    async def boot():
        # Broker() grabs the running loop in __init__, so it must be built here.
        from amqtt.broker import Broker

        instance = Broker(config)
        await instance.start()
        return instance

    try:
        broker = loop.run_until_complete(boot())
        state["ok"] = True
    except Exception:
        state["error"] = traceback.format_exc()
    finally:
        ready.set()
    if broker is None:
        return
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(broker.shutdown())
        loop.close()


async def wait_health(tries: int = 60) -> bool:
    for _ in range(tries):
        await asyncio.sleep(0.5)
        try:
            if http("GET", "/health", timeout=2)[0] == 200:
                return True
        except Exception:
            pass
    return False


def seed() -> str | None:
    """Create the demo shop through the REST surface, never by writing SQL."""
    site = {
        "site_id": SITE,
        "business_name": "Demo Cafe",
        "business_type": "cafe",
        "wifi_ssids": ["CafeWiFi"],
        "known_access_points": [
            "AA:BB:CC:00:00:01",
            "AA:BB:CC:00:00:02",
            "AA:BB:CC:00:00:03",
        ],
        "router_model": "Demo router",
        "primary_language": "en",
        "notes": "Seeded by scripts/run_demo.py",
    }
    status, _ = http("POST", "/sites", site)
    if status not in (201, 409):  # 409 = --keep, the previous run's site
        print(f"  seed: POST /sites -> {status}")

    status, _ = http(
        "POST",
        "/sensors",
        {
            "sensor_id": SENSOR,
            "name": "Front counter",
            "location": "Counter",
            "channels": [1, 6, 11],
        },
    )
    if status not in (201, 409):
        print(f"  seed: POST /sensors -> {status}")

    status, _ = http("PATCH", f"/sites/{SITE}/sensors/{SENSOR}", {})
    if status != 200:
        print(f"  seed: assign sensor -> {status}")

    answers = {key: True for key in CHECKLIST_QUESTIONS}
    status, body = http("PUT", f"/sites/{SITE}/checklist", {"answers": answers})
    if status != 200:
        print(f"  seed: PUT checklist -> {status} {body}")

    status, body = http("POST", f"/sites/{SITE}/trust", {})
    if status != 200:
        print(f"  seed: POST trust -> {status}")
        return None
    return body["trust_token"]


def banner(token: str | None, frontend: bool, scenario: str) -> None:
    attack = {
        "deauth": "deauth flood from 11:22:33:44:55:66 starts 10s after sensor boot",
        "evil-twin": "CafeWiFi clone at 15s (frames only: no detector rule yet)",
        "both": "deauth flood at 10s; CafeWiFi clone at 15s (clone: frames only)",
        "idle": "normal beacon traffic only; no simulated attack",
    }[scenario]

    print()
    print("=" * 70)
    print("  PRODOS demo is running")
    print("-" * 70)
    if frontend:
        print("  Dashboard     http://localhost:5173")
    print("  API docs      http://127.0.0.1:8000/docs")
    if token:
        print(f"  Trust page    {BASE}/trust/{token}")
        print(f"  QR image      {BASE}/trust/{token}/qr.png")
    print("-" * 70)
    print(f"  site {SITE} | sensor {SENSOR} | ADMIN_API_KEY unset, owner views open")
    print(f"  {attack}")
    print("  Ctrl+C stops everything")
    print("=" * 70, flush=True)


async def main(args) -> int:
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        import amqtt.broker  # noqa: F401
    except ImportError:
        print(
            "Missing amqtt. Run:\n"
            "    backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements-dev.txt"
        )
        return 2

    if not args.keep and os.path.exists(DB):
        try:
            os.remove(DB)
        except OSError:
            print(
                f"Cannot delete {DB} - a backend still holds it.\n"
                "Stop stray processes first: Stop-Process -Name python -Force"
            )
            return 1

    try:
        http("GET", "/health", timeout=1)
    except Exception:
        pass
    else:
        print(
            "Something already answers on :8000, so this demo would talk to it.\n"
            "Stop it first: Stop-Process -Name python -Force"
        )
        return 1

    try:
        with socket.create_connection(("127.0.0.1", 1883), timeout=0.5):
            external = True
    except OSError:
        external = False

    if external:
        # The dev stack usually has mosquitto in Docker on 1883 already.
        print("  broker: reusing what already listens on 127.0.0.1:1883")
    else:
        ready = threading.Event()
        state: dict = {}
        threading.Thread(
            target=broker_thread,
            daemon=True,
            args=(
                {
                    "listeners": {
                        "default": {"type": "tcp", "bind": "127.0.0.1:1883"}
                    },
                    "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
                    "topic-check": {"enabled": False},
                },
                ready,
                state,
            ),
        ).start()
        ready.wait(10)
        if not state.get("ok"):
            print(state.get("error", "broker did not start"))
            return 1
        print("  broker: amqtt inside this process on 127.0.0.1:1883")

    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{DB}",
        MQTT_HOST="127.0.0.1",
        MQTT_PORT="1883",
        PORT="8000",
        ADMIN_API_KEY="",
        PYTHONUNBUFFERED="1",
    )

    api = spawn("backend", [PY, "run.py"], BACKEND, env)
    if not await wait_health():
        print("Backend did not come up; its log lines above say why.")
        return 1

    token = seed()

    spawn("detection", [PY, "main.py"], DETECTION, env)
    await asyncio.sleep(1.5)  # let detection subscribe before frames flow

    flags = {
        "deauth": ["--deauth"],
        "evil-twin": ["--evil-twin"],
        "both": ["--deauth", "--evil-twin"],
        "idle": [],
    }[args.scenario]
    spawn(
        "sensor",
        [PY, SENSOR_SCRIPT, "--host", "127.0.0.1", "--sensor", SENSOR, *flags],
        REPO,
        env,
    )

    # Frame data must exist before the score snapshot, or network hygiene
    # scores 0 and the Score view looks broken on a working stack.
    frames_seen = False
    for _ in range(30):
        await asyncio.sleep(0.5)
        try:
            status, recent = http("GET", "/frames/recent?limit=5", timeout=2)
            if status == 200 and recent:
                frames_seen = True
                break
        except Exception:
            pass
    if not frames_seen:
        print("  warning: no frames reached the backend; score hygiene will read 0")

    # score_loop runs once at startup and then daily, so a site created after
    # boot has no snapshot until the next sweep. One restart covers it.
    print("  bouncing the backend so score_loop writes a snapshot")
    stop(api)
    api = spawn("backend", [PY, "run.py"], BACKEND, env)
    if not await wait_health():
        print("Backend did not come back after the restart.")
        return 1

    status, score = http("GET", f"/sites/{SITE}/score")
    if status == 200:
        print(f"  score: {score['score']} ({score['band']})")
    else:
        print(f"  warning: GET /sites/{SITE}/score -> {status}; Score view stays empty")

    frontend = False
    if not args.no_frontend:
        npm = shutil.which("npm")
        if npm is None:
            print("  frontend skipped: npm is not on PATH")
        elif not os.path.isdir(os.path.join(FRONTEND, "node_modules")):
            print("  frontend skipped: run `npm install` in frontend/ first")
        else:
            npm_args = (
                ["cmd", "/c", "npm", "run", "dev"]
                if os.name == "nt"
                else [npm, "run", "dev"]
            )
            spawn("frontend", npm_args, FRONTEND, env)
            frontend = True

    banner(token, frontend, args.scenario)

    # Stay alive until Ctrl+C. A dying child is visible in its prefixed log
    # lines; tearing the whole demo down on one failure would hide the cause.
    await asyncio.Event().wait()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="One command: broker, backend, detection, fake sensor, dashboard."
    )
    parser.add_argument(
        "--scenario",
        choices=["deauth", "evil-twin", "both", "idle"],
        default="deauth",
        help="which simulated attack the fake sensor runs (default: deauth)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the previous run's backend/_demo.db instead of wiping it",
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="do not start the Vite dev server",
    )
    args = parser.parse_args()

    code = 1
    try:
        code = asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nStopping...")
        code = 0
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        reap()
        print(f"demo database: {DB}")
        print("next run wipes it unless you pass --keep")
    sys.exit(code)
