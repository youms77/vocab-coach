"""Review load forecast over 14 study days."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.durations import DurationEstimates
from app.domain.enums import CardDirection, ItemStatus, SrsState
from app.domain.forecast import CardSnapshot, forecast_load

DOUALA = ZoneInfo("Africa/Douala")
TODAY = date(2026, 11, 1)  # study day 2026-11-01 03:00 UTC -> 2026-11-02 03:00 UTC
NOW = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


def card(
    card_id: int,
    due: datetime,
    direction: CardDirection = CardDirection.RECEPTIVE,
    item_status: ItemStatus = ItemStatus.LEARNING,
    state: SrsState = SrsState.REVIEW,
    suspended: bool = False,
) -> CardSnapshot:
    return CardSnapshot(card_id, card_id, direction, state, due, item_status, suspended)


def forecast(cards: list[CardSnapshot], days: int = 14) -> list[tuple[date, int, float]]:
    loads = forecast_load(cards, TODAY, DOUALA, 4, DurationEstimates(), days)
    return [(load.day, load.cards, load.seconds) for load in loads]


def test_forecast_covers_14_days_and_counts_overdue_on_first_day() -> None:
    cards = [
        card(1, NOW - timedelta(days=5)),  # overdue
        card(2, NOW, CardDirection.PRODUCTIVE),
        card(3, NOW + timedelta(days=2)),
        card(4, NOW + timedelta(days=30)),  # beyond the window
    ]
    result = forecast(cards)
    assert len(result) == 14
    assert result[0] == (TODAY, 2, 15 + 25)
    assert result[2] == (TODAY + timedelta(days=2), 1, 15)
    assert sum(cards for _, cards, _ in result) == 3


def test_forecast_learning_step_due_later_today_counts_today() -> None:
    # 2026-11-02 02:30 in Douala still belongs to study day 2026-11-01.
    late = datetime(2026, 11, 2, 2, 30, tzinfo=DOUALA)
    result = forecast(
        [card(1, NOW + timedelta(minutes=10), state=SrsState.LEARNING), card(2, late)]
    )
    assert result[0][1] == 2
    assert result[1][1] == 0


@pytest.mark.parametrize("status", [ItemStatus.ARCHIVED, ItemStatus.KNOWN])
def test_forecast_excludes_archived_and_known_items(status: ItemStatus) -> None:
    result = forecast([card(1, NOW, item_status=status), card(2, NOW)])
    assert result[0][1] == 1


def test_forecast_excludes_suspended_cards() -> None:
    assert forecast([card(1, NOW, suspended=True)])[0][1] == 0
