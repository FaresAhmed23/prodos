import time
import uuid
from datetime import datetime, timezone

from detectors.base import Detector
from schemas import DetectionEvent, WiFiFrame


class DeauthDetector(Detector):
    """Raises an event when one sender sends too many deauth frames."""

    def __init__(self, threshold: int = 30, window_s: int = 10):
        self.threshold = threshold
        self.window_s = window_s
        self.recent: dict[str, list[float]] = {}
        self.alerted: set[str] = set()

    def process_batch(
        self, sensor_id: str, frames: list[WiFiFrame]
    ) -> list[DetectionEvent]:
        now = time.monotonic()
        events: list[DetectionEvent] = []
        for frame in frames:
            if frame.frame_type != "deauth":
                continue
            times = self.recent.setdefault(frame.src_mac, [])
            times.append(now)
            while times and now - times[0] > self.window_s:
                times.pop(0)

            count = len(times)
            if count >= self.threshold:
                if frame.src_mac not in self.alerted:
                    self.alerted.add(frame.src_mac)
                    events.append(
                        DetectionEvent(
                            event_id=str(uuid.uuid4()),
                            event_type="deauth_flood",
                            detected_at=datetime.now(timezone.utc),
                            severity=min(10, 5 + count // self.threshold),
                            confidence=0.9,
                            sensor_ids=[sensor_id],
                            details={
                                "src_mac": frame.src_mac,
                                "rate_per_sec": round(count / self.window_s),
                                "window_s": self.window_s,
                            },
                        )
                    )
            else:
                self.alerted.discard(frame.src_mac)
        return events