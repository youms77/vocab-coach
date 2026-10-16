"""Module C: FSRS cards and review log."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow
from app.db.types import JSONDict, UTCDateTime, closed_enum
from app.domain.enums import CardDirection, SrsState


class Card(TimestampMixin, Base):
    """One card per (term, direction). Scheduling fields mirror the fsrs `Card`; `srs_payload` keeps
    the library's full serialised state for an exact restore."""

    __tablename__ = "card"
    __table_args__ = (
        UniqueConstraint("lexical_item_id", "direction"),
        Index("ix_card_suspended_due", "suspended", "due"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lexical_item_id: Mapped[int] = mapped_column(ForeignKey("lexical_item.id", ondelete="CASCADE"))
    direction: Mapped[CardDirection] = mapped_column(closed_enum(CardDirection, "card_direction"))
    srs_state: Mapped[SrsState] = mapped_column(
        closed_enum(SrsState, "card_srs_state"), default=SrsState.NEW
    )
    step: Mapped[int | None] = mapped_column(Integer)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    # Kept by the app: fsrs 6 no longer counts repetitions and lapses.
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    srs_algorithm: Mapped[str | None] = mapped_column(String(64))
    srs_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)


def _rating_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} BETWEEN 1 AND 4", name=f"{column}_range")


class ReviewLog(Base):
    """Append-only. Before/after snapshot so retention can be computed without replaying FSRS."""

    __tablename__ = "review_log"
    __table_args__ = (_rating_check("auto_rating"), _rating_check("final_rating"))

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id", ondelete="CASCADE"), index=True)
    study_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_session.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    exercise_type: Mapped[str] = mapped_column(String(64))
    exercise_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercise_template.id", ondelete="SET NULL")
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    # Relative to data/audio/.
    audio_path: Mapped[str | None] = mapped_column(String(500))
    auto_rating: Mapped[int | None] = mapped_column(Integer)
    final_rating: Mapped[int] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)

    state_before: Mapped[SrsState] = mapped_column(closed_enum(SrsState, "state_before"))
    stability_before: Mapped[float | None] = mapped_column(Float)
    difficulty_before: Mapped[float | None] = mapped_column(Float)
    due_before: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Days since the previous review (fractional: learning steps are minutes).
    elapsed_days: Mapped[float | None] = mapped_column(Float)
    retrievability: Mapped[float | None] = mapped_column(Float)
    state_after: Mapped[SrsState] = mapped_column(closed_enum(SrsState, "state_after"))
    stability_after: Mapped[float | None] = mapped_column(Float)
    difficulty_after: Mapped[float | None] = mapped_column(Float)
    due_after: Mapped[datetime] = mapped_column(UTCDateTime)
    scheduled_days: Mapped[float] = mapped_column(Float)
    srs_algorithm: Mapped[str] = mapped_column(String(64))
