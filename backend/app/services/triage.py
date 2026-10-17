"""Intake triage (module A): "I know it" / "not sure" / "to learn" before terms enter the queue.

The list shows the term and its sentence only, never a usage sheet: a sheet would bias the
self-assessment. Decisions are applied all or nothing.

A list-extension suggestion triaged as known also leaves the deck the AI suggested it for (the SPEC:
only retained terms enter the deck); it stays in the library as `known`, so it is never suggested
again. Imported terms keep their deck links whatever the decision (D-075, D-084).
"""

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import DeckItem, EventLog, LexicalItem
from app.domain.enums import ItemStatus, ItemType
from app.domain.events import DeckItemRemoved, EventType, ItemOrigin, ItemTriaged, TriageDecision
from app.domain.study_day import as_utc
from app.services.items import transition_item
from app.services.library import DeckRef, ItemNotFound, LibraryError, decks_of, get_deck

# `unsure` joins the queue like `learn`: discovery starts with the meaning hidden, so an unsure
# term costs one discovery at most, and the decision stays in the event for statistics.
TRIAGE_TARGET = {
    TriageDecision.LEARN: ItemStatus.QUEUED,
    TriageDecision.UNSURE: ItemStatus.QUEUED,
    TriageDecision.KNOWN: ItemStatus.KNOWN,
}


class NotInTriage(LibraryError):
    code = "not_in_triage"


class DuplicateDecision(LibraryError):
    status, code = 422, "duplicate_decision"


class TriageEntry(BaseModel):
    item_id: int
    term: str
    item_type: ItemType
    sentence: str | None
    decks: list[DeckRef]


def list_triage(session: Session, deck_id: int | None = None) -> list[TriageEntry]:
    """Terms waiting for triage, in deck order when a deck is given, else oldest first."""
    if deck_id is not None:
        get_deck(session, deck_id)
        rows = session.execute(
            select(LexicalItem, DeckItem.context_sentence)
            .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
            .where(DeckItem.deck_id == deck_id, LexicalItem.status == ItemStatus.TRIAGE)
            .order_by(DeckItem.position, LexicalItem.id)
        ).all()
    else:
        rows = [
            (item, None)
            for item in session.scalars(
                select(LexicalItem)
                .where(LexicalItem.status == ItemStatus.TRIAGE)
                .order_by(LexicalItem.created_at, LexicalItem.id)
            )
        ]
    decks = decks_of(session, (item.id for item, _ in rows))
    return [
        TriageEntry(
            item_id=item.id,
            term=item.term,
            item_type=ItemType(item.item_type),
            sentence=context or item.origin_sentence,
            decks=decks.get(item.id, []),
        )
        for item, context in rows
    ]


def apply_triage(
    session: Session, decisions: Sequence[tuple[int, TriageDecision]], at: datetime
) -> dict[str, int]:
    """Apply every decision or none: one `item.triaged` event and one status change per term.

    Raises ItemNotFound, NotInTriage (with the offending ids) or DuplicateDecision.
    """
    at = as_utc(at)
    ids = [item_id for item_id, _ in decisions]
    if len(set(ids)) != len(ids):
        raise DuplicateDecision("Each term may appear only once.")
    items = {
        item.id: item
        for item in session.scalars(select(LexicalItem).where(LexicalItem.id.in_(ids)))
    }
    missing = [item_id for item_id in ids if item_id not in items]
    if missing:
        raise ItemNotFound(f"There is no term {missing[0]}.", item_ids=missing)
    not_in_triage = [item_id for item_id in ids if items[item_id].status != ItemStatus.TRIAGE]
    if not_in_triage:
        raise NotInTriage(
            "Some terms are not waiting for triage; nothing was changed.", item_ids=not_in_triage
        )
    counts = {decision.value: 0 for decision in TriageDecision}
    for item_id, decision in decisions:
        item = items[item_id]
        record_event(
            session, ItemTriaged(lexical_item_id=item.id, decision=decision), occurred_at=at
        )
        transition_item(session, item, TRIAGE_TARGET[decision], at)
        if decision is TriageDecision.KNOWN:
            _leave_extension_deck(session, item, at)
        counts[decision.value] += 1
    session.flush()
    return counts


def extension_deck_of(session: Session, item_id: int) -> int | None:
    """The deck a list extension created this term for (read from its `item.created` event: the
    term table keeps no origin), or None for any other origin."""
    payload = session.scalar(
        select(EventLog.payload)
        .where(
            EventLog.event_type == EventType.ITEM_CREATED,
            EventLog.entity_type == "lexical_item",
            EventLog.entity_id == item_id,
        )
        .order_by(EventLog.id)
        .limit(1)
    )
    if not payload or payload.get("origin") != ItemOrigin.EXTENSION:
        return None
    return payload.get("deck_id")


def _leave_extension_deck(session: Session, item: LexicalItem, at: datetime) -> None:
    deck_id = extension_deck_of(session, item.id)
    if deck_id is None:
        return
    link = session.scalar(
        select(DeckItem).where(DeckItem.deck_id == deck_id, DeckItem.lexical_item_id == item.id)
    )
    if link is None:
        return
    session.delete(link)
    record_event(session, DeckItemRemoved(deck_id=deck_id, lexical_item_id=item.id), occurred_at=at)
