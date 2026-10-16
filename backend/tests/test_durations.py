"""Duration estimates: defaults, then observed medians."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.domain.durations import (
    DISCOVERY_SECONDS,
    PRODUCTIVE_TYPED_CARD_SECONDS,
    RECEPTIVE_CARD_SECONDS,
    DurationClass,
    DurationEstimates,
    duration_class,
    estimate_durations,
)
from app.domain.enums import CardDirection, ItemStatus
from app.domain.events import DiscoveryCompleted
from app.services.durations import observed_estimates
from tests.factories import NOW, add_card, add_item, add_review


def test_planner_durations_default_without_data() -> None:
    estimates = estimate_durations([], [])
    assert estimates == DurationEstimates()
    assert estimates.receptive == RECEPTIVE_CARD_SECONDS == 15
    assert estimates.productive_typed == PRODUCTIVE_TYPED_CARD_SECONDS == 25
    assert estimates.discovery == DISCOVERY_SECONDS == 150
    assert estimates.observed == frozenset()


def test_planner_durations_use_median_from_thirty_reviews_per_class() -> None:
    receptive = [(DurationClass.RECEPTIVE, float(s)) for s in range(1, 31)]  # median 15.5
    productive = [(DurationClass.PRODUCTIVE_TYPED, 40.0)] * 29  # one short of the threshold
    estimates = estimate_durations(receptive + productive, [])
    assert estimates.receptive == 15.5
    assert estimates.productive_typed == PRODUCTIVE_TYPED_CARD_SECONDS
    assert estimates.observed == {"receptive"}


def test_planner_durations_use_discovery_median_from_ten_discoveries() -> None:
    assert estimate_durations([], [100.0] * 9).discovery == DISCOVERY_SECONDS
    assert estimate_durations([], [100.0] * 9 + [400.0]).discovery == 100.0


def test_planner_duration_class() -> None:
    assert duration_class(CardDirection.RECEPTIVE, "recognition") == DurationClass.RECEPTIVE
    assert (
        duration_class(CardDirection.PRODUCTIVE, "typed_recall") == DurationClass.PRODUCTIVE_TYPED
    )
    assert duration_class(CardDirection.PRODUCTIVE, "spoken_answer") == DurationClass.ORAL


def test_planner_durations_observed_from_database_last_30_days(session: Session) -> None:
    item = add_item(session, status=ItemStatus.LEARNING)
    card = add_card(session, item, CardDirection.RECEPTIVE)
    for _ in range(30):
        add_review(session, card).response_time_ms = 8000
    old = add_review(session, card)  # outside the window: ignored
    old.reviewed_at, old.response_time_ms = NOW - timedelta(days=31), 90_000
    for _ in range(10):
        record_event(
            session,
            DiscoveryCompleted(lexical_item_id=item.id, duration_ms=120_000),
            occurred_at=NOW,
        )
    session.flush()
    estimates = observed_estimates(session, NOW + timedelta(hours=1))
    assert estimates.receptive == 8.0
    assert estimates.discovery == 120.0
    assert estimates.productive_typed == PRODUCTIVE_TYPED_CARD_SECONDS
    assert estimates.observed == {"receptive", "discovery"}
