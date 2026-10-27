"""Periods, time buckets, rates and quartiles shared by every statistic. Pure Python."""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

# An instant -> its study day (D-014: `timezone` and `day_start_hour`).
DayOf = Callable[[datetime], date]

DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 366
# A rate per 100 words needs at least this many words in its bucket.
MIN_WORDS_FOR_RATE = 100
# A success rate needs at least this many reviews.
MIN_REVIEWS_FOR_RATE = 10
# Rates and shares are rounded for the answer (the counts stay exact).
DECIMALS = 6


class Granularity(StrEnum):
    DAY = "day"
    WEEK = "week"  # ISO weeks, Monday to Sunday, on the study day


class InvalidPeriod(ValueError):
    """`from` after `to`, or a period longer than MAX_PERIOD_DAYS."""


@dataclass(frozen=True)
class Period:
    """Study days `start` to `end`, both included."""

    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.start <= day <= self.end


def make_period(start: date | None, end: date | None, today: date) -> Period:
    """The requested period; by default the last DEFAULT_PERIOD_DAYS study days up to today."""
    end = end or today
    start = start or end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    if start > end:
        raise InvalidPeriod(f"`from` ({start}) is after `to` ({end}).")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise InvalidPeriod(f"A period covers at most {MAX_PERIOD_DAYS} study days.")
    return Period(start, end)


def days_back(today: date, days: int) -> Period:
    """The last `days` study days, today included."""
    return Period(today - timedelta(days=days - 1), today)


@dataclass(frozen=True)
class Bucket:
    """One time bucket: `key` is the day, or the Monday of the ISO week; `first_day` and
    `last_day` are the part of it inside the period."""

    key: date
    first_day: date
    last_day: date


def bucket_key(day: date, granularity: Granularity) -> date:
    if granularity is Granularity.WEEK:
        return day - timedelta(days=day.weekday())
    return day


def buckets(period: Period, granularity: Granularity) -> list[Bucket]:
    """Every bucket of the period, in order, empty ones included."""
    found: dict[date, Bucket] = {}
    day = period.start
    while day <= period.end:
        key = bucket_key(day, granularity)
        known = found.get(key)
        found[key] = Bucket(key, known.first_day if known else day, day)
        day += timedelta(days=1)
    return list(found.values())


@dataclass(frozen=True)
class Rate:
    """Errors per 100 words. `value` is None when `words` is under the threshold."""

    value: float | None
    errors: int
    words: int
    insufficient: bool


def per_100_words(errors: int, words: int, min_words: int = MIN_WORDS_FOR_RATE) -> Rate:
    if words < min_words or words == 0:
        return Rate(None, errors, words, True)
    return Rate(round(100 * errors / words, DECIMALS), errors, words, False)


@dataclass(frozen=True)
class Share:
    """`successes` out of `n`. `value` is None when `n` is under the threshold."""

    value: float | None
    successes: int
    n: int
    insufficient: bool


def share(successes: int, n: int, min_n: int = MIN_REVIEWS_FOR_RATE) -> Share:
    if n < min_n or n == 0:
        return Share(None, successes, n, True)
    return Share(round(successes / n, DECIMALS), successes, n, False)


@dataclass(frozen=True)
class Quartiles:
    """Median and quartiles by linear interpolation between order statistics: the default method
    of `pandas.Series.quantile` and `numpy.quantile`, so the export gives the same values."""

    n: int
    q1: float | None
    median: float | None
    q3: float | None
    minimum: float | None
    maximum: float | None


def quartiles(values: Sequence[float]) -> Quartiles:
    data = sorted(values)
    if not data:
        return Quartiles(0, None, None, None, None, None)
    if len(data) == 1:
        only = float(data[0])
        return Quartiles(1, only, only, only, only, only)
    q1, median, q3 = statistics.quantiles(data, n=4, method="inclusive")
    return Quartiles(
        len(data),
        round(q1, DECIMALS),
        round(median, DECIMALS),
        round(q3, DECIMALS),
        float(data[0]),
        float(data[-1]),
    )


@dataclass(frozen=True)
class RangeCount:
    """How many values fall in [low, high); `high` None means no upper bound."""

    low: float
    high: float | None
    count: int


def histogram(values: Sequence[float], edges: Sequence[float]) -> list[RangeCount]:
    """Counts per range [edges[i], edges[i+1]), the last range open-ended. Values under the first
    edge are counted in the first range."""
    counts = [0] * len(edges)
    for value in values:
        index = 0
        for i, edge in enumerate(edges):
            if value >= edge:
                index = i
        counts[index] += 1
    return [
        RangeCount(edges[i], edges[i + 1] if i + 1 < len(edges) else None, counts[i])
        for i in range(len(edges))
    ]
