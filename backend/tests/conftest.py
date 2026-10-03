"""Shared fixtures. No broker, no network, no Postgres.

Two deliberate choices:

* Routers are mounted on a bare FastAPI app instead of importing `app.main`.
  The real app's lifespan opens an MQTT connection and spawns ingest tasks, which
  is exactly what these tests must not do. Every route is still the real one,
  with the real dependency override for the session.

* The stub LLM is a real loopback HTTP server rather than a mocked `httpx.post`.
  That costs one socket on 127.0.0.1 but actually exercises URL construction, the
  Authorization header and the response parser. A mock would pass while the
  request was malformed. It binds port 0, so no fixed port to collide on.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Must happen before app.config is imported: a developer with LLM_API_KEY exported
# in their shell would otherwise get LLMProvider in tests that assume the floor.
for _var in ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL"):
    os.environ.pop(_var, None)
os.environ["DATABASE_URL"] = "sqlite://"  # nothing should ever connect to this

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, get_db  # noqa: E402
from app.routers import alerts as alerts_router  # noqa: E402
from app.routers import events as events_router  # noqa: E402
from app.routers import frames as frames_router  # noqa: E402
from app.routers import sensors as sensors_router  # noqa: E402


@pytest.fixture
def engine():
    # StaticPool + check_same_thread=False is what makes "sqlite://" shared across
    # the test's threads instead of being a fresh empty database per connection.
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def client(session):
    app = FastAPI()
    for module in (frames_router, sensors_router, events_router, alerts_router):
        app.include_router(module.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def alerts_on_test_db(monkeypatch, session_factory):
    """Point app.alerts at the test database.

    `handle_detection_event` opens its own session via `alerts.SessionLocal`, so
    without this the alert pipeline would write to the real configured database.
    """
    from app import alerts

    monkeypatch.setattr(alerts, "SessionLocal", session_factory)
    return alerts


@pytest.fixture
def stub_llm():
    """An OpenAI-compatible /chat/completions server on an ephemeral port."""
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            received.append({"body": body, "auth": self.headers.get("Authorization")})
            content = {
                "title": "STUB TITLE",
                "explanation": "STUB BODY.",
                "recommended_action": "STUB ACTION.",
            }
            out = json.dumps(
                {"choices": [{"message": {"content": json.dumps(content)}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield {"base": f"http://127.0.0.1:{server.server_port}/v1", "received": received}
    finally:
        server.shutdown()
        server.server_close()
