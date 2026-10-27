"""Error statistics on hand-built cases (M9.a). Expected values are written here, not recomputed."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.stats.common import Granularity, Period
from app.domain.stats.errors import (
    ErrorFact,
    ProductionWords,
    TrendStatus,
    classify_trend,
    code_at_level,
    error_rates,
    error_trends,
    top_recurring,
    trend_windows,
)
from tests.test_stats_common import douala_day

DAY = date(2026, 8, 20)
PERIOD = Period(date(2026, 8, 19), date(2026, 8, 21))


def at(day: date, hour: int = 18) -> datetime:
    """`hour` o'clock UTC on `day` (19:00 in Douala: inside that study day)."""
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def production(
    pid: int, words: int, kind: str = "writing", day: date = DAY, **kw
) -> ProductionWords:  # noqa: ANN003
    return ProductionWords(pid, kind, kw.pop("modality", "written"), words, at(day), **kw)


def error(
    eid: int, code: str, *, pid: int | None = 1, kind: str | None = "writing", day: date = DAY, **kw
) -> ErrorFact:  # noqa: ANN003
    return ErrorFact(
        eid, code, kw.pop("source", "writing"), kw.pop("occurred_at", at(day)), pid, kind, **kw
    )


def rates(productions, errors, granularity=Granularity.DAY, period=PERIOD):  # noqa: ANN001, ANN201
    return error_rates(productions, errors, douala_day, period, granularity)


def bucket(result, day: date):  # noqa: ANN001, ANN201
    return next(b for b in result.buckets if b.key == day)


# --- Normalised rate -----------------------------------------------------------------------------


def test_three_errors_for_600_words_is_half_an_error_per_100_words() -> None:
    result = rates(
        [production(1, 300), production(2, 300)],  # the second production has no error
        [
            error(1, "grammar.tense.past_simple_vs_present_perfect"),
            error(2, "grammar.article"),
            error(3, "grammar.tense.past_simple_vs_present_perfect"),
        ],
    )
    day = bucket(result, DAY)
    assert (day.rate.value, day.rate.errors, day.rate.words) == (0.5, 3, 600)
    assert result.rate.value == 0.5
    level1 = {c.code: (c.rate.errors, c.rate.value) for c in day.level1}
    assert level1 == {"grammar": (3, 0.5)}
    level2 = {c.code: (c.rate.errors, c.rate.value) for c in day.level2}
    assert level2 == {
        "grammar.tense": (2, pytest.approx(1 / 3, abs=1e-6)),
        "grammar.article": (1, pytest.approx(1 / 6, abs=1e-6)),
    }


def test_a_bucket_of_80_words_is_insufficient() -> None:
    day = bucket(rates([production(1, 80)], [error(1, "grammar.article")]), DAY)
    assert day.rate.value is None and day.rate.insufficient and day.rate.errors == 1
    assert day.level2[0].rate.value is None


def test_drill_errors_stay_out_of_the_rate() -> None:
    result = rates(
        [production(1, 600), production(2, 50, kind="drill")],
        [
            error(1, "grammar.article"),
            error(2, "grammar.article", pid=2, kind="drill", source="drill"),
        ],
    )
    day = bucket(result, DAY)
    assert (day.rate.errors, day.rate.words) == (1, 600)
    assert day.unnormalized.total == 1 and day.unnormalized.by_reason["drill"] == 1
    assert result.unnormalized_by_category == {"grammar.article": 1}


def test_review_confusions_and_manual_errors_are_counted_apart() -> None:
    result = rates(
        [production(1, 600)],
        [
            error(1, "lexis.false_friend", pid=None, kind=None, source="review", review_log_id=7),
            error(2, "grammar.article", pid=None, kind=None, source="manual"),
            # A review sentence checked by the AI is a production: it is in the rate (D-127).
            error(3, "grammar.article", source="review"),
        ],
    )
    assert result.rate.errors == 1
    assert result.unnormalized.by_reason == {"drill": 0, "review": 1, "manual": 1, "other": 0}


def test_a_deleted_error_is_not_counted() -> None:
    # A deleted error no longer has a row: the service never passes it. The rate is unchanged.
    assert rates([production(1, 600)], []).rate.value == 0.0


