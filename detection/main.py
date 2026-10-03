"""Prodos detection engine.

Owned by Omar Ahmed Fathy and Mohamed Zaki Ibrahim from hand-off.
Fares created this skeleton for task F-3 and does not modify it after that.
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

import aiomqtt

from schemas import DetectionEvent, FrameBatch, WiFiFrame

log = logging.getLogger(__name__)

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC_FRAMES = os.environ.get("TOPIC_FRAMES", "prodos/sensors/+/frames")
TOPIC_EVENTS = os.environ.get("TOPIC_EVENTS", "prodos/events")

DEAUTH_WINDOW_S = 10.0
DEAUTH_THRESHOLD = 30


class Detector:
    """Base class 7. Subclass and register in DETECTORS to add a rule."""
    """Mohamed is a nigga"""

    def process_batch(self, sensor_id: str, frames: list[WiFiFrame]) -> list[DetectionEvent]:
        raise NotImplementedError


class DemoDeauthDetector(Detector):
    """Fires deauth_flood when one src_mac sends DEAUTH_THRESHOLD+ deauths
    inside a DEAUTH_WINDOW_S sliding window.

    Replace this with the real M1 rule (AGENTS.md milestone M1). Kept
    deliberately simple so the hand-off has something runnable.
    """

    def __init__(self, window_s: float = DEAUTH_WINDOW_S, threshold: int = DEAUTH_THRESHOLD):
        self.window_s = window_s
        self.threshold = threshold
        self._deauths: dict[str, deque[tuple[float, WiFiFrame]]] = defaultdict(deque)

    def process_batch(self, sensor_id: str, frames: list[WiFiFrame]) -> list[DetectionEvent]:
        now = time.monotonic()
        events: list[DetectionEvent] = []

        for frame in frames:
            if frame.frame_type in ("deauth", "disassoc"):
                self._deauths[frame.src_mac].append((now, frame))

        for src_mac, window in list(self._deauths.items()):
            while window and now - window[0][0] > self.window_s:
                window.popleft()

            if len(window) < self.threshold:
                continue

            count = len(window)
            rate = count / self.window_s
            events.append(
                DetectionEvent(
                    event_id=str(uuid.uuid4()),
                    event_type="deauth_flood",
                    detected_at=datetime.now(timezone.utc),
                    # TODO(detection team): placeholder severity, real model is M2.
                    severity=min(10, max(1, 1 + count // 10)),
                    confidence=min(1.0, count / (self.threshold * 2)),
                    sensor_ids=[sensor_id],
                    details={
                        "src_mac": src_mac,
                        "rate_per_sec": round(rate, 2),
                        "window_s": int(self.window_s),
                        "count": count,
                    },
                )
            )
            # Clear so one burst yields one event instead of one per batch.
            window.clear()

        return events


DETECTORS: list[Detector] = [DemoDeauthDetector()]


async def run() -> None:
    while True:
        try:
            async with aiomqtt.Client(MQTT_HOST, MQTT_PORT) as client:
                log.info("subscribed to %s on %s:%s", TOPIC_FRAMES, MQTT_HOST, MQTT_PORT)
                await client.subscribe(TOPIC_FRAMES)
                async for message in client.messages:
                    try:
                        batch = FrameBatch.model_validate_json(message.payload)
                    except Exception:
                        log.warning("dropping invalid batch on %s", message.topic)
                        continue

                    for detector in DETECTORS:
                        for event in detector.process_batch(batch.sensor_id, batch.frames):
                            await client.publish(TOPIC_EVENTS, event.model_dump_json())
                            log.info("published %s %s", event.event_type, event.event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("detection loop failed; reconnecting in 5s")
            await asyncio.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # aiomqtt drives its socket through add_reader/add_writer, which Windows'
    # default ProactorEventLoop does not implement -- the subscribe would just
    # time out. Must be set before asyncio.run builds the loop.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("stopping")


if __name__ == "__main__":
    main()