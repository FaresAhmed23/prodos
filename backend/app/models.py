from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, SmallInteger, String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# SQLite only autoincrements plain INTEGER PRIMARY KEYs, so the surrogate key
# needs a dialect variant or frame inserts fail outside Postgres.
FRAME_PK = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Frame(Base):
    __tablename__ = "frames"

    id: Mapped[int] = mapped_column(FRAME_PK, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(String(64), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    batch_seq: Mapped[int] = mapped_column(Integer)
    uptime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[int] = mapped_column(SmallInteger)
    frame_type: Mapped[str] = mapped_column(String(16), index=True)
    src_mac: Mapped[str] = mapped_column(String(17), index=True)
    dst_mac: Mapped[str] = mapped_column(String(17))
    bssid: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)
    ssid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rssi: Mapped[int] = mapped_column(SmallInteger)
    seq_num: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[int] = mapped_column(SmallInteger)
    confidence: Mapped[float] = mapped_column(Float)
    sensor_ids: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# --------------------------- Edited --------------------
class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)

    # Additions:
    lang: Mapped[str] = mapped_column(String(8), primary_key=True)

class ExplanationLog(Base):
    """One row per generated explanation. Store AI answers to either use them again or for later fine-tuning.

    `prompt` is null for template output, which is how a reviewer tells a real
    LLM explanation from an offline one after the fact.
    """

    __tablename__ = "explanation_logs"
    
    id: Mapped[int] = mapped_column(FRAME_PK, primary_key=True, autoincrement=True)
    event: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider_used: Mapped[str] = mapped_column(String(32), index=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class Sensor(Base):
    __tablename__ = "sensors"

    sensor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="offline", index=True)


# ====================================================================================
#                                    New Tables @Fares
# ====================================================================================

# Saves the state of a business so the llm can know who its dealing with.
class SiteProfile(Base):
    __tablename__ = "site_profile"

    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_name: Mapped[str | None] = mapped_column(String(200))
    business_type: Mapped[str | None] = mapped_column(String(64))
    wifi_ssids: Mapped[list] = mapped_column(JSON, default=list)
    known_access_points: Mapped[list] = mapped_column(JSON, default=list)
    router_model: Mapped[str | None] = mapped_column(String(100))
    primary_language: Mapped[str] = mapped_column(String(8), default="en")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

# Aggregation of related events, to save context tokens, and to reduce the number of times the llm will be needed to be called.
class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_site_key_last",
              "site_id", "incident_key", "last_seen_at"),
    )

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    site_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("site_profile.site_id"), nullable=False)
    incident_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=1)
    max_severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sensor_ids: Mapped[list] = mapped_column(JSON, default=list)

    # Reuse write-back (ALT PATH 3). Plain column.
    explained_alert_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("Alert.alert_id"))
    explained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    explained_lang: Mapped[str | None] = mapped_column(String(8))
    explained_severity: Mapped[int | None] = mapped_column(SmallInteger)
    explained_event_count: Mapped[int | None] = mapped_column(Integer)