from schemas import DetectionEvent, WiFiFrame


class Detector:
    """Template that every detector follows."""

    def process_batch(
        self, sensor_id: str, frames: list[WiFiFrame]
    ) -> list[DetectionEvent]:
        """Look at a batch of frames and return any events found."""
        return []