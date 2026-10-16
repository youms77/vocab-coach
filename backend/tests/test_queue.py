"""Deck transitions and queue order (queue criteria). Planner-level queue tests are at the end."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Deck, EventLog, LexicalItem
from app.domain.deck_queue import (
    DECK_TRANSITIONS,
    DeckItemRef,
    DeckSnapshot,
    InvalidDeckTransition,
    queue_order,
    queued_candidates,
)
from app.domain.enums import CardDirection, DeckStatus, ItemStatus
from app.domain.fsrs_engine import FsrsEngine
from app.domain.planner import BlockKind, NewItemEntry, PlanLimit, SessionPlan
from app.services.decks import change_deck_status, reorder_queue
from app.services.planning import plan_today
from tests.factories import NOW, add_card, add_deck, add_item, link

TODAY = date(2026, 11, 1)
ALL_PAIRS = [(a, b) for a in DeckStatus for b in DeckStatus]
ALLOWED = [(a, b) for a, b in ALL_PAIRS if b in DECK_TRANSITIONS[a]]
FORBIDDEN = [p for p in ALL_PAIRS if p not in ALLOWED]


def snapshot(
    deck_id: int,
    status: DeckStatus = DeckStatus.ACTIVE,
    deadline: date | None = None,
    position: int | None = None,
    items: tuple[tuple[int, ItemStatus], ...] = (),
) -> DeckSnapshot:
    refs = tuple(DeckItemRef(item_id, s, i) for i, (item_id, s) in enumerate(items))
    return DeckSnapshot(deck_id, status, deadline, position, refs)


# --- Deck transitions ---------------------------------------------------------------------


@pytest.mark.parametrize(("from_status", "to_status"), ALLOWED, ids=lambda s: str(s))
def test_queue_allowed_deck_transition_logs_event(
    session: Session, from_status: DeckStatus, to_status: DeckStatus
) -> None:
    deck = add_deck(session)
    deck.status = from_status
    change_deck_status(session, deck, to_status, NOW)
    assert deck.status == to_status
    [event] = session.scalars(
        select(EventLog.payload).where(EventLog.event_type == "deck.status_changed")
    ).all()
    assert (event["from_status"], event["to_status"]) == (from_status.value, to_status.value)


@pytest.mark.parametrize(("from_status", "to_status"), FORBIDDEN, ids=lambda s: str(s))
def test_queue_forbidden_deck_transition_raises(
    session: Session, from_status: DeckStatus, to_status: DeckStatus
) -> None:
    deck = add_deck(session)
    deck.status = from_status
    with pytest.raises(InvalidDeckTransition):
        change_deck_status(session, deck, to_status, NOW)


def test_queue_done_and_reopen_dates(session: Session) -> None:
    deck = add_deck(session)
    change_deck_status(session, deck, DeckStatus.ACTIVE, NOW)
    later = NOW + timedelta(days=3)
    change_deck_status(session, deck, DeckStatus.DONE, later)
    assert deck.completed_at == later
    change_deck_status(session, deck, DeckStatus.ACTIVE, later + timedelta(days=1))
    assert deck.completed_at is None
    assert deck.activated_at == NOW  # first activation is kept


# --- Queue order ----------------------------------------------------------------------------


def test_queue_order_deadline_first_then_position() -> None:
    decks = [
        snapshot(1, position=0),
        snapshot(2, position=1, deadline=TODAY + timedelta(days=20)),
        snapshot(3, position=2, deadline=TODAY + timedelta(days=5)),
        snapshot(4, position=None),
        snapshot(5, position=3, deadline=TODAY),  # deadline today: not future, normal place
        snapshot(6, status=DeckStatus.PAUSED, position=0),
        snapshot(7, status=DeckStatus.QUEUED, position=4),
    ]
    assert [d.id for d in queue_order(decks, TODAY)] == [3, 2, 1, 5, 7, 4]


def test_queue_term_in_two_decks_is_proposed_once_through_first_deck() -> None:
    first = snapshot(1, position=0, items=((10, ItemStatus.QUEUED), (11, ItemStatus.QUEUED)))
    second = snapshot(2, position=1, items=((11, ItemStatus.QUEUED), (12, ItemStatus.TRIAGE)))
    candidates = queued_candidates(queue_order([second, first], TODAY))
    assert [(c.lexical_item_id, c.deck_id) for c in candidates] == [(10, 1), (11, 1)]


def test_queue_term_beyond_queued_is_ignored() -> None:
    deck = snapshot(1, items=((10, ItemStatus.LEARNING), (11, ItemStatus.QUEUED)))
    assert [c.lexical_item_id for c in queued_candidates([deck])] == [11]


# --- Reordering -----------------------------------------------------------------------------


def test_queue_reorder_is_dense_and_logged(session: Session) -> None:
    decks = [add_deck(session, f"Deck {i}") for i in range(4)]
    decks[0].queue_position, decks[1].queue_position = 5, 9
    decks[2].status = DeckStatus.ACTIVE
    done = add_deck(session, "Finished")
    done.status, done.queue_position = DeckStatus.DONE, 7
    order = [decks[3].id, decks[1].id, decks[2].id, decks[0].id]
    reorder_queue(session, order, NOW)
    positions = {i: p for i, p in session.execute(select(Deck.id, Deck.queue_position))}
    assert [positions[i] for i in order] == [0, 1, 2, 3]
    assert positions[done.id] == 7
    [event] = session.scalars(
        select(EventLog.payload).where(EventLog.event_type == "deck.reordered")
    ).all()
    assert event["deck_ids"] == order


def test_queue_reorder_must_list_every_open_deck_once(session: Session) -> None:
    a, b = add_deck(session, "A"), add_deck(session, "B")
    with pytest.raises(ValueError, match="exactly once"):
        reorder_queue(session, [a.id], NOW)
    with pytest.raises(ValueError, match="exactly once"):
        reorder_queue(session, [a.id, b.id, a.id], NOW)


# --- Queue as seen by the planner (database -> plan_today) ----------------------------------


def _deck_with_items(
    session: Session, name: str, count: int, status: DeckStatus, position: int
) -> tuple[Deck, list[LexicalItem]]:
    deck = add_deck(session, name)
    deck.status, deck.queue_position = status, position
    items = [add_item(session, f"{name} {i}", status=ItemStatus.QUEUED) for i in range(count)]
    for i, item in enumerate(items):
        link(session, deck, item).position = i
    return deck, items


def _planned(session: Session) -> tuple[list[tuple[int, int | None]], SessionPlan]:
    plan = plan_today(session, NOW, engine_factory=lambda r: FsrsEngine(r, fuzz=False))
    block = plan.block(BlockKind.NEW_ITEMS)
    entries = [e for e in block.entries if isinstance(e, NewItemEntry)] if block else []
    return [(e.lexical_item_id, e.deck_id) for e in entries], plan


def test_queue_paused_deck_gives_no_new_terms_but_reviews_continue(session: Session) -> None:
    deck, _ = _deck_with_items(session, "Paused", 3, DeckStatus.PAUSED, 0)
    learned = add_item(session, "already learning", status=ItemStatus.LEARNING)
    link(session, deck, learned)
    add_card(session, learned, CardDirection.RECEPTIVE)  # due at NOW
    new_terms, plan = _planned(session)
    assert new_terms == []
    assert plan.limit == PlanLimit.NOTHING_TO_LEARN
    assert plan.block(BlockKind.REVIEWS) is not None


def test_queue_automatic_activation_is_proposed_without_writing(session: Session) -> None:
    active, _ = _deck_with_items(session, "Active", 2, DeckStatus.ACTIVE, 0)
    waiting, _ = _deck_with_items(session, "Waiting", 20, DeckStatus.QUEUED, 1)
    session.flush()
    events_before = session.scalar(select(func.count()).select_from(EventLog))
    new_terms, plan = _planned(session)
    assert [deck_id for _, deck_id in new_terms] == [active.id] * 2 + [waiting.id] * 10
    assert plan.decks_to_activate == [waiting.id]
    assert waiting.status == DeckStatus.QUEUED
    assert not session.dirty and not session.new
    assert session.scalar(select(func.count()).select_from(EventLog)) == events_before


def test_queue_term_in_two_decks_is_planned_once(session: Session) -> None:
    first, first_items = _deck_with_items(session, "First", 2, DeckStatus.ACTIVE, 0)
    second, _ = _deck_with_items(session, "Second", 1, DeckStatus.ACTIVE, 1)
    link(session, second, first_items[1])
    new_terms, _ = _planned(session)
    assert len(new_terms) == 3
    assert (first_items[1].id, first.id) in new_terms
    assert len({item_id for item_id, _ in new_terms}) == 3


def test_queue_term_already_learning_via_another_deck_is_ignored(session: Session) -> None:
    _deck_with_items(session, "Active", 1, DeckStatus.ACTIVE, 0)
    other, _ = _deck_with_items(session, "Other", 0, DeckStatus.ACTIVE, 1)
    learned = add_item(session, "learned elsewhere", status=ItemStatus.LEARNING)
    link(session, other, learned)
    new_terms, _ = _planned(session)
    assert learned.id not in {item_id for item_id, _ in new_terms}
    assert len(new_terms) == 1
