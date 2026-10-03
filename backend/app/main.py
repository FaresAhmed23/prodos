import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .mqtt import (
    alerts_broadcaster,
    events_ingest_loop,
    frames_broadcaster,
    mqtt_ingest_loop,
    sensor_presence_loop,
)
from .retention import retention_loop
from .routers import alerts, events, frames, sensors

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def run_migrations() -> None:
    """Bring the schema to head. Replaces `Base.metadata.create_all` (F-9).

    create_all could not express "add a column" or "rename a table" — it only
    ever creates what is missing, so any change to a model silently did nothing
    to an existing database and only showed up as a crash in production. Alembic
    records each change as an ordered, reversible revision.

    Both paths are made absolute so this works regardless of the working
    directory: the Docker image runs with WORKDIR /app, but a caller invoking it
    from anywhere must not get a different database.
    """
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(root))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    tasks = [
        asyncio.create_task(mqtt_ingest_loop()),
        asyncio.create_task(events_ingest_loop()),
        asyncio.create_task(sensor_presence_loop()),
        asyncio.create_task(retention_loop()),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Prodos API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(frames.router)
app.include_router(sensors.router)
app.include_router(events.router)
app.include_router(alerts.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/frames")
async def ws_frames(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = frames_broadcaster.subscribe()
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        frames_broadcaster.unsubscribe(queue)


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = alerts_broadcaster.subscribe()
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        alerts_broadcaster.unsubscribe(queue)