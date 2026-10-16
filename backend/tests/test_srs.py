"""SRS interface and FSRS adapter (pure, no database)."""

import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import SrsState
from app.domain.fsrs_engine import FsrsEngine, fuzz_bounds, fuzzed_interval
from app.domain.srs import Rating, SrsCardState

AT = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


def engine(retention: float = 0.9) -> FsrsEngine:
    return FsrsEngine(retention, fuzz=False)


def new_state(fsrs: FsrsEngine) -> SrsCardState:
    return fsrs.initial_state(card_id=1, due=AT)


def to_review(fsrs: FsrsEngine) -> SrsCardState:
    """A card that graduated with Easy on its first review."""
    state = fsrs.review(new_state(fsrs), Rating.EASY, AT, 5000)
    assert state.state == SrsState.REVIEW
    return state


def test_srs_initial_state_is_new_learning_step_zero() -> None:
    state = new_state(engine())
    assert state.state == SrsState.NEW
    assert state.step == 0
    assert state.payload is not None
    assert state.payload["state"] == 1  # fsrs State.Learning
    assert state.payload["step"] == 0


def test_srs_new_card_rated_good_goes_to_second_learning_step() -> None:
    # fsrs 6.3.2 default steps are (1 min, 10 min): Good moves step 0 → step 1, due in 10 min.
    state = engine().review(new_state(engine()), Rating.GOOD, AT, 5000)
    assert state.state == SrsState.LEARNING
    assert state.step == 1
    assert state.due == AT + timedelta(minutes=10)
    assert state.last_review == AT


def test_srs_new_card_rated_again_is_due_at_first_learning_step() -> None:
    state = engine().review(new_state(engine()), Rating.AGAIN, AT, 5000)
    assert state.state == SrsState.LEARNING
    assert state.step == 0
    assert state.due == AT + timedelta(minutes=1)


def test_srs_again_on_review_card_goes_to_relearning() -> None:
    fsrs = engine()
    review = to_review(fsrs)
    state = fsrs.review(review, Rating.AGAIN, review.due, 5000)
    assert state.state == SrsState.RELEARNING
    assert state.step == 0
    assert state.due == review.due + timedelta(minutes=10)
    assert state.stability is not None and review.stability is not None
    assert state.stability < review.stability


def test_srs_payload_round_trip_is_exact() -> None:
    fsrs = engine()
    state = fsrs.review(to_review(fsrs), Rating.GOOD, AT + timedelta(days=9), 4000)
    restored = FsrsEngine._to_card(state)
    assert restored.to_dict() == state.payload
    # Same next state whether we restore from the payload or keep the original object.
    corrupted_columns = SrsCardState(
        state=SrsState.LEARNING, due=AT, stability=1.0, difficulty=1.0, payload=state.payload
    )
    later = AT + timedelta(days=40)
    assert fsrs.review(corrupted_columns, Rating.GOOD, later, None) == fsrs.review(
        state, Rating.GOOD, later, None
    )


def test_srs_higher_retention_gives_shorter_interval() -> None:
    at_090 = to_review(engine(0.90))
    at_095 = to_review(engine(0.95))
    assert at_095.due - AT < at_090.due - AT


def test_srs_retrievability_is_none_when_new_and_decreases_over_time() -> None:
    fsrs = engine()
    assert fsrs.retrievability(new_state(fsrs), AT) is None
    review = to_review(fsrs)
    soon = fsrs.retrievability(review, AT + timedelta(days=1))
    later = fsrs.retrievability(review, AT + timedelta(days=30))
    assert soon is not None and later is not None
    assert 0 < later < soon <= 1


def test_srs_accepts_any_utc_equivalent_instant() -> None:
    # fsrs itself refuses a tzinfo other than timezone.utc; the adapter normalises.
    douala = AT.astimezone(ZoneInfo("Africa/Douala"))
    state = engine().review(new_state(engine()), Rating.GOOD, douala, None)
    assert state.last_review == AT


def test_srs_naive_instant_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        engine().review(new_state(engine()), Rating.GOOD, datetime(2026, 11, 1, 8, 0), None)  # noqa: DTZ001


def test_srs_seeded_fuzz_is_reproducible_and_within_bounds() -> None:
    def graduate(seed: int) -> datetime:
        fsrs = FsrsEngine(0.9, rng=random.Random(seed))
        return fsrs.review(fsrs.initial_state(1, AT), Rating.EASY, AT, None).due

    assert graduate(7) == graduate(7)
    unfuzzed_days = (to_review(engine()).due - AT).days
    low, high = fuzz_bounds(unfuzzed_days)
    assert low < unfuzzed_days < high
    seen = {(graduate(seed) - AT).days for seed in range(50)}
    assert seen <= set(range(low, high + 1))
    assert len(seen) > 1


def test_srs_short_intervals_are_not_fuzzed() -> None:
    assert fuzzed_interval(timedelta(days=2), random.Random(1)) == timedelta(days=2)
    assert fuzzed_interval(timedelta(minutes=10), random.Random(1)) == timedelta(minutes=10)
