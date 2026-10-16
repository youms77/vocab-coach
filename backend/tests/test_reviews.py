"""Review service: FSRS state, counters, review log, events (SRS acceptance criteria)."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, EventLog, LexicalItem
from app.db.settings_store import set_setting
from app.domain.enums import CardDirection, ItemStatus, SrsState
from app.domain.fsrs_engine import ALGORITHM, FsrsEngine
from app.domain.srs import EngineFactory, Rating, SrsCardState, SrsEngine
from app.services.reviews import ReviewNotAllowed, record_review
from tests.factories import NOW, add_card, add_item


def no_fuzz(retention: float) -> SrsEngine:
    return FsrsEngine(retention, fuzz=False)


def review(
    session: Session,
    card: Card,
    rating: Rating,
    at: datetime = NOW,
    engine_factory: EngineFactory = no_fuzz,
) -> None:
    record_review(session, card, rating, at, 4000, "typed_recall", engine_factory=engine_factory)


@pytest.fixture
def item(session: Session) -> LexicalItem:
    return add_item(session, status=ItemStatus.LEARNING)


@pytest.fixture
def card(session: Session, item: LexicalItem) -> Card:
    return add_card(session, item, CardDirection.RECEPTIVE)


def events(session: Session, event_type: str) -> list[EventLog]:
    return list(session.scalars(select(EventLog).where(EventLog.event_type == event_type)))


def test_srs_review_of_new_card_fills_log_snapshot_and_event(session: Session, card: Card) -> None:
    log = record_review(
        session, card, Rating.GOOD, NOW, 4200, "typed_recall", "shed light on", Rating.HARD,
        engine_factory=no_fuzz,
    )  # fmt: skip
    assert card.srs_state == SrsState.LEARNING
    assert card.step == 1
    assert card.due == NOW + timedelta(minutes=10)
    assert card.reps == 1
    assert card.lapses == 0
    assert card.last_review_at == NOW
    assert card.srs_algorithm == ALGORITHM
    assert card.srs_payload is not None and card.srs_payload["step"] == 1

    assert log.state_before == SrsState.NEW
    assert log.stability_before is None
    assert log.elapsed_days is None
    assert log.retrievability is None
    assert log.state_after == SrsState.LEARNING
    assert log.stability_after == card.stability
    assert log.due_after == card.due
    assert log.scheduled_days == pytest.approx(10 / 1440)
    assert log.auto_rating == Rating.HARD
    assert log.final_rating == Rating.GOOD
    assert log.answer_text == "shed light on"

    [event] = events(session, "card.reviewed")
    assert event.occurred_at == NOW
    assert event.payload["final_rating"] == 3
    assert event.payload["auto_rating"] == 2
    assert event.payload["review_log_id"] == log.id


def test_srs_reps_increment_and_before_snapshot_follows_previous_after(
    session: Session, card: Card
) -> None:
    review(session, card, Rating.GOOD)
    first_due, first_stability = card.due, card.stability
    later = NOW + timedelta(minutes=12)
    log = record_review(
        session, card, Rating.GOOD, later, 3000, "typed_recall", engine_factory=no_fuzz
    )
    assert card.reps == 2
    assert log.state_before == SrsState.LEARNING
    assert log.due_before == first_due
    assert log.stability_before == first_stability
    assert log.elapsed_days == pytest.approx(12 / 1440)
    assert card.srs_state == SrsState.REVIEW


def test_srs_again_on_review_card_counts_a_lapse(session: Session, card: Card) -> None:
    review(session, card, Rating.EASY)
    assert card.srs_state == SrsState.REVIEW
    review(session, card, Rating.AGAIN, at=card.due)
    assert card.srs_state == SrsState.RELEARNING
    assert card.lapses == 1
    assert card.reps == 2


def test_srs_again_in_learning_or_relearning_is_not_a_lapse(session: Session, card: Card) -> None:
    review(session, card, Rating.AGAIN)
    assert card.srs_state == SrsState.LEARNING
    review(session, card, Rating.EASY, at=NOW + timedelta(minutes=2))
    review(session, card, Rating.AGAIN, at=card.due)
    assert card.lapses == 1
    review(session, card, Rating.AGAIN, at=card.due)  # again while relearning
    assert card.srs_state == SrsState.RELEARNING
    assert card.lapses == 1
    assert card.reps == 4


def test_srs_review_earlier_than_last_review_is_refused(session: Session, card: Card) -> None:
    review(session, card, Rating.GOOD)
    with pytest.raises(ReviewNotAllowed, match="earlier"):
        review(session, card, Rating.GOOD, at=NOW - timedelta(seconds=1))
    review(session, card, Rating.GOOD, at=NOW)  # same instant is accepted
    assert card.reps == 2


@pytest.mark.parametrize("status", [ItemStatus.ARCHIVED, ItemStatus.KNOWN, ItemStatus.QUEUED])
def test_srs_review_of_card_whose_item_is_not_learnable_is_refused(
    session: Session, card: Card, item: LexicalItem, status: ItemStatus
) -> None:
    item.status = status
    with pytest.raises(ReviewNotAllowed, match=str(status)):
        review(session, card, Rating.GOOD)
    assert card.reps == 0
    assert events(session, "card.reviewed") == []


def test_srs_target_retention_is_read_at_each_review(session: Session, item: LexicalItem) -> None:
    receptive = add_card(session, item, CardDirection.RECEPTIVE)
    productive = add_card(session, item, CardDirection.PRODUCTIVE)
    review(session, receptive, Rating.EASY)
    set_setting(session, "target_retention", 0.95)
    review(session, productive, Rating.EASY)
    assert productive.due - NOW < receptive.due - NOW


class FakeEngine:
    """Deterministic stand-in: every review schedules the card in `rating` days."""

    algorithm = "fake-1"

    def initial_state(self, card_id: int, due: datetime) -> SrsCardState:
        return SrsCardState(state=SrsState.NEW, due=due)

    def review(
        self, state: SrsCardState, rating: Rating, at: datetime, duration_ms: int | None
    ) -> SrsCardState:
        return replace(
            state,
            state=SrsState.REVIEW,
            due=at + timedelta(days=int(rating)),
            stability=float(rating),
            difficulty=5.0,
            last_review=at,
            payload={"fake": int(rating)},
        )

    def retrievability(self, state: SrsCardState, at: datetime) -> float | None:
        return None if state.last_review is None else 0.5


def test_srs_engine_can_be_swapped_without_touching_the_service(
    session: Session, card: Card
) -> None:
    log = record_review(
        session,
        card,
        Rating.EASY,
        NOW,
        None,
        "typed_recall",
        engine_factory=lambda _r: FakeEngine(),
    )
    assert card.srs_algorithm == log.srs_algorithm == "fake-1"
    assert card.due == NOW + timedelta(days=4)
    assert card.srs_payload == {"fake": 4}
    assert log.scheduled_days == 4.0
