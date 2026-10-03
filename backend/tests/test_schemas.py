"""Schema validation and MAC normalization -- the sensor-facing contract.

These are the checks that protect every other team: a frame that validates here
is a frame the backend will store, and a MAC that normalizes here is a MAC the
dashboard can compare as a string.
"""

import pytest
from pydantic import ValidationError

from app.schemas import DetectionEvent, FrameBatch, WiFiFrame

GOOD_FRAME = {
    "uptime_ms": 1234,
    "timestamp": None,
    "channel": 6,
    "frame_type": "beacon",
    "src_mac": "aa:bb:cc:dd:ee:ff",
    "dst_mac": "11:22:33:44:55:66",
    "bssid": "aa:bb:cc:dd:ee:ff",
    "ssid": "CafeWiFi",
    "rssi": -42,
    "seq_num": 7,
}


def batch(**overrides):
    payload = {"sensor_id": "sensor-1", "batch_seq": 1, "frames": [dict(GOOD_FRAME)]}
    payload.update(overrides)
    return payload


# --- MAC normalization -----------------------------------------------------
# The spec says AA:BB:CC:DD:EE:FF, upper-case, colon-separated, done in the
# validator so no caller can skip it.


@pytest.mark.parametrize(
    "raw",
    [
        "aa:bb:cc:dd:ee:ff",
        "AA:BB:CC:DD:EE:FF",
        "aa-bb-cc-dd-ee-ff",
        "aabbccddeeff",
        "AA:BB:CC:DD:EE-ff",
        "aAbBcCdDeEfF",
    ],
)
def test_mac_normalizes_to_canonical_form(raw):
    frame = WiFiFrame(**{**GOOD_FRAME, "src_mac": raw})
    assert frame.src_mac == "AA:BB:CC:DD:EE:FF"


def test_bssid_is_normalized_too():
    frame = WiFiFrame(**{**GOOD_FRAME, "bssid": "de:ad:be:ef:00:01"})
    assert frame.bssid == "DE:AD:BE:EF:00:01"


def test_bssid_may_be_absent():
    assert WiFiFrame(**{**GOOD_FRAME, "bssid": None}).bssid is None


@pytest.mark.parametrize("raw", ["", "not-a-mac", "aa:bb:cc:dd:ee", "zz:bb:cc:dd:ee:ff"])
def test_invalid_mac_rejected(raw):
    with pytest.raises(ValidationError):
        WiFiFrame(**{**GOOD_FRAME, "src_mac": raw})


# --- FrameBatch bounds -----------------------------------------------------


def test_valid_batch_parses():
    parsed = FrameBatch.model_validate(batch())
    assert parsed.sensor_id == "sensor-1"
    assert len(parsed.frames) == 1


def test_empty_frame_list_rejected():
    with pytest.raises(ValidationError):
        FrameBatch.model_validate(batch(frames=[]))


def test_more_than_200_frames_rejected():
    with pytest.raises(ValidationError):
        FrameBatch.model_validate(batch(frames=[dict(GOOD_FRAME) for _ in range(201)]))


def test_exactly_200_frames_accepted():
    assert len(FrameBatch.model_validate(batch(frames=[dict(GOOD_FRAME)] * 200)).frames) == 200


def test_sensor_id_length_bounded():
    assert FrameBatch.model_validate(batch(sensor_id="x" * 64)).sensor_id
    with pytest.raises(ValidationError):
        FrameBatch.model_validate(batch(sensor_id="x" * 65))


@pytest.mark.parametrize("channel", [0, 15, -1])
def test_channel_out_of_range_rejected(channel):
    with pytest.raises(ValidationError):
        WiFiFrame(**{**GOOD_FRAME, "channel": channel})


@pytest.mark.parametrize("channel", [1, 6, 14])
def test_channel_boundaries_accepted(channel):
    assert WiFiFrame(**{**GOOD_FRAME, "channel": channel}).channel == channel


@pytest.mark.parametrize("rssi", [1, -129])
def test_rssi_out_of_range_rejected(rssi):
    with pytest.raises(ValidationError):
        WiFiFrame(**{**GOOD_FRAME, "rssi": rssi})


@pytest.mark.parametrize("seq_num", [-1, 4096])
def test_seq_num_out_of_range_rejected(seq_num):
    with pytest.raises(ValidationError):
        WiFiFrame(**{**GOOD_FRAME, "seq_num": seq_num})


def test_unknown_frame_type_rejected():
    with pytest.raises(ValidationError):
        WiFiFrame(**{**GOOD_FRAME, "frame_type": "wormhole"})


def test_optional_fields_default_to_none():
    frame = WiFiFrame(**{**GOOD_FRAME, "uptime_ms": None, "timestamp": None, "seq_num": None})
    assert (frame.uptime_ms, frame.timestamp, frame.seq_num) == (None, None, None)


# --- DetectionEvent, the detection engine -> backend contract --------------


def event(**overrides):
    from datetime import datetime, timezone

    payload = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "deauth_flood",
        "detected_at": datetime.now(timezone.utc),
        "severity": 8,
        "confidence": 0.9,
        "sensor_ids": ["sensor-1"],
        "details": {},
    }
    payload.update(overrides)
    return payload


def test_valid_event_parses():
    assert DetectionEvent.model_validate(event()).event_type == "deauth_flood"


@pytest.mark.parametrize("severity", [0, 11])
def test_event_severity_bounded(severity):
    with pytest.raises(ValidationError):
        DetectionEvent.model_validate(event(severity=severity))


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_event_confidence_bounded(confidence):
    with pytest.raises(ValidationError):
        DetectionEvent.model_validate(event(confidence=confidence))


def test_unknown_event_type_rejected():
    with pytest.raises(ValidationError):
        DetectionEvent.model_validate(event(event_type="meteor"))


def test_details_may_be_any_rule_specific_dict():
    parsed = DetectionEvent.model_validate(event(details={"src_mac": "AA:BB:CC:DD:EE:FF", "rate_per_sec": 63}))
    assert parsed.details["rate_per_sec"] == 63
