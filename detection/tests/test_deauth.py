from detectors.deauth import DeauthDetector
from schemas import WiFiFrame


def make_frame(frame_type: str, src_mac: str) -> WiFiFrame:
    """Build one fake WiFi frame for testing."""
    return WiFiFrame(
        channel=6,
        frame_type=frame_type,
        src_mac=src_mac,
        dst_mac="FF:FF:FF:FF:FF:FF",
        bssid=src_mac,
        rssi=-50,
    )


ATTACKER = "AA:BB:CC:DD:EE:01"
OTHER = "AA:BB:CC:DD:EE:02"


def test_flood_raises_event():
    detector = DeauthDetector()
    frames = [make_frame("deauth", ATTACKER) for _ in range(30)]
    events = detector.process_batch("sensor-1", frames)
    assert len(events) == 1
    assert events[0].event_type == "deauth_flood"
    assert events[0].details["src_mac"] == ATTACKER


def test_few_deauth_frames_are_normal():
    detector = DeauthDetector()
    frames = [make_frame("deauth", ATTACKER) for _ in range(5)]
    assert detector.process_batch("sensor-1", frames) == []


def test_other_frame_types_are_ignored():
    detector = DeauthDetector()
    frames = [make_frame("beacon", ATTACKER) for _ in range(100)]
    assert detector.process_batch("sensor-1", frames) == []


def test_one_flood_gives_one_event():
    detector = DeauthDetector()
    frames = [make_frame("deauth", ATTACKER) for _ in range(60)]
    events = detector.process_batch("sensor-1", frames)
    assert len(events) == 1


def test_senders_are_counted_separately():
    detector = DeauthDetector()
    frames = [make_frame("deauth", ATTACKER) for _ in range(20)]
    frames += [make_frame("deauth", OTHER) for _ in range(20)]
    assert detector.process_batch("sensor-1", frames) == []