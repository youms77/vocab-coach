"""Practice statistics (module I): study time from the learner's actions, regularity, words
produced, minutes of recorded speech. Pure Python.

Study time is not read from `study_session` (a session can stay open for hours, and many actions
happen outside one): the instants of the learner's actions are sorted per study day, a gap of at
least ACTIVITY_GAP_MINUTES opens a new block, and a block lasts from its first to its last action
plus ACTIVITY_TAIL_SECONDS (the time spent on the last action).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.stats.common import DayOf, Granularity, Period, bucket_key, buckets
from app.domain.stats.errors import NORMALIZABLE_KINDS, ProductionWords, production_day

ACTIVITY_GAP_MINUTES = 10
ACTIVITY_TAIL_SECONDS = 60
STREAK_WINDOW_DAYS = 30


@dataclass(frozen=True)
class Block:
    start: datetime
    end: datetime
    actions: int

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds() + ACTIVITY_TAIL_SECONDS


def blocks_by_day(instants: Iterable[datetime], day_of: DayOf) -> dict[date, list[Block]]:
    """Activity blocks of every study day (a block never spans two study days)."""
    per_day: dict[date, list[datetime]] = defaultdict(list)
    for instant in instants:
        per_day[day_of(instant)].append(instant)
    gap = timedelta(minutes=ACTIVITY_GAP_MINUTES)
    found: dict[date, list[Block]] = {}
    for day, times in per_day.items():
        times.sort()
        blocks: list[Block] = []
        start = last = times[0]
        count = 1
        for instant in times[1:]:
            if instant - last >= gap:
                blocks.append(Block(start, last, count))
                start, count = instant, 0
            last = instant
            count += 1
        blocks.append(Block(start, last, count))
        found[day] = blocks
    return found


@dataclass(frozen=True)
class SessionSpan:
    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class TimeBucket:
    key: date
    first_day: date
    last_day: date
    seconds: float  # from the activity blocks
    blocks: int
    actions: int
    session_seconds: float  # ended `study_session` rows, for comparison only (not added)


@dataclass(frozen=True)
class StudyTime:
    seconds: float
    session_seconds: float
    active_days: int
    buckets: list[TimeBucket]


def study_time(
    instants: Iterable[datetime],
    sessions: Iterable[SessionSpan],
    day_of: DayOf,
    period: Period,
    granularity: Granularity,
) -> StudyTime:
    per_day = blocks_by_day(instants, day_of)
    seconds: dict[date, float] = defaultdict(float)
    block_count: dict[date, int] = defaultdict(int)
    actions: dict[date, int] = defaultdict(int)
    active = 0
    for day, blocks in per_day.items():
        if day not in period:
            continue
        active += 1
        key = bucket_key(day, granularity)
        seconds[key] += sum(b.seconds for b in blocks)
        block_count[key] += len(blocks)
        actions[key] += sum(b.actions for b in blocks)
    session_seconds: dict[date, float] = defaultdict(float)
    for span in sessions:
        day = day_of(span.started_at)
        if day in period:
            session_seconds[bucket_key(day, granularity)] += max(
                0.0, (span.ended_at - span.started_at).total_seconds()
            )
    rows = [
        TimeBucket(
            b.key,
            b.first_day,
            b.last_day,
            seconds[b.key],
            block_count[b.key],
            actions[b.key],
            session_seconds[b.key],
        )  # fmt: skip
        for b in buckets(period, granularity)
    ]
    return StudyTime(sum(seconds.values()), sum(session_seconds.values()), active, rows)


@dataclass(frozen=True)
class Streaks:
    current: int  # ends today, or yesterday while today has no action yet
    longest: int
    longest_end: date | None
    active_days_last_30: int


def streaks(active_days: Iterable[date], today: date) -> Streaks:
    days = {d for d in active_days if d <= today}
    end = today if today in days else today - timedelta(days=1)
    current = 0
    while end - timedelta(days=current) in days:
        current += 1
    longest, longest_end, run, previous = 0, None, 0, None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        if run > longest:
            longest, longest_end = run, day
        previous = day
    window_start = today - timedelta(days=STREAK_WINDOW_DAYS - 1)
    return Streaks(current, longest, longest_end, sum(1 for d in days if d >= window_start))


@dataclass(frozen=True)
class WordsBucket:
    key: date
    first_day: date
    last_day: date
    written: int
    oral: int


def words_produced(
    productions: Iterable[ProductionWords], day_of: DayOf, period: Period, granularity: Granularity
) -> list[WordsBucket]:
    """The learner's own words (the kinds and the date rule of the error rates, D-267)."""
    written: dict[date, int] = defaultdict(int)
    oral: dict[date, int] = defaultdict(int)
    for production in productions:
        if production.kind not in NORMALIZABLE_KINDS:
            continue
        day = production_day(production, day_of)
        if day not in period:
            continue
        target = oral if production.modality == "oral" else written
        target[bucket_key(day, granularity)] += production.word_count
    return [
        WordsBucket(b.key, b.first_day, b.last_day, written[b.key], oral[b.key])
        for b in buckets(period, granularity)
    ]


@dataclass(frozen=True)
class Recording:
    kind: str
    created_at: datetime
    audio_seconds: float


@dataclass(frozen=True)
class SpeechBucket:
    key: date
    first_day: date
    last_day: date
    seconds: float
    by_kind: dict[str, float]


def recorded_speech(
    recordings: Iterable[Recording], day_of: DayOf, period: Period, granularity: Granularity
) -> list[SpeechBucket]:
    """Seconds of every recording (shadowing, free speaking, spoken answers, spoken consolidation),
    per bucket and per production kind."""
    per_kind: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for recording in recordings:
        day = day_of(recording.created_at)
        if day in period:
            per_kind[bucket_key(day, granularity)][recording.kind] += recording.audio_seconds
    found = []
    for b in buckets(period, granularity):
        kinds = {k: round(v, 3) for k, v in sorted(per_kind.get(b.key, {}).items())}
        found.append(
            SpeechBucket(b.key, b.first_day, b.last_day, round(sum(kinds.values()), 3), kinds)
        )
    return found
