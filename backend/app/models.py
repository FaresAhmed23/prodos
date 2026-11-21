from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, SmallInteger, String, Text, ForeignKey, Index, UniqueConstraint
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

    # Edit: Linking events to incidents
    incident_id: Mapped[str] = mapped_column(String(36), ForeignKey("incidents.incident_id"), nullable=True)

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
    # F-22: written once, on new -> acknowledged only. Null on historical rows
    # and never-acknowledged alerts; scoring counts null as unacked.
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Edit: Additions:
    lang: Mapped[str] = mapped_column(String(8), nullable=True)

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

    # Edit: new columns to better specifiy an Explanation log
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("site_profile.site_id"), nullable=True
    )

    # Edit: new columns for performance measurement
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    fallback_reason: Mapped[str] = mapped_column(String(512), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=True)


class Sensor(Base):
    __tablename__ = "sensors"

    sensor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="offline", index=True)

    # Edit: Linking the sensors to businesses
    site_id: Mapped[str] = mapped_column(String(64), ForeignKey("site_profile.site_id"), nullable=True)


# ====================================================================================
#                                    New Tables @Fares
# ====================================================================================

# Saves the state of a business so the llm can know who its dealing with.
class SiteProfile(Base):
    __tablename__ = "site_profile"
    __table_args__ = (
        UniqueConstraint("trust_token", name="uq_site_profile_trust_token"),
    )

    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_name: Mapped[str | None] = mapped_column(String(200))
    business_type: Mapped[str | None] = mapped_column(String(64))
    wifi_ssids: Mapped[list] = mapped_column(JSON, default=list)
    known_access_points: Mapped[list] = mapped_column(JSON, default=list)
    router_model: Mapped[str | None] = mapped_column(String(100))
    primary_language: Mapped[str] = mapped_column(String(8), default="en")
    notes: Mapped[str | None] = mapped_column(Text)
    # F-21 public trust page. Null token = not enrolled; rotate replaces the
    # token, revoke nulls it.
    trust_token: Mapped[str | None] = mapped_column(String(64))
    trust_token_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    trust_token_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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
    explained_alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.alert_id"), nullable=True)
    explained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    explained_lang: Mapped[str | None] = mapped_column(String(8))
    explained_severity: Mapped[int | None] = mapped_column(SmallInteger)
    explained_event_count: Mapped[int | None] = mapped_column(Integer)


class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"

    site_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("site_profile.site_id"), primary_key=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ScoreSnapshot(Base):
    """One posture score per site per day (spec §5)."""

    __tablename__ = "score_snapshots"
    __table_args__ = (
        Index("ix_score_snapshots_site_id_computed_at", "site_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(FRAME_PK, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("site_profile.site_id"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    band: Mapped[str] = mapped_column(String(32), nullable=False)
    components: Mapped[dict] = mapped_column(JSON, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)