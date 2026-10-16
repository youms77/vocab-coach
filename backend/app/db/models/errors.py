"""Module E: error taxonomy and error events."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow
from app.db.types import JSONList, UTCDateTime, closed_enum
from app.domain.enums import ErrorCategoryStatus, ErrorSource


class ErrorCategory(TimestampMixin, Base):
    """Taxonomy node. `code` is a dotted path (`grammar.preposition.fixed_expression`); statistics
    aggregate by code prefix, and events may point at any node, not only leaves."""

    __tablename__ = "error_category"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(200), unique=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_category.id", ondelete="RESTRICT"), index=True
    )
    label_en: Mapped[str] = mapped_column(String(200))
    label_fr: Mapped[str] = mapped_column(String(200))
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_fr: Mapped[str] = mapped_column(Text, default="")
    examples: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    # Built-in categories come from content/error_taxonomy.yaml; others are user/AI proposals.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ErrorCategoryStatus] = mapped_column(
        closed_enum(ErrorCategoryStatus, "error_category_status"),
        default=ErrorCategoryStatus.ACTIVE,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class ErrorEvent(TimestampMixin, Base):
    __tablename__ = "error_event"
    __table_args__ = (
        CheckConstraint(
            "NOT (production_attempt_id IS NOT NULL AND review_log_id IS NOT NULL)",
            name="single_origin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("production_attempt.id", ondelete="CASCADE"), index=True
    )
    review_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_log.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[ErrorSource] = mapped_column(closed_enum(ErrorSource, "error_source"))
    original_text: Mapped[str] = mapped_column(Text, default="")
    erroneous_text: Mapped[str] = mapped_column(Text)
    correction: Mapped[str] = mapped_column(Text)
    alternatives: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int] = mapped_column(
        ForeignKey("error_category.id", ondelete="RESTRICT"), index=True
    )
    lexical_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="SET NULL"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
