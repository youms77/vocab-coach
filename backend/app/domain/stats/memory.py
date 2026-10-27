"""Memory statistics (module I): observed against target retention, calibration, success by exercise
type, agreement of ratings, lapses, stability and time before consolidation. Pure Python.

Everything comes from `review_log` and its before/after snapshot (D-024): FSRS is never replayed and
`fsrs` is never imported. The predicted recall of a review is the `retrievability` the engine stored
in the snapshot when the review was made.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.stats.common import (
    DECIMALS,
    DayOf,
    Granularity,
    Period,
    Quartiles,
    RangeCount,
    Share,
    bucket_key,
    buckets,
    histogram,
    quartiles,
    share,
)

DIRECTIONS = ("receptive", "productive")
REVIEW_STATE = "review"
# Applied by module G to a misused term (D-229): a reinforcement, not an answer to recall.
NOT_A_RECALL = frozenset({"consolidation_misuse"})
SUCCESS_MIN_RATING = 2  # Hard, Good and Easy are successes; Again is a failure
AGAIN = 1

CALIBRATION_BIN = 0.1  # predicted recall in bins of 10 points
STABILITY_EDGES_DAYS = (0, 1, 3, 7, 21, 90)
STABILITY_STATUSES = frozenset({"learning", "consolidated", "active"})
CONSOLIDATION_EDGES_DAYS = (0, 7, 14, 21, 28, 42, 60)
TOP_LAPSED = 10


@dataclass(frozen=True)
class ReviewFact:
    review_id: int
    card_id: int
    item_id: int
    direction: str
    reviewed_at: datetime
    exercise_type: str
    state_before: str
    final_rating: int
    auto_rating: int | None = None
    retrievability: float | None = None  # predicted by the engine at review time


@dataclass(frozen=True)
class RetentionChange:
    """A `setting.changed` event of `target_retention`."""

    at: datetime
    value: float


def is_recall(review: ReviewFact) -> bool:
    """A review that measures recall: the card was in Review before it (no new card, no learning
    or relearning step) and it was an answer (not a consolidation reinforcement)."""
    return review.state_before == REVIEW_STATE and review.exercise_type not in NOT_A_RECALL


def is_success(review: ReviewFact) -> bool:
    return review.final_rating >= SUCCESS_MIN_RATING


def is_lapse(review: ReviewFact) -> bool:
    """D-024: Again on a card in Review (consolidation reinforcements included, like
    `card.lapses`)."""
    return review.state_before == REVIEW_STATE and review.final_rating == AGAIN


def target_at(changes: Sequence[RetentionChange], default: float, instant: datetime) -> float:
    """The target retention in force at `instant` (`changes` sorted by time)."""
    value = default
    for change in changes:
        if change.at > instant:
            break
        value = change.value
    return value


# --- Retention -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RetentionBucket:
    key: date
    first_day: date
    last_day: date
    all: Share
    receptive: Share
    productive: Share
    target: float | None  # mean target over the bucket's recall reviews


@dataclass(frozen=True)
class Retention:
    all: Share
    receptive: Share
    productive: Share
    target: float | None
    buckets: list[RetentionBucket]


def _shares(reviews: Sequence[ReviewFact]) -> tuple[Share, Share, Share]:
    def of(group: Sequence[ReviewFact]) -> Share:
        return share(sum(1 for r in group if is_success(r)), len(group))

    return (
        of(reviews),
        of([r for r in reviews if r.direction == "receptive"]),
        of([r for r in reviews if r.direction == "productive"]),
    )


def _mean_target(
    reviews: Sequence[ReviewFact], changes: Sequence[RetentionChange], default: float
) -> float | None:
    if not reviews:
        return None
    total = sum(target_at(changes, default, r.reviewed_at) for r in reviews)
    return round(total / len(reviews), DECIMALS)


def observed_retention(
    reviews: Iterable[ReviewFact],
    day_of: DayOf,
    period: Period,
    granularity: Granularity,
    changes: Sequence[RetentionChange],
    default_target: float,
) -> Retention:
    changes = sorted(changes, key=lambda c: c.at)
    grouped: dict[date, list[ReviewFact]] = defaultdict(list)
    kept: list[ReviewFact] = []
    for review in reviews:
        day = day_of(review.reviewed_at)
        if day in period and is_recall(review):
            grouped[bucket_key(day, granularity)].append(review)
            kept.append(review)
    rows = []
    for bucket in buckets(period, granularity):
        group = grouped.get(bucket.key, [])
        everything, receptive, productive = _shares(group)
        rows.append(
            RetentionBucket(
                bucket.key,
                bucket.first_day,
                bucket.last_day,
                everything,
                receptive,
                productive,
                _mean_target(group, changes, default_target),
            )
        )
    everything, receptive, productive = _shares(kept)
    return Retention(
        everything, receptive, productive, _mean_target(kept, changes, default_target), rows
    )


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    predicted: float | None  # mean predicted recall of the bin
    observed: Share


def calibration(
    reviews: Iterable[ReviewFact], day_of: DayOf, period: Period
) -> list[CalibrationBin]:
    """Observed success against the recall the engine predicted, in bins of 10 points (recall
    reviews with a stored prediction only)."""
    bins: dict[int, list[ReviewFact]] = defaultdict(list)
    for review in reviews:
        if review.retrievability is None or not is_recall(review):
            continue
        if day_of(review.reviewed_at) not in period:
            continue
        index = min(int(review.retrievability / CALIBRATION_BIN), round(1 / CALIBRATION_BIN) - 1)
        bins[max(index, 0)].append(review)
    found = []
    for index in range(round(1 / CALIBRATION_BIN)):
        group = bins.get(index, [])
        predicted = (
            round(sum(r.retrievability or 0.0 for r in group) / len(group), DECIMALS)
            if group
            else None
        )
        found.append(
            CalibrationBin(
                round(index * CALIBRATION_BIN, 2),
                round((index + 1) * CALIBRATION_BIN, 2),
                predicted,
                share(sum(1 for r in group if is_success(r)), len(group)),
            )
        )
    return found


# --- Exercise types and ratings ------------------------------------------------------------------


@dataclass(frozen=True)
class ExerciseSuccess:
    exercise_type: str
    success: Share


def success_by_exercise(
    reviews: Iterable[ReviewFact], day_of: DayOf, period: Period
) -> list[ExerciseSuccess]:
    """Success rate per exercise type over every review of the period (learning steps included),
    reinforcements of module G excepted. Most frequent type first."""
    totals: Counter[str] = Counter()
    successes: Counter[str] = Counter()
    for review in reviews:
        if review.exercise_type in NOT_A_RECALL or day_of(review.reviewed_at) not in period:
            continue
        totals[review.exercise_type] += 1
        successes[review.exercise_type] += is_success(review)
    order = sorted(totals, key=lambda t: (-totals[t], t))
    return [ExerciseSuccess(t, share(successes[t], totals[t])) for t in order]


@dataclass(frozen=True)
class RatingAgreement:
    """Reviews with a proposed rating: how many the user changed."""

    changed: Share  # successes = reviews whose final rating differs from the proposed one
    raised: int
    lowered: int


def rating_agreement(
    reviews: Iterable[ReviewFact], day_of: DayOf, period: Period
) -> RatingAgreement:
    n = changed = raised = lowered = 0
    for review in reviews:
        if review.auto_rating is None or review.exercise_type in NOT_A_RECALL:
            continue
        if day_of(review.reviewed_at) not in period:
            continue
        n += 1
        if review.final_rating != review.auto_rating:
            changed += 1
            if review.final_rating > review.auto_rating:
                raised += 1
            else:
                lowered += 1
    return RatingAgreement(share(changed, n), raised, lowered)


# --- Lapses --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LapseBucket:
    key: date
    first_day: date
    last_day: date
    lapses: int
    review_state_reviews: int  # reviews of cards in Review: the lapses' denominator


@dataclass(frozen=True)
class LapsedItem:
    item_id: int
    lapses: int


@dataclass(frozen=True)
class Lapses:
    total: int
    buckets: list[LapseBucket]
    top_items: list[LapsedItem]


def lapses(
    reviews: Iterable[ReviewFact], day_of: DayOf, period: Period, granularity: Granularity
) -> Lapses:
    counts: Counter[date] = Counter()
    in_review: Counter[date] = Counter()
    by_item: Counter[int] = Counter()
    for review in reviews:
        day = day_of(review.reviewed_at)
        if day not in period or review.state_before != REVIEW_STATE:
            continue
        key = bucket_key(day, granularity)
        in_review[key] += 1
        if is_lapse(review):
            counts[key] += 1
            by_item[review.item_id] += 1
    rows = [
        LapseBucket(b.key, b.first_day, b.last_day, counts[b.key], in_review[b.key])
        for b in buckets(period, granularity)
    ]
    top = sorted(by_item.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_LAPSED]
    return Lapses(sum(counts.values()), rows, [LapsedItem(i, n) for i, n in top])


# --- Stability -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class CardFact:
    card_id: int
    direction: str
    item_status: str
    stability: float | None  # None: never reviewed


@dataclass(frozen=True)
class StabilityDistribution:
    direction: str
    cards: int
    unreviewed: int
    ranges: list[RangeCount]  # in days
    median_days: float | None


def stability_distribution(cards: Iterable[CardFact]) -> list[StabilityDistribution]:
    """Current stability of the cards of terms being learned (learning, consolidated, active)."""
    values: dict[str, list[float]] = {d: [] for d in DIRECTIONS}
    unreviewed: Counter[str] = Counter()
    for card in cards:
        if card.item_status not in STABILITY_STATUSES or card.direction not in values:
            continue
        if card.stability is None:
            unreviewed[card.direction] += 1
        else:
            values[card.direction].append(card.stability)
    return [
        StabilityDistribution(
            direction,
            len(values[direction]) + unreviewed[direction],
            unreviewed[direction],
            histogram(values[direction], STABILITY_EDGES_DAYS),
            quartiles(values[direction]).median,
        )
        for direction in DIRECTIONS
    ]


# --- Time before consolidation -------------------------------------------------------------------


@dataclass(frozen=True)
class ConsolidationDelay:
    item_id: int
    days: int  # study days from discovery to the first consolidation
    reviews: int  # reviews of the term's cards up to that moment


@dataclass(frozen=True)
class TimeToConsolidation:
    n: int
    days: Quartiles
    reviews: Quartiles
    distribution: list[RangeCount]  # of `days`
    items: list[ConsolidationDelay]


def time_to_consolidation(
    first_consolidated: Mapping[int, datetime],
    discovered: Mapping[int, datetime],
    reviews: Iterable[ReviewFact],
    day_of: DayOf,
    period: Period,
) -> TimeToConsolidation:
    """For every term first consolidated during the period and whose discovery is known: study
    days since the discovery, and reviews of its cards up to the consolidation (included)."""
    wanted = {
        item: at
        for item, at in first_consolidated.items()
        if item in discovered and day_of(at) in period
    }
    review_times: dict[int, list[datetime]] = defaultdict(list)
    for review in reviews:
        if review.item_id in wanted:
            review_times[review.item_id].append(review.reviewed_at)
    delays = []
    for item in sorted(wanted):
        at = wanted[item]
        days = (day_of(at) - day_of(discovered[item])).days
        count = sum(1 for t in review_times[item] if t <= at)
        delays.append(ConsolidationDelay(item, max(days, 0), count))
    day_values = [float(d.days) for d in delays]
    return TimeToConsolidation(
        len(delays),
        quartiles(day_values),
        quartiles([float(d.reviews) for d in delays]),
        histogram(day_values, CONSOLIDATION_EDGES_DAYS),
        delays,
    )