def test_shadowing_words_are_not_in_the_denominator() -> None:
    result = rates([production(1, 600), production(2, 900, kind="shadowing", modality="oral")], [])
    assert result.rate.words == 600


def test_a_transcript_dated_the_day_before_falls_in_that_day_numerator_and_denominator() -> None:
    previous = DAY - timedelta(days=1)
    pasted = production(1, 400, kind="transcript_analysis", modality="oral", occurred_on=previous)
    # D-134: the transcript's errors are dated at the start of the conversation's study day.
    start_of_previous = datetime(2026, 8, 19, 3, 0, tzinfo=UTC)  # 04:00 in Douala
    found = rates(
        [pasted],
        [
            error(
                1,
                "grammar.article",
                kind="transcript_analysis",
                source="transcript",
                occurred_at=start_of_previous,
            )
        ],
    )
    assert (bucket(found, previous).rate.errors, bucket(found, previous).rate.words) == (1, 400)
    assert (bucket(found, DAY).rate.errors, bucket(found, DAY).rate.words) == (0, 0)


def test_a_transcript_without_its_day_counts_on_the_day_it_was_pasted() -> None:
    found = rates([production(1, 400, kind="transcript_analysis", modality="oral")], [])
    assert bucket(found, DAY).rate.words == 400


def test_a_production_at_0330_in_douala_counts_for_the_previous_study_day() -> None:
    late = ProductionWords(1, "writing", "written", 200, datetime(2026, 8, 20, 2, 30, tzinfo=UTC))
    found = rates(
        [late], [error(1, "grammar.article", occurred_at=datetime(2026, 8, 20, 2, 30, tzinfo=UTC))]
    )
    assert bucket(found, date(2026, 8, 19)).rate.words == 200
    assert bucket(found, date(2026, 8, 19)).rate.errors == 1
    assert bucket(found, DAY).rate.words == 0


def test_week_buckets_add_their_days() -> None:
    period = Period(date(2026, 8, 17), date(2026, 8, 23))  # Monday to Sunday
    found = rates(
        [production(1, 100, day=date(2026, 8, 17)), production(2, 100, day=date(2026, 8, 23))],
        [error(1, "grammar.article", day=date(2026, 8, 23))],
        Granularity.WEEK,
        period,
    )
    assert len(found.buckets) == 1
    assert (found.buckets[0].rate.value, found.buckets[0].rate.words) == (0.5, 200)


def test_level_one_categories_add_up_to_the_total() -> None:
    found = rates(
        [production(1, 1000)],
        [
            error(1, "grammar.article"),
            error(2, "spelling"),
            error(3, "lexis.collocation"),
            error(4, "grammar.preposition.fixed_expression"),
        ],
    )
    assert sum(c.rate.errors for c in found.level1) == found.rate.errors == 4
    assert sum(c.rate.errors for c in found.level2) == 4
    assert {c.code for c in found.level2} == {
        "grammar.article",
        "spelling",
        "lexis.collocation",
        "grammar.preposition",
    }


def test_code_at_level() -> None:
    assert code_at_level("grammar.preposition.fixed_expression", 2) == "grammar.preposition"
    assert code_at_level("spelling", 2) == "spelling"


# --- Recurring errors ----------------------------------------------------------------------------


def test_top_recurring_groups_by_pair_and_leaves_drills_out() -> None:
    errors = [
        error(
            1,
            "grammar.preposition.fixed_expression",
            erroneous_text="in campus",
            correction="on campus",
            original_text="I live in campus.",
            occurred_at=at(DAY, 10),
        ),
        error(
            2,
            "grammar.preposition.fixed_expression",
            erroneous_text="In campus",
            correction="on campus",
            original_text="We met in campus.",
            occurred_at=at(DAY, 12),
        ),
        error(
            3,
            "grammar.preposition.fixed_expression",
            erroneous_text="in campus",
            correction="on campus",
            original_text="We met in campus.",
            occurred_at=at(DAY, 14),
        ),
        error(
            4, "grammar.article", erroneous_text="the", correction="a", source="drill", kind="drill"
        ),
        error(
            5, "grammar.article", erroneous_text="the", correction="a", source="drill", kind="drill"
        ),
        error(6, "grammar.article", erroneous_text="a", correction="an"),
    ]
    found = top_recurring(errors, douala_day, PERIOD, carded_keys={"in campus => on campus"})
    assert len(found) == 1
    first = found[0]
    assert (first.key, first.count, first.category, first.has_card) == (
        "in campus => on campus",
        3,
        "grammar.preposition.fixed_expression",
        True,
    )
    assert first.examples == ["We met in campus.", "I live in campus."]
    assert (first.first_at, first.last_at) == (at(DAY, 10), at(DAY, 14))


