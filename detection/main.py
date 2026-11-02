import asyncio
import logging
import sys

import aiomqtt
from pydantic import ValidationError

from detectors.deauth import DeauthDetector
from schemas import FrameBatch

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_FRAMES = "prodos/sensors/+/frames"
TOPIC_EVENTS = "prodos/events"

log = logging.getLogger("detection")

DETECTORS = [DeauthDetector()]


async def run() -> None:
    """Connect to the broker, read frame batches, publish events."""
    async with aiomqtt.Client(BROKER_HOST, BROKER_PORT) as client:
        await client.subscribe(TOPIC_FRAMES)
        log.info("Connected. Listening on %s", TOPIC_FRAMES)

        async for message in client.messages:
            try:
                batch = FrameBatch.model_validate_json(message.payload)
            except ValidationError as error:
                log.warning("Ignoring a bad batch: %s", error)
                continue

            for detector in DETECTORS:
                try:
                    events = detector.process_batch(batch.sensor_id, batch.frames)
                except Exception:
                    log.exception("Detector %s crashed", type(detector).__name__)
                    continue

                for event in events:
                    await client.publish(
                        TOPIC_EVENTS, event.model_dump_json(), qos=1
                    )
                    log.info(
                        "Event sent: %s (severity %s)",
                        event.event_type,
                        event.severity,
                    )


async def main() -> None:
    """Keep running, and reconnect if the broker connection drops."""
    while True:
        try:
            await run()
        except aiomqtt.MqttError as error:
            log.warning("Broker connection lost (%s). Retrying in 5s.", error)
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped.")