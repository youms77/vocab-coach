"""Deck status changes and queue reordering (module D)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Deck
from app.domain.deck_queue import check_deck_transition, dense_positions
from app.domain.enums import DeckStatus
from app.domain.events import DeckReordered, DeckStatusChanged
from app.domain.study_day import as_utc


def change_deck_status(session: Session, deck: Deck, to_status: DeckStatus, at: datetime) -> None:
    """Apply a deck transition and log `deck.status_changed`. Raises InvalidDeckTransition."""
    at = as_utc(at)
    from_status = DeckStatus(deck.status)
    check_deck_transition(deck.id, from_status, to_status)
    deck.status = to_status
    if to_status == DeckStatus.ACTIVE and deck.activated_at is None:
        deck.activated_at = at
    # Reopening a done deck clears its completion date.
    deck.completed_at = at if to_status == DeckStatus.DONE else None
    record_event(
        session,
        DeckStatusChanged(deck_id=deck.id, from_status=from_status, to_status=to_status),
        occurred_at=at,
    )


def reorder_queue(session: Session, deck_ids: Sequence[int], at: datetime) -> None:
    """Rewrite queue positions densely (0..n-1) for every deck that is not done."""
    at = as_utc(at)
    decks = {
        deck.id: deck
        for deck in session.scalars(select(Deck).where(Deck.status != DeckStatus.DONE))
    }
    for deck_id, position in dense_positions(deck_ids, decks).items():
        decks[deck_id].queue_position = position
    record_event(session, DeckReordered(deck_ids=list(deck_ids)), occurred_at=at)
    session.flush()
