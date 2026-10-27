"""Periods, buckets, rates and quartiles of the statistics (M9.a); expected values by hand."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.stats.common import (
    Granularity,
    InvalidPeriod,
    Period,
    buckets,
    histogram,
    make_period,
    per_100_words,
    quartiles,
    share,
)
from app.domain.study_day import study_day_of

DOUALA = ZoneInfo("Africa/Douala")


def douala_day(instant: datetime) -> date:
    return study_day_of(instant, DOUALA, 4)


def test_default_period_is_the_last_30_study_days() -> None:
    assert make_period(None, None, date(2026, 9, 1)) == Period(date(2026, 8, 3), date(2026, 9, 1))


def test_from_after_to_is_refused() -> None:
    with pytest.raises(InvalidPeriod):
        make_period(date(2026, 9, 2), date(2026, 9, 1), date(2026, 9, 1))


def test_366_days_pass_and_367_are_refused() -> None:
    assert make_period(date(2025, 9, 1), date(2026, 9, 1), date(2026, 9, 1)).days == 366
    with pytest.raises(InvalidPeriod):
        make_period(date(2025, 8, 31), date(2026, 9, 1), date(2026, 9, 1))


def test_a_review_at_0330_in_douala_counts_for_the_previous_day() -> None:
    # 03:30 in Douala (UTC+1) is 02:30 UTC; the study day starts at 04:00.
    assert douala_day(datetime(2026, 8, 20, 2, 30, tzinfo=UTC)) == date(2026, 8, 19)
    assert douala_day(datetime(2026, 8, 20, 3, 0, tzinfo=UTC)) == date(2026, 8, 20)


def test_week_buckets_start_on_monday_and_are_clipped_to_the_period() -> None:
    # 2026-08-05 is a Wednesday; 2026-08-17 a Monday.
    found = buckets(Period(date(2026, 8, 5), date(2026, 8, 17)), Granularity.WEEK)
    assert [(b.key, b.first_day, b.last_day) for b in found] == [
        (date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 9)),
        (date(2026, 8, 10), date(2026, 8, 10), date(2026, 8, 16)),
        (date(2026, 8, 17), date(2026, 8, 17), date(2026, 8, 17)),
    ]


def test_day_buckets_include_empty_days() -> None:
    assert len(buckets(Period(date(2026, 8, 1), date(2026, 8, 3)), Granularity.DAY)) == 3


def test_rate_per_100_words_and_its_threshold() -> None:
    rate = per_100_words(3, 600)
    assert (rate.value, rate.errors, rate.words, rate.insufficient) == (0.5, 3, 600, False)
    small = per_100_words(1, 80)
    assert (small.value, small.insufficient, small.words) == (None, True, 80)
    assert per_100_words(0, 100).value == 0.0


def test_share_needs_ten_reviews() -> None:
    assert share(9, 10).value == 0.9
    assert share(8, 9).value is None and share(8, 9).insufficient


def test_quartiles_match_the_linear_method_of_pandas() -> None:
    # pandas.Series([1, 2, 3, 4, 10]).quantile([.25, .5, .75]) -> 2.0, 3.0, 4.0
    q = quartiles([10, 1, 3, 2, 4])
    assert (q.n, q.q1, q.median, q.q3, q.minimum, q.maximum) == (5, 2.0, 3.0, 4.0, 1.0, 10.0)
    # pandas.Series([1, 2, 3, 4]).quantile([.25, .5, .75]) -> 1.75, 2.5, 3.25
    q = quartiles([1, 2, 3, 4])
    assert (q.q1, q.median, q.q3) == (1.75, 2.5, 3.25)
    assert quartiles([]).median is None
    assert quartiles([7]).median == 7.0


def test_histogram_ranges() -> None:
    found = histogram([0, 0.5, 1, 2.9, 3, 100], [0, 1, 3, 7])
    assert [(r.low, r.high, r.count) for r in found] == [
        (0, 1, 2),
        (1, 3, 2),
        (3, 7, 1),
        (7, None, 1),
    ]
