"""Modules E, F, G: productions (writing, speaking, shadowing...), pronunciation, consolidation."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import JSONDict, JSONList, UTCDateTime, closed_enum
from app.domain.enums import (
    ConsolidationTaskKind,
    ConsolidationTaskStatus,
    Modality,
    ProductionKind,
)


class ProductionAttempt(TimestampMixin, Base):
    __tablename__ = "production_attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ProductionKind] = mapped_column(closed_enum(ProductionKind, "production_kind"))
    modality: Mapped[Modality] = mapped_column(closed_enum(Modality, "production_modality"))
    prompt_text: Mapped[str | None] = mapped_column(Text)
    # What the user wrote, or the transcript of what they said.
    text: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str | None] = mapped_column(String(500))
    audio_seconds: Mapped[float | None] = mapped_column(Float)
    # The user's own words only (for a pasted transcript: their sentences, not the other speaker's).
    # Denominator of the "errors per 100 words" rates.
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    ai_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_call_log.id", ondelete="SET NULL")
    )
    consolidation_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("consolidation_task.id", ondelete="SET NULL"), index=True
    )
    curriculum_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_unit.id", ondelete="SET NULL"), index=True
    )
    study_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_session.id", ondelete="SET NULL"), index=True
    )


class ProductionTarget(Base):
    """A term the production was expected to use; `None` = not evaluated yet."""

    __tablename__ = "production_target"
    __table_args__ = (UniqueConstraint("production_attempt_id", "lexical_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    production_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("production_attempt.id", ondelete="CASCADE")
    )
    lexical_item_id: Mapped[int] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="CASCADE"), index=True
    )
    used: Mapped[bool | None] = mapped_column(Boolean)
    used_correctly: Mapped[bool | None] = mapped_column(Boolean)


class PronunciationResult(TimestampMixin, Base):
    __tablename__ = "pronunciation_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    production_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("production_attempt.id", ondelete="CASCADE"), index=True
    )
    target_text: Mapped[str] = mapped_column(Text)
    transcript: Mapped[str] = mapped_column(Text)
    unrecognized_words: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    provider: Mapped[str] = mapped_column(String(50))


class ConsolidationTask(TimestampMixin, Base):
    __tablename__ = "consolidation_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("deck.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(Text)
    task_kind: Mapped[ConsolidationTaskKind] = mapped_column(
        closed_enum(ConsolidationTaskKind, "consolidation_task_kind")
    )
    suggested_structure: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    status: Mapped[ConsolidationTaskStatus] = mapped_column(
        closed_enum(ConsolidationTaskStatus, "consolidation_task_status"),
        default=ConsolidationTaskStatus.PROPOSED,
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ConsolidationTaskItem(Base):
    __tablename__ = "consolidation_task_item"
    __table_args__ = (UniqueConstraint("consolidation_task_id", "lexical_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    consolidation_task_id: Mapped[int] = mapped_column(
        ForeignKey("consolidation_task.id", ondelete="CASCADE")
    )
    lexical_item_id: Mapped[int] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="CASCADE"), index=True
    )
