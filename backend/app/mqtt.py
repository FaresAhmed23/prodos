import asyncio
import logging
from datetime import datetime, timedelta

import aiomqtt
from sqlalchemy import update

from .config import settings
from .database import SessionLocal
from .models import Frame, Sensor, utcnow
from .schemas import FrameBatch, FrameOut

log = logging.getLogger(__name__)

SENSOR_OFFLINE_AFTER_S = 60
SENSOR_PRESENCE_INTERVAL_S = 15


class Broadcaster:
    """Fan-out to WebSocket clients. Slow clients are dropped, never awaited."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()

    def subscribe(self) -> "asyncio.Queue[dict]":
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[dict]") -> None:
        self._subscribers.discard(queue)

    async def publish(self, message: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("dropping slow websocket subscriber")
                self._subscribers.discard(queue)


frames_broadcaster = Broadcaster()


def _store_batch(sensor_id: str, frames: list[Frame], seen_at: datetime) -> None:
    with SessionLocal() as session:
        session.add_all(frames)
        sensor = session.get(Sensor, sensor_id)
        if sensor is None:
            session.add(
                Sensor(sensor_id=sensor_id, status="online", last_seen_at=seen_at, channels=[])
            )
        elif sensor.status != "retired":
            sensor.status = "online"
            sensor.last_seen_at = seen_at
        session.commit()


async def _handle_message(topic: str, payload: bytes) -> None:
    batch = FrameBatch.model_validate_json(payload)
    seen_at = utcnow()
    rows = [
        Frame(
            sensor_id=batch.sensor_id,
            received_at=seen_at,
            batch_seq=batch.batch_seq,
            **frame.model_dump(),
        )
        for frame in batch.frames
    ]
    await asyncio.to_thread(_store_batch, batch.sensor_id, rows, seen_at)

    for row in rows:
        # Build the broadcast payload through FrameOut, not a hand-rolled dict:
        # a raw datetime here is not JSON-serializable, so send_json raised
        # TypeError and killed every live stream on the first frame. This also
        # guarantees /ws/frames and /frames/recent emit identical JSON.
        await frames_broadcaster.publish(FrameOut.model_validate(row).model_dump(mode="json"))


def _expire_sensors(cutoff: datetime) -> None:
    with SessionLocal() as session:
        session.execute(
            update(Sensor)
            .where(Sensor.status == "online", Sensor.last_seen_at < cutoff)
            .values(status="offline")
        )
        session.commit()


async def mqtt_ingest_loop() -> None:
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                log.info("mqtt connected: %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.subscribe(settings.mqtt_topic_frames)
                async for message in client.messages:
                    await _handle_message(str(message.topic), message.payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("mqtt ingest failed; reconnecting in 5s")
            await asyncio.sleep(5)


async def sensor_presence_loop() -> None:
    while True:
        await asyncio.sleep(SENSOR_PRESENCE_INTERVAL_S)
        try:
            cutoff = utcnow() - timedelta(seconds=SENSOR_OFFLINE_AFTER_S)
            await asyncio.to_thread(_expire_sensors, cutoff)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sensor presence sweep failed")