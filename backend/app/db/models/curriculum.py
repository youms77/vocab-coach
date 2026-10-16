"""Module H: general-English tracks and units."""

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import JSONDict, closed_enum
from app.domain.enums import UnitContentStatus, UnitProgress


class CurriculumTrack(TimestampMixin, Base):
    __tablename__ = "curriculum_track"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    syllabus_version: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class CurriculumUnit(TimestampMixin, Base):
    __tablename__ = "curriculum_unit"
    __table_args__ = (UniqueConstraint("track_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("curriculum_track.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    content_status: Mapped[UnitContentStatus] = mapped_column(
        closed_enum(UnitContentStatus, "unit_content_status"),
        default=UnitContentStatus.PENDING,
    )
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    # Deck holding the unit's terms.
    deck_id: Mapped[int | None] = mapped_column(
        ForeignKey("deck.id", ondelete="SET NULL"), index=True
    )
    progress: Mapped[UnitProgress] = mapped_column(
        closed_enum(UnitProgress, "unit_progress"), default=UnitProgress.NOT_STARTED
    )
