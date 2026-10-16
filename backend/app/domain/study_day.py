"""Study day: the local calendar day a moment belongs to, shifted by `day_start_hour` (D-014).

Pure Python. A review at 02:00 in Douala with `day_start_hour` = 4 belongs to the previous
study day. Callers pass aware instants; nothing here reads the clock.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def as_utc(instant: datetime) -> datetime:
    """The same instant with `tzinfo=UTC`; raises ValueError for a naive datetime."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(f"naive datetime {instant!r}: pass an aware instant")
    return instant.astimezone(UTC)


def study_day_of(instant: datetime, tz: ZoneInfo, day_start_hour: int) -> date:
    """Study day containing `instant`."""
    as_utc(instant)
    return (instant.astimezone(tz) - timedelta(hours=day_start_hour)).date()


def study_day_bounds(day: date, tz: ZoneInfo, day_start_hour: int) -> tuple[datetime, datetime]:
    """[start, end) of a study day, as UTC instants."""
    start = datetime.combine(day, time(day_start_hour), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(day_start_hour), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)
