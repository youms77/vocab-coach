"""Progress statistics (module I): the status funnel now, and rebuilt from the event log.

The rebuild replays the life of every term: `item.created` makes it `draft` (every term is created
in `draft`, `library.create_item`), `item.status_changed` moves it, `item.deleted` and the source of
`item.merged` remove it. Applied to every event, it must give the counts of `lexical_item` now.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.stats.common import DayOf, Granularity, Period, buckets

FUNNEL = ("queued", "discovering", "learning", "consolidated", "active")
OUTSIDE_FUNNEL = ("triage", "known", "archived", "draft")
STATUSES = FUNNEL + OUTSIDE_FUNNEL
CREATED_STATUS = "draft"


class Change(StrEnum):
    CREATED = "created"
    STATUS = "status"
    REMOVED = "removed"  # deleted, or merged into another term


@dataclass(frozen=True)
class LifecycleEvent:
    at: datetime
    order: int  # event id: the order of two events at the same instant
    item_id: int
    change: Change
    to_status: str | None = None


def snapshot(statuses: Iterable[str]) -> dict[str, int]:
    """Count per status, the 9 statuses always present, in funnel order then the others."""
    counts = Counter(statuses)
    return {status: counts.get(status, 0) for status in STATUSES}


def _apply(state: dict[int, str], event: LifecycleEvent) -> None:
    if event.change is Change.CREATED:
        state[event.item_id] = CREATED_STATUS
    elif event.change is Change.STATUS and event.to_status is not None:
        state[event.item_id] = event.to_status
    elif event.change is Change.REMOVED:
        state.pop(event.item_id, None)


def replay(events: Iterable[LifecycleEvent]) -> dict[int, str]:
    """item id -> status after every event."""
    state: dict[int, str] = {}
    for event in sorted(events, key=lambda e: (e.at, e.order)):
        _apply(state, event)
    return state


@dataclass(frozen=True)
class FunnelBucket:
    key: date
    first_day: date
    last_day: date
    counts: dict[str, int]  # at the end of `last_day`


def rebuild(
    events: Iterable[LifecycleEvent], day_of: DayOf, period: Period, granularity: Granularity
) -> list[FunnelBucket]:
    """Counts per status at the end of every bucket of the period (events before the period are
    applied too)."""
    ordered = sorted(events, key=lambda e: (e.at, e.order))
    state: dict[int, str] = {}
    index = 0
    found = []
    for bucket in buckets(period, granularity):
        while index < len(ordered) and day_of(ordered[index].at) <= bucket.last_day:
            _apply(state, ordered[index])
            index += 1
        found.append(
            FunnelBucket(bucket.key, bucket.first_day, bucket.last_day, snapshot(state.values()))
        )
    return found
