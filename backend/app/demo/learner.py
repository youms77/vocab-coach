"""Simulated learner for the demo history (D-034). Pure Python: draws from an injected generator.

p(success) = retrievability x term factor x direction factor, bounded. A failure is Again; a
success is Hard, Good or Easy with weights that depend on retrievability. About 5 % of proposed
ratings are changed by one step by the "user". Response times are log-normal around the default
durations of D-028, slower after a failure.
"""

import math
import random
from dataclasses import dataclass

from app.domain.durations import (
    DISCOVERY_SECONDS,
    ORAL_ANSWER_SECONDS,
    ORAL_EXERCISE_TYPES,
    PRODUCTIVE_TYPED_CARD_SECONDS,
    RECEPTIVE_CARD_SECONDS,
)
from app.domain.enums import CardDirection, SrsState
from app.domain.srs import Rating

# Provisional exercise types (SPEC module C), by direction and card maturity. M4 owns the real
# list; this is the only place the demo names them.
DEMO_EXERCISE_TYPES: dict[CardDirection, dict[str, tuple[str, ...]]] = {
    CardDirection.RECEPTIVE: {
        "young": ("recognition_in_sentence",),
        "mature": ("recognition_in_sentence", "listening_comprehension"),
    },
    CardDirection.PRODUCTIVE: {
        "young": ("typed_recall", "gap_fill"),
        "mature": ("sentence_production", "spoken_answer"),
    },
}
MATURE_STABILITY_DAYS = 21.0

# Productive recall is harder than recognition.
DIRECTION_FACTOR = {CardDirection.RECEPTIVE: 1.0, CardDirection.PRODUCTIVE: 0.96}
# Success of a learning or relearning step (fsrs gives no useful retrievability within a day).
STEP_SUCCESS = 0.85
P_MIN, P_MAX = 0.05, 0.98
# Latent term difficulty, drawn once per term.
TERM_FACTOR_RANGE = (0.92, 1.06)
RATING_CHANGE_SHARE = 0.05
LOG_SIGMA = 0.35
FAILURE_SLOWDOWN = 1.6


@dataclass(frozen=True)
class ReviewOutcome:
    final_rating: Rating
    auto_rating: Rating
    response_time_ms: int
    exercise_type: str

    @property
    def failed(self) -> bool:
        return self.final_rating == Rating.AGAIN


class Learner:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._term_factors: dict[int, float] = {}

    def term_factor(self, item_id: int) -> float:
        """Latent ease of a term, drawn the first time the term is seen."""
        if item_id not in self._term_factors:
            self._term_factors[item_id] = self._rng.uniform(*TERM_FACTOR_RANGE)
        return self._term_factors[item_id]

    def success_probability(
        self,
        item_id: int,
        direction: CardDirection,
        state: SrsState,
        retrievability: float | None,
    ) -> float:
        base = retrievability if state == SrsState.REVIEW and retrievability is not None else None
        if base is None:
            base = STEP_SUCCESS
        p = base * self.term_factor(item_id) * DIRECTION_FACTOR[direction]
        return min(P_MAX, max(P_MIN, p))

    def exercise_type(self, direction: CardDirection, stability: float | None) -> str:
        mature = stability is not None and stability >= MATURE_STABILITY_DAYS
        return self._rng.choice(DEMO_EXERCISE_TYPES[direction]["mature" if mature else "young"])

    def review(
        self,
        item_id: int,
        direction: CardDirection,
        state: SrsState,
        stability: float | None,
        retrievability: float | None,
    ) -> ReviewOutcome:
        exercise = self.exercise_type(direction, stability)
        p = self.success_probability(item_id, direction, state, retrievability)
        rating = self._success_rating(retrievability) if self._rng.random() < p else Rating.AGAIN
        return ReviewOutcome(
            final_rating=rating,
            auto_rating=self._proposed_rating(rating),
            response_time_ms=self._response_ms(direction, exercise, rating == Rating.AGAIN),
            exercise_type=exercise,
        )

    def initial_rating(self, item_id: int, direction: CardDirection) -> Rating:
        """Rating given at the end of a discovery (the first look at the card)."""
        p = self.success_probability(item_id, direction, SrsState.NEW, None)
        return self._success_rating(None) if self._rng.random() < p else Rating.AGAIN

    def discovery_ms(self) -> int:
        return self._lognormal_ms(DISCOVERY_SECONDS)

    def _success_rating(self, retrievability: float | None) -> Rating:
        r = 0.85 if retrievability is None else retrievability
        if r >= 0.9:
            weights = (0.10, 0.60, 0.30)
        elif r >= 0.75:
            weights = (0.20, 0.70, 0.10)
        else:
            weights = (0.40, 0.55, 0.05)
        return self._rng.choices((Rating.HARD, Rating.GOOD, Rating.EASY), weights=weights)[0]

    def _proposed_rating(self, final: Rating) -> Rating:
        """What the app proposed; the user changed it by one step in ~5 % of reviews."""
        if self._rng.random() >= RATING_CHANGE_SHARE:
            return final
        step = self._rng.choice((-1, 1))
        if not Rating.AGAIN <= final + step <= Rating.EASY:
            step = -step
        return Rating(final + step)

    def _response_ms(self, direction: CardDirection, exercise: str, failed: bool) -> int:
        if exercise in ORAL_EXERCISE_TYPES:
            median = ORAL_ANSWER_SECONDS
        elif direction == CardDirection.RECEPTIVE:
            median = RECEPTIVE_CARD_SECONDS
        else:
            median = PRODUCTIVE_TYPED_CARD_SECONDS
        return self._lognormal_ms(median * (FAILURE_SLOWDOWN if failed else 1.0))

    def _lognormal_ms(self, median_seconds: float) -> int:
        return round(1000 * self._rng.lognormvariate(math.log(median_seconds), LOG_SIGMA))


def poisson(rng: random.Random, mean: float) -> int:
    """Poisson draw (Knuth's method; the means used here are small)."""
    if mean <= 0:
        return 0
    limit, k, product = math.exp(-mean), 0, rng.random()
    while product > limit:
        k += 1
        product *= rng.random()
    return k