# --- Lasting trends ------------------------------------------------------------------------------


def test_trend_windows_are_two_runs_of_28_study_days() -> None:
    a, b = trend_windows(date(2026, 9, 1))
    assert (b.start, b.end) == (date(2026, 8, 5), date(2026, 9, 1))
    assert (a.start, a.end) == (date(2026, 7, 8), date(2026, 8, 4))


@pytest.mark.parametrize(
    ("ea", "wa", "eb", "wb", "expected"),
    [
        (4, 400, 2, 400, TrendStatus.DECLINING),  # exactly 0.5 x A
        (4, 400, 3, 600, TrendStatus.DECLINING),  # 0.5 vs 1.0 per 100 words
        (5, 500, 3, 499, TrendStatus.STABLE),  # just above 0.5 x A
        (2, 400, 0, 400, TrendStatus.INSUFFICIENT),  # only 2 errors in A
        (3, 400, 0, 400, TrendStatus.DECLINING),  # 3 errors in A is enough
        (4, 299, 0, 400, TrendStatus.INSUFFICIENT),  # A under 300 words
        (4, 400, 0, 299, TrendStatus.INSUFFICIENT),  # B under 300 words
        (2, 400, 3, 400, TrendStatus.RISING),  # 1.5 x A exactly, 3 errors in B
        (2, 400, 2, 300, TrendStatus.INSUFFICIENT),  # rate up but 2 errors on each side
        (0, 400, 3, 400, TrendStatus.RISING),  # from nothing to 3 errors
        (4, 400, 5, 400, TrendStatus.STABLE),  # 1.25 x A
    ],
)
def test_trend_status_at_the_bounds(
    ea: int, wa: int, eb: int, wb: int, expected: TrendStatus
) -> None:
    assert classify_trend(ea, wa, eb, wb) is expected


def test_error_trends_cover_every_level_and_the_share_of_fixed_errors() -> None:
    today = date(2026, 9, 1)
    a, b = trend_windows(today)
    day_a, day_b = a.start + timedelta(days=3), b.start + timedelta(days=3)
    productions = [production(1, 400, day=day_a), production(2, 400, day=day_b)]
    fixed = "grammar.preposition.fixed_expression"
    errors = (
        [error(i, fixed, day=day_a) for i in range(1, 5)]  # 4 in A
        + [error(10, fixed, day=day_b)]  # 1 in B: declining
        + [error(i, "grammar.article", day=day_a) for i in range(20, 24)]  # 4 in A
        + [error(i, "grammar.article", day=day_b) for i in range(30, 34)]  # 4 in B: stable
    )
    trends = error_trends(productions, errors, douala_day, today)
    status = {t.code: (t.level, t.status) for group in trends.by_status.values() for t in group}
    assert status[fixed] == (3, TrendStatus.DECLINING)
    assert status["grammar.preposition"] == (2, TrendStatus.DECLINING)
    assert status["grammar.article"] == (2, TrendStatus.STABLE)
    assert status["grammar"] == (1, TrendStatus.STABLE)  # 8 -> 5
    # Level 2: grammar.preposition (4 errors in A) declines, grammar.article (4) does not.
    assert (trends.fixed_share.successes, trends.fixed_share.n, trends.fixed_share.value) == (
        4,
        8,
        0.5,
    )
    declining = trends.by_status["declining"]
    assert [t.code for t in declining] == ["grammar.preposition", fixed]
    assert declining[0].ratio == 0.25 and declining[0].window_a.value == 1.0
