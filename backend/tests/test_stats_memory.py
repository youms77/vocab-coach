"""Memory statistics on hand-built cases (M9.a); expected values written by hand."""

from datetime import UTC, date, datetime, timedelta

from app.domain.stats.common import Granularity, Period
from app.domain.stats.memory import (
    CardFact,
    RetentionChange,
    ReviewFact,
    calibration,
    lapses,
    observed_retention,
    rating_agreement,
    stability_distribution,
    success_by_exercise,
    time_to_consolidation,
)
from tests.test_stats_common import douala_day

DAY = date(2026, 8, 20)
PERIOD = Period(date(2026, 8, 19), date(2026, 8, 21))


def at(day: date = DAY, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, 18, minute, tzinfo=UTC)


_ids = iter(range(1, 10_000))


def review(
    rating: int,
    *,
    state: str = "review",
    direction: str = "productive",
    exercise: str = "typed_recall",
    when: datetime | None = None,
    item: int = 1,
    auto: int | None = None,
    predicted: float | None = None,
) -> ReviewFact:
    rid = next(_ids)
    return ReviewFact(
        rid, item * 10 + (direction == "receptive"), item, direction, when or at(minute=rid % 60),
        exercise, state, rating, auto, predicted,
    )  # fmt: skip


def retention(reviews, changes=(), granularity=Granularity.DAY, default=0.9):  # noqa: ANN001, ANN201
    return observed_retention(reviews, douala_day, PERIOD, granularity, list(changes), default)


def test_nine_successes_out_of_ten_review_reviews_is_0_9() -> None:
    reviews = [review(3) for _ in range(8)] + [review(2), review(1)]
    # Excluded: a learning step, a relearning step, a new card, a module G reinforcement.
    reviews += [
        review(3, state="learning"),
        review(1, state="relearning"),
        review(3, state="new"),
        review(1, exercise="consolidation_misuse"),
    ]
    found = retention(reviews)
    assert (found.all.value, found.all.successes, found.all.n) == (0.9, 9, 10)
    assert found.productive.value == 0.9
    assert found.receptive.n == 0 and found.receptive.value is None
    day = next(b for b in found.buckets if b.key == DAY)
    assert (day.all.value, day.target) == (0.9, 0.9)


def test_under_ten_reviews_retention_is_insufficient() -> None:
    found = retention([review(3) for _ in range(9)])
    assert found.all.value is None and found.all.insufficient and found.all.n == 9


def test_the_target_changes_in_the_middle_of_the_period() -> None:
    first, second = date(2026, 8, 19), date(2026, 8, 21)
    reviews = [review(3, when=at(first)) for _ in range(4)] + [
        review(3, when=at(second)) for _ in range(6)
    ]
    change = RetentionChange(datetime(2026, 8, 20, 12, tzinfo=UTC), 0.85)
    found = retention(reviews, [change])
    by_day = {b.key: b.target for b in found.buckets}
    assert by_day == {first: 0.9, DAY: None, second: 0.85}
    # Mean over the ten reviews: (4 x 0.90 + 6 x 0.85) / 10.
    assert found.target == 0.87


def test_retention_by_direction() -> None:
    reviews = [review(3, direction="receptive") for _ in range(10)] + [
        review(1, direction="productive") for _ in range(10)
    ]
    found = retention(reviews)
    assert (found.receptive.value, found.productive.value, found.all.value) == (1.0, 0.0, 0.5)


def test_a_review_at_0330_in_douala_counts_for_the_previous_day() -> None:
    late = datetime(2026, 8, 20, 2, 30, tzinfo=UTC)  # 03:30 in Douala
    found = retention([review(3, when=late)])
    by_day = {b.key: b.all.n for b in found.buckets}
    assert by_day == {date(2026, 8, 19): 1, DAY: 0, date(2026, 8, 21): 0}


def test_calibration_bins_by_predicted_recall() -> None:
    reviews = [review(3, predicted=0.92) for _ in range(9)] + [review(1, predicted=0.98)]
    reviews += [
        review(1, predicted=0.55),
        review(3, predicted=1.0),
        review(3, state="learning", predicted=0.95),
    ]
    bins = {b.low: b for b in calibration(reviews, douala_day, PERIOD)}
    assert len(bins) == 10
    top = bins[0.9]
    # 1.0 falls in the last bin; the learning step is left out.
    assert (top.observed.successes, top.observed.n, top.observed.value) == (10, 11, 0.909091)
    assert top.predicted == 0.932727  # (9 x 0.92 + 0.98 + 1.0) / 11 = 10.26 / 11
    assert (bins[0.5].observed.n, bins[0.5].observed.value) == (1, None)
    assert bins[0.0].predicted is None


