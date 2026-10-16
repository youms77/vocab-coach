"""Modules D, I, J: study sessions, event log, AI call log, settings."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base, TimestampMixin, utcnow
from app.db.types import JSONDict, UTCDateTime


class StudySession(TimestampMixin, Base):
    __tablename__ = "study_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Plan frozen when the session starts.
    planned: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)


class EventLog(Base):
    """Shared, append-only log read by the dashboard.

    No foreign keys on purpose: events must survive the deletion of what they describe. The
    application never updates or deletes rows; SQLite triggers (migration 0001) enforce it.
    `occurred_at` is the business date (demo data may backdate it); `recorded_at` is the insert
    time.
    """

    __tablename__ = "event_log"
    __table_args__ = (Index("ix_event_log_type_occurred_at", "event_type", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    # Plain JSON (not mutable): rows are never modified.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_version: Mapped[int] = mapped_column(Integer)
    study_session_id: Mapped[int | None] = mapped_column(Integer)


class AICallLog(Base):
    """One row per provider call. Never stores an API key or the full prompt."""

    __tablename__ = "ai_call_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    # Truncated to ERROR_MESSAGE_MAX characters on assignment.
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    fallback_from: Mapped[str | None] = mapped_column(String(50))

    ERROR_MESSAGE_MAX = 500

    @validates("error_message")
    def _truncate_error_message(self, _key: str, value: str | None) -> str | None:
        return value[: self.ERROR_MESSAGE_MAX] if value is not None else None


class Setting(Base):
    """Only values the user changed; defaults live in app/domain/settings_defaults.py.
    Never holds secrets (API keys stay in `.env`)."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
