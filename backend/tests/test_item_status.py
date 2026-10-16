"""Item status rules: transition table, consolidation, discovery, unarchive (status criteria)."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Card, EventLog, LexicalItem, ReviewLog
from app.domain.enums import CardDirection, DeckStatus, ItemStatus, SrsState
from app.domain.fsrs_engine import FsrsEngine
from app.domain.item_status import (
    ITEM_TRANSITIONS,
    InvalidItemTransition,
    TransitionKind,
    check_item_transition,
    consolidation_target,
)
from app.domain.srs import Rating, SrsCardState
from app.services.discovery import DiscoveryError, complete_discovery, start_discovery
from app.services.items import mark_active, transition_item, unarchive_item
from app.services.reviews import record_review
from tests.factories import NOW, add_card, add_deck, add_item, link

ALL_PAIRS = [(a, b) for a in ItemStatus for b in ItemStatus]
MANUAL_PAIRS = [(a, b) for a, b in ALL_PAIRS if ITEM_TRANSITIONS[a].get(b) == TransitionKind.MANUAL]
NOT_MANUAL_PAIRS = [p for p in ALL_PAIRS if p not in MANUAL_PAIRS]


def status_events(session: Session) -> list[tuple[str, str]]:
    rows = session.scalars(
        select(EventLog).where(EventLog.event_type == "item.status_changed").order_by(EventLog.id)
    )
    return [(r.payload["from_status"], r.payload["to_status"]) for r in rows]


def no_fuzz(retention: float) -> FsrsEngine:
    return FsrsEngine(retention, fuzz=False)


@dataclass
class StabilityEngine:
    """Fake engine whose reviews set a chosen stability."""

    stability: float
    algorithm: str = "fake-stability"

    def initial_state(self, card_id: int, due: datetime) -> SrsCardState:
        return SrsCardState(state=SrsState.NEW, due=due)

    def review(
        self, state: SrsCardState, rating: Rating, at: datetime, duration_ms: int | None
    ) -> SrsCardState:
        return replace(
            state, state=SrsState.REVIEW, due=at + timedelta(days=1), stability=self.stability,
            difficulty=5.0, last_review=at,
        )  # fmt: skip

    def retrievability(self, state: SrsCardState, at: datetime) -> float | None:
        return None


def review_with_stability(session: Session, card: Card, stability: float, at: datetime) -> None:
    record_review(
        session, card, Rating.GOOD, at, 1000, "typed_recall",
        engine_factory=lambda _r: StabilityEngine(stability),
    )  # fmt: skip


# --- Transition table -------------------------------------------------------------------------


@pytest.mark.parametrize(("from_status", "to_status"), MANUAL_PAIRS, ids=lambda s: str(s))
def test_status_allowed_manual_transition_succeeds_and_logs_event(
    session: Session, from_status: ItemStatus, to_status: ItemStatus
) -> None:
    item = add_item(session, status=from_status)
    transition_item(session, item, to_status, NOW)
    assert item.status == to_status
    assert item.status_changed_at == NOW
    assert status_events(session) == [(from_status.value, to_status.value)]


@pytest.mark.parametrize(("from_status", "to_status"), NOT_MANUAL_PAIRS, ids=lambda s: str(s))
def test_status_forbidden_manual_transition_raises(
    session: Session, from_status: ItemStatus, to_status: ItemStatus
) -> None:
    item = add_item(session, status=from_status)
    with pytest.raises(InvalidItemTransition):
        transition_item(session, item, to_status, NOW)
    assert item.status == from_status
    assert status_events(session) == []


def test_status_reserved_transitions_need_their_operation() -> None:
    with pytest.raises(InvalidItemTransition, match="only complete_discovery"):
        check_item_transition(1, ItemStatus.DISCOVERING, ItemStatus.LEARNING, TransitionKind.MANUAL)
    with pytest.raises(InvalidItemTransition, match="only mark_active"):
        check_item_transition(1, ItemStatus.LEARNING, ItemStatus.ACTIVE, TransitionKind.AUTOMATIC)
    check_item_transition(1, ItemStatus.CONSOLIDATED, ItemStatus.LEARNING, TransitionKind.AUTOMATIC)


@pytest.mark.parametrize("from_status", [ItemStatus.LEARNING, ItemStatus.CONSOLIDATED])
def test_status_mark_active(session: Session, from_status: ItemStatus) -> None:
    item = add_item(session, status=from_status)
    mark_active(session, item, NOW)
    assert item.status == ItemStatus.ACTIVE
    assert status_events(session) == [(from_status.value, "active")]


def test_status_mark_active_refused_before_learning(session: Session) -> None:
    item = add_item(session, status=ItemStatus.QUEUED)
    with pytest.raises(InvalidItemTransition):
        mark_active(session, item, NOW)


# --- Consolidation ----------------------------------------------------------------------------


def test_status_consolidation_target_rule() -> None:
    assert consolidation_target(ItemStatus.LEARNING, 7.0, 7) == ItemStatus.CONSOLIDATED
    assert consolidation_target(ItemStatus.LEARNING, 6.99, 7) is None
    assert consolidation_target(ItemStatus.CONSOLIDATED, 6.99, 7) == ItemStatus.LEARNING
    assert consolidation_target(ItemStatus.CONSOLIDATED, None, 7) == ItemStatus.LEARNING
    assert consolidation_target(ItemStatus.ACTIVE, 0.5, 7) is None


def test_status_consolidates_at_threshold_and_falls_back_below(session: Session) -> None:
    item = add_item(session, status=ItemStatus.LEARNING)
    productive = add_card(session, item, CardDirection.PRODUCTIVE)
    review_with_stability(session, productive, 6.9, NOW)
    assert item.status == ItemStatus.LEARNING
    review_with_stability(session, productive, 7.0, NOW + timedelta(days=1))
    assert item.status == ItemStatus.CONSOLIDATED
    review_with_stability(session, productive, 2.0, NOW + timedelta(days=2))
    assert item.status == ItemStatus.LEARNING
    assert status_events(session) == [("learning", "consolidated"), ("consolidated", "learning")]


def test_status_receptive_stability_does_not_consolidate(session: Session) -> None:
    item = add_item(session, status=ItemStatus.LEARNING)
    receptive = add_card(session, item, CardDirection.RECEPTIVE)
    review_with_stability(session, receptive, 30.0, NOW)
    assert item.status == ItemStatus.LEARNING


def test_status_active_is_kept_after_a_lapse(session: Session) -> None:
    item = add_item(session, status=ItemStatus.ACTIVE)
    productive = add_card(session, item, CardDirection.PRODUCTIVE)
    review_with_stability(session, productive, 0.5, NOW)
    assert item.status == ItemStatus.ACTIVE


# --- Discovery --------------------------------------------------------------------------------


def test_status_start_discovery_activates_queued_deck(session: Session) -> None:
    deck = add_deck(session)
    item = add_item(session, status=ItemStatus.QUEUED)
    link(session, deck, item)
    start_discovery(session, item, deck, NOW)
    assert item.status == ItemStatus.DISCOVERING
    assert deck.status == DeckStatus.ACTIVE
    assert deck.activated_at == NOW
    deck_events = session.scalars(
        select(EventLog.payload).where(EventLog.event_type == "deck.status_changed")
    ).all()
    assert [(e["from_status"], e["to_status"]) for e in deck_events] == [("queued", "active")]


@pytest.mark.parametrize("deck_status", [DeckStatus.PAUSED, DeckStatus.DONE])
def test_status_start_discovery_refused_through_paused_or_done_deck(
    session: Session, deck_status: DeckStatus
) -> None:
    deck = add_deck(session)
    deck.status = deck_status
    item = add_item(session, status=ItemStatus.QUEUED)
    link(session, deck, item)
    with pytest.raises(DiscoveryError, match="no new terms"):
        start_discovery(session, item, deck, NOW)
    assert item.status == ItemStatus.QUEUED


def test_status_start_discovery_refused_through_unrelated_deck(session: Session) -> None:
    deck = add_deck(session)
    item = add_item(session, status=ItemStatus.QUEUED)
    with pytest.raises(DiscoveryError, match="not in deck"):
        start_discovery(session, item, deck, NOW)


def test_status_complete_discovery_without_ratings_creates_new_cards_due_next_day(
    session: Session,
) -> None:
    item = add_item(session, status=ItemStatus.QUEUED)
    start_discovery(session, item, None, NOW)
    receptive, productive = complete_discovery(
        session, item, NOW, duration_ms=140_000, engine_factory=no_fuzz
    )
    # NOW = 2026-10-16 09:00 in Douala; the next study day starts on the 17th at 04:00 local.
    next_day_start = datetime(2026, 10, 17, 3, 0, tzinfo=UTC)
    assert item.status == ItemStatus.LEARNING
    assert item.discovered_at == NOW
    for card, direction in ((receptive, "receptive"), (productive, "productive")):
        assert card.direction == direction
        assert card.srs_state == SrsState.NEW
        assert card.due == next_day_start
        assert card.reps == 0
        assert card.srs_payload is not None and card.srs_payload["step"] == 0
    types = session.scalars(select(EventLog.event_type).order_by(EventLog.id)).all()
    assert types == [
        "item.status_changed",
        "item.status_changed",
        "card.created",
        "card.created",
        "discovery.completed",
    ]
    completed = session.scalars(
        select(EventLog.payload).where(EventLog.event_type == "discovery.completed")
    ).one()
    assert completed["duration_ms"] == 140_000


def test_status_complete_discovery_with_initial_ratings_records_first_reviews(
    session: Session,
) -> None:
    item = add_item(session, status=ItemStatus.DISCOVERING)
    receptive, productive = complete_discovery(
        session,
        item,
        NOW,
        initial_ratings={
            CardDirection.RECEPTIVE: Rating.GOOD,
            CardDirection.PRODUCTIVE: Rating.AGAIN,
        },
        engine_factory=no_fuzz,
    )
    assert receptive.srs_state == productive.srs_state == SrsState.LEARNING
    assert receptive.due == NOW + timedelta(minutes=10)
    assert productive.due == NOW + timedelta(minutes=1)
    assert receptive.reps == productive.reps == 1
    assert session.scalar(select(func.count()).select_from(ReviewLog)) == 2


def test_status_complete_discovery_twice_or_from_queued_is_refused(session: Session) -> None:
    item = add_item(session, status=ItemStatus.DISCOVERING)
    complete_discovery(session, item, NOW, engine_factory=no_fuzz)
    with pytest.raises(DiscoveryError, match="already has cards"):
        complete_discovery(session, item, NOW, engine_factory=no_fuzz)
    queued = add_item(session, "account for", status=ItemStatus.QUEUED)
    with pytest.raises(InvalidItemTransition):
        complete_discovery(session, queued, NOW, engine_factory=no_fuzz)


# --- Unarchive --------------------------------------------------------------------------------


def test_status_unarchive_without_cards_returns_to_queued(session: Session) -> None:
    item = add_item(session, status=ItemStatus.ARCHIVED)
    unarchive_item(session, item, NOW)
    assert item.status == ItemStatus.QUEUED


def test_status_unarchive_with_cards_returns_to_learning_or_consolidated(
    session: Session,
) -> None:
    young = add_item(session, "young", status=ItemStatus.ARCHIVED)
    add_card(session, young, CardDirection.PRODUCTIVE).stability = 2.0
    unarchive_item(session, young, NOW)
    assert young.status == ItemStatus.LEARNING

    mature: LexicalItem = add_item(session, "mature", status=ItemStatus.ARCHIVED)
    add_card(session, mature, CardDirection.PRODUCTIVE).stability = 12.0
    unarchive_item(session, mature, NOW)
    assert mature.status == ItemStatus.CONSOLIDATED