def test_success_by_exercise_type_counts_every_review() -> None:
    reviews = [review(3, exercise="gap_fill", state="learning") for _ in range(6)]
    reviews += [review(1, exercise="gap_fill") for _ in range(4)]
    reviews += [review(3, exercise="recognition")]
    reviews += [review(1, exercise="consolidation_misuse")]
    found = {e.exercise_type: e.success for e in success_by_exercise(reviews, douala_day, PERIOD)}
    assert set(found) == {"gap_fill", "recognition"}
    assert (found["gap_fill"].value, found["gap_fill"].n) == (0.6, 10)
    assert (found["recognition"].value, found["recognition"].n) == (None, 1)


def test_rating_agreement() -> None:
    reviews = [review(3, auto=3) for _ in range(7)] + [
        review(4, auto=3),
        review(2, auto=3),
        review(3, auto=1),
    ]
    reviews += [review(3)]  # self-graded: no proposed rating
    found = rating_agreement(reviews, douala_day, PERIOD)
    assert (found.changed.successes, found.changed.n, found.changed.value) == (3, 10, 0.3)
    assert (found.raised, found.lowered) == (2, 1)


def test_lapses_are_again_on_a_review_card() -> None:
    reviews = [review(1, item=1), review(1, item=1), review(1, item=2), review(3, item=2)]
    reviews += [review(1, state="learning", item=3), review(1, state="relearning", item=3)]
    reviews += [review(1, exercise="consolidation_misuse", item=4)]  # counted, like card.lapses
    found = lapses(reviews, douala_day, PERIOD, Granularity.DAY)
    assert found.total == 4
    day = next(b for b in found.buckets if b.key == DAY)
    assert (day.lapses, day.review_state_reviews) == (4, 5)
    assert [(i.item_id, i.lapses) for i in found.top_items] == [(1, 2), (2, 1), (4, 1)]


def test_stability_distribution_of_terms_being_learned() -> None:
    cards = [
        CardFact(1, "productive", "learning", 0.5),
        CardFact(2, "productive", "consolidated", 7.0),
        CardFact(3, "productive", "active", 120.0),
        CardFact(4, "productive", "learning", None),
        CardFact(5, "receptive", "consolidated", 2.0),
        CardFact(6, "receptive", "archived", 30.0),  # archived term: left out
        CardFact(7, "receptive", "known", 30.0),
    ]
    by_direction = {d.direction: d for d in stability_distribution(cards)}
    productive = by_direction["productive"]
    assert (productive.cards, productive.unreviewed, productive.median_days) == (4, 1, 7.0)
    assert [(r.low, r.count) for r in productive.ranges] == [
        (0, 1),
        (1, 0),
        (3, 0),
        (7, 1),
        (21, 0),
        (90, 1),
    ]
    assert by_direction["receptive"].cards == 1


def test_time_before_consolidation() -> None:
    d0 = date(2026, 8, 1)
    first = {
        1: at(d0 + timedelta(days=10)),
        2: at(d0 + timedelta(days=20)),
        3: at(d0 + timedelta(days=5)),  # consolidated before the period: left out
        4: at(DAY),  # no known discovery: left out
    }
    discovered = {1: at(d0), 2: at(d0 + timedelta(days=2)), 3: at(d0)}
    reviews = [
        review(3, item=1, when=at(d0)),
        review(3, item=1, when=at(d0 + timedelta(days=4))),
        review(3, item=1, when=at(d0 + timedelta(days=10))),  # the same instant: counted
        review(3, item=1, when=at(d0 + timedelta(days=12))),  # after: not counted
        review(3, item=2, when=at(d0 + timedelta(days=3))),
    ]
    period = Period(date(2026, 8, 10), date(2026, 8, 21))
    found = time_to_consolidation(first, discovered, reviews, douala_day, period)
    assert [(d.item_id, d.days, d.reviews) for d in found.items] == [(1, 10, 3), (2, 18, 1)]
    assert (found.n, found.days.median, found.days.q1, found.days.q3) == (2, 14.0, 12.0, 16.0)
    assert found.reviews.median == 2.0
    assert [(r.low, r.count) for r in found.distribution if r.count] == [(7, 1), (14, 1)]
