from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.study_day import study_day_bounds, study_day_of

DOUALA = ZoneInfo("Africa/Douala")  # UTC+1, no daylight saving time


def test_study_day_switches_at_four_in_douala() -> None:
    # 02:00 and 03:59 in Douala still belong to the previous study day; 04:00 starts a new one.
    assert study_day_of(datetime(2026, 11, 2, 2, 0, tzinfo=DOUALA), DOUALA, 4) == date(2026, 11, 1)
    assert study_day_of(datetime(2026, 11, 2, 3, 59, tzinfo=DOUALA), DOUALA, 4) == date(2026, 11, 1)
    assert study_day_of(datetime(2026, 11, 2, 4, 0, tzinfo=DOUALA), DOUALA, 4) == date(2026, 11, 2)


def test_study_day_accepts_any_aware_instant() -> None:
    # 01:30 UTC = 02:30 in Douala → previous study day.
    assert study_day_of(datetime(2026, 11, 2, 1, 30, tzinfo=UTC), DOUALA, 4) == date(2026, 11, 1)


def test_study_day_bounds_are_utc_and_contiguous() -> None:
    start, end = study_day_bounds(date(2026, 11, 1), DOUALA, 4)
    assert start == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
    assert study_day_bounds(date(2026, 11, 2), DOUALA, 4)[0] == end
    assert study_day_of(start, DOUALA, 4) == date(2026, 11, 1)
    assert study_day_of(end, DOUALA, 4) == date(2026, 11, 2)


def test_study_day_bounds_follow_daylight_saving_time() -> None:
    paris = ZoneInfo("Europe/Paris")
    # Clocks go back at 03:00 on 2026-10-25: the study day starting on the 24th lasts 25 hours.
    start, end = study_day_bounds(date(2026, 10, 24), paris, 4)
    assert (end - start).total_seconds() == 25 * 3600


def test_naive_instant_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        study_day_of(datetime(2026, 11, 2, 2, 0), DOUALA, 4)  # noqa: DTZ001
