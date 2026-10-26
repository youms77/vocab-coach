"""Progress and practice statistics on hand-built cases (M9.a2); expected values written by hand."""

from datetime import UTC, date, datetime, timedelta

from app.domain.stats.common import Granularity, Period
from app.domain.stats.errors import ProductionWords
from app.domain.stats.practice import (
    Recording,
    SessionSpan,
    blocks_by_day,
    recorded_speech,
    streaks,
    study_time,
    words_produced,
)
from app.domain.stats.progress import (
    Change,
    LifecycleEvent,
    rebuild,
    replay,
    snapshot,
)
from tests.test_stats_common import douala_day

DAY = date(2026, 8, 20)


def at(day: date, hour: int = 18, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


# --- Funnel --------------------------------------------------------------------------------------


def life(*steps: tuple[int, date, Change, str | None]) -> list[LifecycleEvent]:
    return [
        LifecycleEvent(at(day), order, item, change, status)
        for order, (item, day, change, status) in enumerate(steps, 1)
    ]


def test_snapshot_lists_the_nine_statuses_in_funnel_order() -> None:
    counts = snapshot(["learning", "learning", "triage"])
    assert list(counts) == [
        "queued", "discovering", "learning", "consolidated", "active",
        "triage", "known", "archived", "draft",
    ]  # fmt: skip
    assert (counts["learning"], counts["triage"], counts["active"]) == (2, 1, 0)


def test_the_rebuild_at_the_last_instant_equals_the_snapshot_with_a_merge_and_a_deletion() -> None:
    d1, d2, d3 = date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)
    events = life(
        (1, d1, Change.CREATED, None),
        (1, d1, Change.STATUS, "queued"),
        (2, d1, Change.CREATED, None),
        (2, d1, Change.STATUS, "triage"),
        (3, d1, Change.CREATED, None),
        (3, d1, Change.STATUS, "queued"),
        (1, d2, Change.STATUS, "discovering"),
        (1, d2, Change.STATUS, "learning"),
        (2, d2, Change.REMOVED, None),  # deleted
        (3, d3, Change.REMOVED, None),  # merged into term 1
        (4, d3, Change.CREATED, None),  # still a draft
    )
    # The table now holds terms 1 (learning) and 4 (draft).
    assert snapshot(replay(events).values()) == snapshot(["learning", "draft"])
    found = rebuild(events, douala_day, Period(d1, d3), Granularity.DAY)
    by_day = {b.key: {k: v for k, v in b.counts.items() if v} for b in found}
    assert by_day == {
        d1: {"queued": 2, "triage": 1},
        d2: {"queued": 1, "learning": 1},
        d3: {"learning": 1, "draft": 1},
    }


def test_events_before_the_period_are_applied_and_weeks_close_on_sunday() -> None:
    events = life(
        (1, date(2026, 7, 1), Change.CREATED, None),
        (1, date(2026, 7, 1), Change.STATUS, "active"),
        (2, date(2026, 8, 19), Change.CREATED, None),  # a Wednesday
    )
    found = rebuild(events, douala_day, Period(date(2026, 8, 10), DAY), Granularity.WEEK)
    assert [(b.key, b.counts["active"], b.counts["draft"]) for b in found] == [
        (date(2026, 8, 10), 1, 0),
        (date(2026, 8, 17), 1, 1),
    ]


def test_a_status_change_without_creation_still_counts() -> None:
    events = [LifecycleEvent(at(DAY), 1, 9, Change.STATUS, "known")]
    assert replay(events) == {9: "known"}


# --- Activity blocks -----------------------------------------------------------------------------


def test_a_gap_of_9_min_59_s_continues_a_block_and_10_min_opens_one() -> None:
    t0 = at(DAY, 18)
    instants = [t0, t0 + timedelta(minutes=9, seconds=59), t0 + timedelta(minutes=19, seconds=59)]
    blocks = blocks_by_day(instants, douala_day)[DAY]
    assert [(b.actions, b.seconds) for b in blocks] == [(2, 599 + 60), (1, 60)]


def test_study_time_per_day_and_sessions_apart() -> None:
    t0 = at(DAY, 18)
    instants = [t0, t0 + timedelta(minutes=5), at(DAY, 20)]
    sessions = [SessionSpan(t0, t0 + timedelta(hours=3))]
    period = Period(DAY, DAY + timedelta(days=1))
    found = study_time(instants, sessions, douala_day, period, Granularity.DAY)
    day = found.buckets[0]
    assert (day.seconds, day.blocks, day.actions, day.session_seconds) == (360 + 60, 2, 3, 10800)
    assert (found.seconds, found.session_seconds, found.active_days) == (420, 10800, 1)
    assert found.buckets[1].seconds == 0


def test_an_action_at_0330_in_douala_belongs_to_the_previous_study_day() -> None:
    late = datetime(2026, 8, 21, 2, 30, tzinfo=UTC)
    assert list(blocks_by_day([late], douala_day)) == [DAY]


# --- Streaks -------------------------------------------------------------------------------------


def test_current_and_longest_streak_broken_by_an_empty_day() -> None:
    today = date(2026, 9, 1)
    days = [today - timedelta(days=k) for k in (1, 2, 3)]  # yesterday and the two days before
    days += [today - timedelta(days=k) for k in (5, 6, 7, 8, 9)]  # day -4 is empty
    found = streaks(days, today)
    # Today has no action yet: the streak still ends yesterday.
    assert (found.current, found.longest, found.longest_end) == (3, 5, today - timedelta(days=5))
    assert found.active_days_last_30 == 8
    assert streaks(days + [today], today).current == 4
    assert streaks([today - timedelta(days=2)], today).current == 0
    assert streaks([], today) == streaks([], today) and streaks([], today).longest == 0


# --- Words and speech ----------------------------------------------------------------------------


def test_words_produced_by_modality() -> None:
    productions = [
        ProductionWords(1, "writing", "written", 120, at(DAY)),
        ProductionWords(2, "speaking", "oral", 80, at(DAY)),
        ProductionWords(3, "shadowing", "oral", 0, at(DAY)),
        ProductionWords(4, "drill", "written", 30, at(DAY)),
        ProductionWords(5, "transcript_analysis", "oral", 50, at(DAY), date(2026, 8, 19)),
    ]
    found = words_produced(productions, douala_day, Period(date(2026, 8, 19), DAY), Granularity.DAY)
    assert [(b.key, b.written, b.oral) for b in found] == [
        (date(2026, 8, 19), 0, 50),
        (DAY, 120, 80),
    ]


def test_recorded_speech_by_kind() -> None:
    recordings = [
        Recording("shadowing", at(DAY), 6.5),
        Recording("shadowing", at(DAY), 4.0),
        Recording("speaking", at(DAY), 95.25),
    ]
    found = recorded_speech(recordings, douala_day, Period(DAY, DAY), Granularity.DAY)
    assert (found[0].seconds, found[0].by_kind) == (105.75, {"shadowing": 10.5, "speaking": 95.25})
