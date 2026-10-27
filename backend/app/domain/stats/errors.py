"""Error statistics (module I): normalised rates, errors outside the rates, recurring errors and
lasting trends. Pure Python.

Normalised rate = errors per 100 words produced. Numerator: the existing errors (a deleted error was
a false positive) of a production of kind writing, speaking, transcript_analysis or consolidation,
review sentences and spoken answers included (D-127, D-183). Denominator: the words of the same
kinds, with or without an error. Both fall on the production's study day: a transcript counts on the
day of the conversation (`occurred_on` of `production.recorded` v3+), like its errors (D-134).
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from fractions import Fraction

from app.domain.error_cards import ErrorRow, group_recurring
from app.domain.stats.common import (
    DayOf,
    Granularity,
    Period,
    Rate,
    Share,
    bucket_key,
    buckets,
    per_100_words,
    share,
)

# Productions whose words are the learner's own (shadowing repeats a sentence, a drill fills gaps).
NORMALIZABLE_KINDS = frozenset({"writing", "speaking", "transcript_analysis", "consolidation"})
TRANSCRIPT_KIND = "transcript_analysis"
DRILL_SOURCE = "drill"
RATE_LEVELS = (1, 2)

# Lasting trends: the last DECLINE_WINDOW_DAYS study days (window B) against the ones before (A).
DECLINE_WINDOW_DAYS = 28
DECLINE_RATIO = 0.5
RISE_RATIO = 1.5
MIN_WORDS_PER_WINDOW = 300
MIN_ERRORS = 3
# The share of fixed errors is computed on the categories of this level.
FIXED_SHARE_LEVEL = 2

TOP_RECURRING = 5
RECURRING_EXAMPLES = 2


@dataclass(frozen=True)
class ProductionWords:
    production_id: int
    kind: str
    modality: str
    word_count: int
    created_at: datetime
    occurred_on: date | None = None  # transcript: the day of the conversation, when given


@dataclass(frozen=True)
class ErrorFact:
    error_id: int
    code: str
    source: str
    occurred_at: datetime
    production_id: int | None = None
    production_kind: str | None = None
    review_log_id: int | None = None
    erroneous_text: str = ""
    correction: str = ""
    original_text: str = ""


def production_day(production: ProductionWords, day_of: DayOf) -> date:
    """A transcript counts on the day of the conversation when the user gave it, any other
    production on the study day it was made."""
    if production.kind == TRANSCRIPT_KIND and production.occurred_on is not None:
        return production.occurred_on
    return day_of(production.created_at)


def is_normalizable(error: ErrorFact) -> bool:
    return error.source != DRILL_SOURCE and error.production_kind in NORMALIZABLE_KINDS


class Unnormalized(StrEnum):
    """Why an error stays out of the rates."""

    DRILL = "drill"
    REVIEW = "review"  # a lexical confusion of a typed review answer
    MANUAL = "manual"  # entered by hand, without a production
    OTHER = "other"


def unnormalized_reason(error: ErrorFact) -> Unnormalized:
    if error.source == DRILL_SOURCE:
        return Unnormalized.DRILL
    if error.review_log_id is not None:
        return Unnormalized.REVIEW
    if error.source == "manual" and error.production_id is None:
        return Unnormalized.MANUAL
    return Unnormalized.OTHER


def code_at_level(code: str, level: int) -> str:
    """The category of `code` at `level` (D-016, D-037): its first `level` segments. A code with
    fewer segments is its own category, so every level partitions the errors."""
    return ".".join(code.split(".")[:level])


def code_level(code: str) -> int:
    return code.count(".") + 1


def prefixes(code: str) -> list[str]:
    """`grammar.tense.x` -> `grammar`, `grammar.tense`, `grammar.tense.x`."""
    parts = code.split(".")
    return [".".join(parts[:k]) for k in range(1, len(parts) + 1)]


# --- Rates ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryRate:
    code: str
    level: int
    rate: Rate  # rate.errors: the errors of this category; rate.words: all the words


@dataclass(frozen=True)
class UnnormalizedCount:
    total: int
    by_reason: dict[str, int]


@dataclass(frozen=True)
class ErrorBucket:
    key: date
    first_day: date
    last_day: date
    rate: Rate
    level1: list[CategoryRate]
    level2: list[CategoryRate]
    unnormalized: UnnormalizedCount


@dataclass(frozen=True)
class ErrorRates:
    rate: Rate
    level1: list[CategoryRate]
    level2: list[CategoryRate]
    unnormalized: UnnormalizedCount
    unnormalized_by_category: dict[str, int]  # level 2
    buckets: list[ErrorBucket]


def _category_rates(
    errors: Sequence[ErrorFact], words: int, level: int, codes: Sequence[str]
) -> list[CategoryRate]:
    counts = Counter(code_at_level(e.code, level) for e in errors)
    return [CategoryRate(code, level, per_100_words(counts[code], words)) for code in codes]


def _ordered_codes(errors: Sequence[ErrorFact], level: int) -> list[str]:
    counts = Counter(code_at_level(e.code, level) for e in errors)
    return [code for code, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _unnormalized(errors: Iterable[ErrorFact]) -> UnnormalizedCount:
    counts = Counter(unnormalized_reason(e).value for e in errors)
    by_reason = {reason.value: counts.get(reason.value, 0) for reason in Unnormalized}
    return UnnormalizedCount(sum(counts.values()), by_reason)


def error_rates(
    productions: Iterable[ProductionWords],
    errors: Iterable[ErrorFact],
    day_of: DayOf,
    period: Period,
    granularity: Granularity,
) -> ErrorRates:
    """Rates per 100 words for the period and per bucket, overall and per category (levels 1, 2).
    Every bucket lists the same categories (those with an error in the period), zeros included."""
    words_by_key: dict[date, int] = defaultdict(int)
    total_words = 0
    for production in productions:
        if production.kind not in NORMALIZABLE_KINDS:
            continue
        day = production_day(production, day_of)
        if day in period:
            words_by_key[bucket_key(day, granularity)] += production.word_count
            total_words += production.word_count

    counted: dict[date, list[ErrorFact]] = defaultdict(list)
    outside: dict[date, list[ErrorFact]] = defaultdict(list)
    all_counted: list[ErrorFact] = []
    all_outside: list[ErrorFact] = []
    for error in errors:
        day = day_of(error.occurred_at)
        if day not in period:
            continue
        key = bucket_key(day, granularity)
        if is_normalizable(error):
            counted[key].append(error)
            all_counted.append(error)
        else:
            outside[key].append(error)
            all_outside.append(error)

    codes = {level: _ordered_codes(all_counted, level) for level in RATE_LEVELS}
    rows = []
    for bucket in buckets(period, granularity):
        key_errors = counted.get(bucket.key, [])
        words = words_by_key.get(bucket.key, 0)
        rows.append(
            ErrorBucket(
                key=bucket.key,
                first_day=bucket.first_day,
                last_day=bucket.last_day,
                rate=per_100_words(len(key_errors), words),
                level1=_category_rates(key_errors, words, 1, codes[1]),
                level2=_category_rates(key_errors, words, 2, codes[2]),
                unnormalized=_unnormalized(outside.get(bucket.key, [])),
            )
        )
    by_category = Counter(code_at_level(e.code, 2) for e in all_outside)
    return ErrorRates(
        rate=per_100_words(len(all_counted), total_words),
        level1=_category_rates(all_counted, total_words, 1, codes[1]),
        level2=_category_rates(all_counted, total_words, 2, codes[2]),
        unnormalized=_unnormalized(all_outside),
        unnormalized_by_category=dict(sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))),
        buckets=rows,
    )


# --- Recurring errors ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RecurringError:
    key: str
    erroneous_text: str
    correction: str
    category: str
    count: int
    first_at: datetime
    last_at: datetime
    examples: list[str]  # `original_text` of the latest occurrences
    has_card: bool


def top_recurring(
    errors: Iterable[ErrorFact],
    day_of: DayOf,
    period: Period,
    carded_keys: set[str],
    limit: int = TOP_RECURRING,
) -> list[RecurringError]:
    """The most frequent recurring errors of the period, with the grouping key of the suggestions
    (D-164); drill errors are left out (D-137)."""
    facts = [e for e in errors if e.source != DRILL_SOURCE and day_of(e.occurred_at) in period]
    by_id = {e.error_id: e for e in facts}
    rows = [
        ErrorRow(e.error_id, e.erroneous_text, e.correction, e.code, e.occurred_at) for e in facts
    ]
    found = []
    for group in group_recurring(rows)[:limit]:
        examples: list[str] = []
        for error_id in group.error_ids:
            text = by_id[error_id].original_text.strip()
            if text and text not in examples:
                examples.append(text)
            if len(examples) == RECURRING_EXAMPLES:
                break
        found.append(
            RecurringError(
                key=group.key,
                erroneous_text=group.erroneous_text,
                correction=group.correction,
                category=group.category_code,
                count=group.count,
                first_at=group.first_at,
                last_at=group.last_at,
                examples=examples,
                has_card=group.key in carded_keys,
            )
        )
    return found


# --- Lasting trends ------------------------------------------------------------------------------


class TrendStatus(StrEnum):
    DECLINING = "declining"
    RISING = "rising"
    STABLE = "stable"
    INSUFFICIENT = "insufficient"


def trend_windows(today: date) -> tuple[Period, Period]:
    """(A, B): B is the last DECLINE_WINDOW_DAYS study days up to today, A the ones before."""
    b_start = today - timedelta(days=DECLINE_WINDOW_DAYS - 1)
    a_start = b_start - timedelta(days=DECLINE_WINDOW_DAYS)
    return Period(a_start, b_start - timedelta(days=1)), Period(b_start, today)


def classify_trend(errors_a: int, words_a: int, errors_b: int, words_b: int) -> TrendStatus:
    """Exact comparison of the rates (fractions, so a rate at exactly DECLINE_RATIO x A declines).

    - insufficient: a window has fewer than MIN_WORDS_PER_WINDOW words, or both windows have fewer
      than MIN_ERRORS errors (nothing to compare);
    - declining: A has at least MIN_ERRORS errors and rate(B) <= DECLINE_RATIO x rate(A);
    - rising: B has at least MIN_ERRORS errors and rate(B) >= RISE_RATIO x rate(A);
    - stable otherwise.
    """
    if words_a < MIN_WORDS_PER_WINDOW or words_b < MIN_WORDS_PER_WINDOW:
        return TrendStatus.INSUFFICIENT
    rate_a = Fraction(errors_a, words_a)
    rate_b = Fraction(errors_b, words_b)
    if errors_a >= MIN_ERRORS and rate_b <= Fraction(str(DECLINE_RATIO)) * rate_a:
        return TrendStatus.DECLINING
    if errors_b >= MIN_ERRORS and rate_b >= Fraction(str(RISE_RATIO)) * rate_a:
        return TrendStatus.RISING
    if errors_a < MIN_ERRORS and errors_b < MIN_ERRORS:
        return TrendStatus.INSUFFICIENT
    return TrendStatus.STABLE


@dataclass(frozen=True)
class Trend:
    code: str
    level: int
    status: TrendStatus
    window_a: Rate
    window_b: Rate
    ratio: float | None  # rate(B) / rate(A); None when rate(A) is 0 or a window lacks words


@dataclass(frozen=True)
class Trends:
    window_a: Period
    window_b: Period
    words_a: int
    words_b: int
    by_status: dict[str, list[Trend]]
    # Share of the errors of window A that belong to level-2 categories in lasting decline.
    fixed_share: Share


def _window_words(
    productions: Iterable[ProductionWords], day_of: DayOf, a: Period, b: Period
) -> tuple[int, int]:
    words_a = words_b = 0
    for production in productions:
        if production.kind not in NORMALIZABLE_KINDS:
            continue
        day = production_day(production, day_of)
        if day in a:
            words_a += production.word_count
        elif day in b:
            words_b += production.word_count
    return words_a, words_b


def _trend(code: str, level: int, ea: int, wa: int, eb: int, wb: int) -> Trend:
    status = classify_trend(ea, wa, eb, wb)
    ratio = None
    if wa >= MIN_WORDS_PER_WINDOW and wb >= MIN_WORDS_PER_WINDOW and ea > 0:
        ratio = round(float(Fraction(eb, wb) / Fraction(ea, wa)), 6)
    return Trend(
        code=code,
        level=level,
        status=status,
        window_a=per_100_words(ea, wa, MIN_WORDS_PER_WINDOW),
        window_b=per_100_words(eb, wb, MIN_WORDS_PER_WINDOW),
        ratio=ratio,
    )


def error_trends(
    productions: Iterable[ProductionWords],
    errors: Iterable[ErrorFact],
    day_of: DayOf,
    today: date,
) -> Trends:
    """The status of every category (all levels) that has an error in window A or B."""
    productions = list(productions)
    a, b = trend_windows(today)
    words_a, words_b = _window_words(productions, day_of, a, b)
    in_a: Counter[str] = Counter()
    in_b: Counter[str] = Counter()
    partition_a: Counter[str] = Counter()
    partition_b: Counter[str] = Counter()
    for error in errors:
        if not is_normalizable(error):
            continue
        day = day_of(error.occurred_at)
        if day in a:
            in_a.update(prefixes(error.code))
            partition_a[code_at_level(error.code, FIXED_SHARE_LEVEL)] += 1
        elif day in b:
            in_b.update(prefixes(error.code))
            partition_b[code_at_level(error.code, FIXED_SHARE_LEVEL)] += 1

    by_status: dict[str, list[Trend]] = {status.value: [] for status in TrendStatus}
    for code in sorted(set(in_a) | set(in_b), key=lambda c: (code_level(c), c)):
        trend = _trend(code, code_level(code), in_a[code], words_a, in_b[code], words_b)
        by_status[trend.status.value].append(trend)

    fixed = sum(
        count
        for code, count in partition_a.items()
        if classify_trend(count, words_a, partition_b[code], words_b) is TrendStatus.DECLINING
    )
    total_a = sum(partition_a.values())
    enough = words_a >= MIN_WORDS_PER_WINDOW and words_b >= MIN_WORDS_PER_WINDOW
    fixed_share = share(fixed, total_a, 1) if enough else Share(None, fixed, total_a, True)
    return Trends(a, b, words_a, words_b, by_status, fixed_share)
