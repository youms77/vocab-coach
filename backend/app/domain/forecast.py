"""Review load forecast (docs/SPEC.md modules D and I). Pure Python.

Counts the cards due on each study day from their current due dates (no simulation of future
reviews). Reused by the planner (anticipation constraint) and, in M9, by the dashboard.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.durations import DurationEstimates
from app.domain.enums import CardDirection, ItemStatus, SrsState
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.study_day import study_day_bounds, study_day_of


@dataclass(frozen=True)
class CardSnapshot:
    """What planning needs to know about a card. `retrievability` is computed by the SRS engine
    at the planning instant (None for a card never reviewed)."""

    card_id: int
    lexical_item_id: int
    direction: CardDirection
    state: SrsState
    due: datetime
    item_status: ItemStatus
    suspended: bool = False
    retrievability: float | None = None

    @property
    def schedulable(self) -> bool:
        """Cards of archived or known items (and suspended cards) are kept but never planned."""
        return not self.suspended and self.item_status in REVIEWABLE_STATUSES


@dataclass(frozen=True)
class DayLoad:
    day: date
    cards: int
    seconds: float


def forecast_load(
    cards: Iterable[CardSnapshot],
    from_day: date,
    tz: ZoneInfo,
    day_start_hour: int,
    durations: DurationEstimates,
    days: int = 14,
) -> list[DayLoad]:
    """Cards due and estimated seconds for each study day from `from_day` (included).

    An overdue card counts on the first day; cards due after the window are ignored.
    """
    _, first_day_end = study_day_bounds(from_day, tz, day_start_hour)
    counts = {from_day + timedelta(days=k): 0 for k in range(days)}
    seconds = dict.fromkeys(counts, 0.0)
    for card in cards:
        if not card.schedulable:
            continue
        day = from_day if card.due < first_day_end else study_day_of(card.due, tz, day_start_hour)
        if day in counts:
            counts[day] += 1
            seconds[day] += durations.for_due_card(card.direction)
    return [DayLoad(day, counts[day], seconds[day]) for day in counts]
