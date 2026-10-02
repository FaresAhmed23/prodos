# CONTRACT — must stay in sync

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FrameType = Literal["beacon", "probe_req", "probe_resp", "deauth", "disassoc", "other"]
EventType = Literal["evil_twin", "rogue_ap", "deauth_flood", "anomaly"]
AlertStatus = Literal["new", "acknowledged", "resolved"]
SensorStatus = Literal["online", "offline", "retired"]

_MAC_HEX = re.compile(r"[^0-9A-Fa-f]")


def normalize_mac(value: str) -> str:
    raw = _MAC_HEX.sub("", value)
    if len(raw) != 12:
        raise ValueError(f"invalid MAC address: {value!r}")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).upper()


class WiFiFrame(BaseModel):
    uptime_ms: int | None = None
    timestamp: datetime | None = None
    channel: int = Field(ge=1, le=14)
    frame_type: FrameType
    src_mac: str
    dst_mac: str
    bssid: str | None = None
    ssid: str | None = None
    rssi: int = Field(ge=-128, le=0)
    seq_num: int | None = Field(default=None, ge=0, le=4095)

    @field_validator("src_mac", "dst_mac")
    @classmethod
    def _normalize_addr(cls, value: str) -> str:
        return normalize_mac(value)

    @field_validator("bssid")
    @classmethod
    def _normalize_bssid(cls, value: str | None) -> str | None:
        return normalize_mac(value) if value else value


class FrameBatch(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=64)
    batch_seq: int
    frames: list[WiFiFrame] = Field(min_length=1, max_length=200)


class DetectionEvent(BaseModel):
    event_id: str
    event_type: EventType
    detected_at: datetime
    severity: int = Field(ge=1, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    sensor_ids: list[str]
    details: dict


class Alert(BaseModel):
    alert_id: str
    event_id: str
    created_at: datetime
    severity: int = Field(ge=1, le=10)
    title: str
    explanation: str
    recommended_action: str
    status: AlertStatus = "new"

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    event_id: str
    event_type: EventType
    detected_at: datetime
    severity: int
    confidence: float
    sensor_ids: list[str]
    details: dict
    received_at: datetime

    model_config = {"from_attributes": True}


class AlertUpdate(BaseModel):
    """PATCH body. Only the two transitions a client is allowed to make --
    "new" is assigned by the backend, never by the caller."""

    status: Literal["acknowledged", "resolved"]


class FrameOut(BaseModel):
    id: int
    sensor_id: str
    received_at: datetime
    batch_seq: int
    channel: int
    frame_type: str
    src_mac: str
    dst_mac: str
    bssid: str | None
    ssid: str | None
    rssi: int
    seq_num: int | None

    model_config = {"from_attributes": True}


class SensorCreate(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=64)
    name: str | None = None
    location: str | None = None
    channels: list[int] = Field(default_factory=list)


class SensorUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    channels: list[int] | None = None
    status: SensorStatus | None = None


class SensorOut(BaseModel):
    sensor_id: str
    name: str | None
    location: str | None
    channels: list[int]
    last_seen_at: datetime | None
    registered_at: datetime
    status: SensorStatus

    model_config = {"from_attributes": True}