"""Module A: sources, decks, lexical items, usage sheets, exercise templates."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow
from app.db.types import JSONDict, UTCDateTime, closed_enum
from app.domain.enums import (
    CardDirection,
    ContentOrigin,
    DeckKind,
    DeckStatus,
    EnrichmentStatus,
    ItemStatus,
    ItemType,
)


class Source(TimestampMixin, Base):
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(200))
    context: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(1000))
    source_date: Mapped[date | None] = mapped_column(Date)


class Deck(TimestampMixin, Base):
    __tablename__ = "deck"
    __table_args__ = (Index("ix_deck_status_queue_position", "status", "queue_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("source.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[DeckKind] = mapped_column(
        closed_enum(DeckKind, "deck_kind"), default=DeckKind.CUSTOM
    )
    status: Mapped[DeckStatus] = mapped_column(
        closed_enum(DeckStatus, "deck_status"), default=DeckStatus.QUEUED
    )
    deadline: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    queue_position: Mapped[int | None] = mapped_column(Integer)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    items: Mapped[list[DeckItem]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", passive_deletes=True
    )


class DeckItem(Base):
    """Many-to-many link: a term can belong to several decks and still has one pair of cards."""

    __tablename__ = "deck_item"
    __table_args__ = (UniqueConstraint("deck_id", "lexical_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("deck.id", ondelete="CASCADE"))
    lexical_item_id: Mapped[int] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Sentence specific to this deck (the term's own origin sentence lives on lexical_item).
    context_sentence: Mapped[str | None] = mapped_column(Text)

    deck: Mapped[Deck] = relationship(back_populates="items")
    lexical_item: Mapped[LexicalItem] = relationship(back_populates="deck_links")


class LexicalItem(TimestampMixin, Base):
    __tablename__ = "lexical_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(300))
    # Indexed but not unique: homographs and duplicates are reported on import, not forbidden.
    normalized_form: Mapped[str] = mapped_column(String(300), index=True)
    lemma: Mapped[str | None] = mapped_column(String(300))
    item_type: Mapped[ItemType] = mapped_column(
        closed_enum(ItemType, "item_type"), default=ItemType.WORD
    )
    part_of_speech: Mapped[str | None] = mapped_column(String(50))
    origin_sentence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ItemStatus] = mapped_column(
        closed_enum(ItemStatus, "item_status"), default=ItemStatus.DRAFT, index=True
    )
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    discovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    # Cards born from an error ("at university") belong to an error_drill deck. This FK and
    # error_event.lexical_item_id form a cycle; `use_alter` only tells SQLAlchemy how to order
    # the tables (SQLite accepts a forward reference in CREATE TABLE).
    origin_error_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_event.id", ondelete="SET NULL", use_alter=True)
    )

    deck_links: Mapped[list[DeckItem]] = relationship(
        back_populates="lexical_item", cascade="all, delete-orphan", passive_deletes=True
    )


class Enrichment(TimestampMixin, Base):
    """AI usage sheet. Versions are kept; exactly one is current per term."""

    __tablename__ = "enrichment"
    __table_args__ = (
        Index(
            "uq_enrichment_current",
            "lexical_item_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lexical_item_id: Mapped[int] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONDict)
    schema_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[EnrichmentStatus] = mapped_column(
        closed_enum(EnrichmentStatus, "enrichment_status"), default=EnrichmentStatus.COMPLETE
    )
    # Null when the sheet was typed by hand.
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class ExerciseTemplate(TimestampMixin, Base):
    __tablename__ = "exercise_template"

    id: Mapped[int] = mapped_column(primary_key=True)
    lexical_item_id: Mapped[int] = mapped_column(
        ForeignKey("lexical_item.id", ondelete="CASCADE"), index=True
    )
    exercise_type: Mapped[str] = mapped_column(String(64))
    direction: Mapped[CardDirection | None] = mapped_column(
        closed_enum(CardDirection, "exercise_direction")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONDict)
    origin: Mapped[ContentOrigin] = mapped_column(closed_enum(ContentOrigin, "exercise_origin"))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
