"""`SrsEngine` implemented with the `fsrs` library (6.x). The only module that imports `fsrs`.

Library facts this adapter relies on (fsrs 6.3.2, read from the source, see D-012 and D-022):
- there is no New state: our `new` maps to Learning, step 0;
- `review_card` requires `tzinfo == timezone.utc` exactly, so instants are normalised first;
- `Card()` reads the clock when `card_id` or `due` is missing, so both are always passed;
- the library fuzzes intervals with the module-global `random.random`, which cannot be seeded
  without touching global state. Library fuzzing is therefore off, and this adapter applies the same
  fuzz ranges with an injected `random.Random` (reproducible simulations, deterministic tests).
"""

import math
import random
from datetime import datetime, timedelta
from importlib.metadata import version

from fsrs import Card, Scheduler, State
from fsrs import Rating as FsrsRating

from app.domain.enums import SrsState
from app.domain.srs import Rating, SrsCardState, SrsEngine
from app.domain.study_day import as_utc

ALGORITHM = f"fsrs-{version('fsrs')}"

# Library defaults, written out so a library upgrade cannot change them silently.
LEARNING_STEPS = (timedelta(minutes=1), timedelta(minutes=10))
RELEARNING_STEPS = (timedelta(minutes=10),)
MAXIMUM_INTERVAL_DAYS = 36500

# (start, end, factor) in days: same ranges as fsrs 6.3.2 `FUZZ_RANGES`.
FUZZ_RANGES = ((2.5, 7.0, 0.15), (7.0, 20.0, 0.10), (20.0, math.inf, 0.05))

_TO_FSRS = {
    SrsState.NEW: State.Learning,
    SrsState.LEARNING: State.Learning,
    SrsState.REVIEW: State.Review,
    SrsState.RELEARNING: State.Relearning,
}
_FROM_FSRS = {
    State.Learning: SrsState.LEARNING,
    State.Review: SrsState.REVIEW,
    State.Relearning: SrsState.RELEARNING,
}


def fuzz_bounds(interval_days: int, maximum: int = MAXIMUM_INTERVAL_DAYS) -> tuple[int, int]:
    """Smallest and largest fuzzed interval for a computed interval (same formula as fsrs)."""
    delta = 1.0
    for start, end, factor in FUZZ_RANGES:
        delta += factor * max(min(float(interval_days), end) - start, 0.0)
    low = max(2, round(interval_days - delta))
    high = min(round(interval_days + delta), maximum)
    return min(low, high), high


def fuzzed_interval(interval: timedelta, rng: random.Random) -> timedelta:
    """Random whole-day interval within `fuzz_bounds`; intervals under 2.5 days are unchanged."""
    if interval.days < 2.5:
        return interval
    low, high = fuzz_bounds(interval.days)
    return timedelta(days=rng.randint(low, high))


class FsrsEngine:
    def __init__(
        self,
        desired_retention: float = 0.9,
        *,
        fuzz: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self._scheduler = Scheduler(
            desired_retention=desired_retention,
            learning_steps=LEARNING_STEPS,
            relearning_steps=RELEARNING_STEPS,
            maximum_interval=MAXIMUM_INTERVAL_DAYS,
            enable_fuzzing=False,
        )
        self._fuzz = fuzz
        # Scheduling jitter, not security: a non-cryptographic generator is the right tool.
        self._rng = rng if rng is not None else random.Random()  # noqa: S311

    @property
    def algorithm(self) -> str:
        return ALGORITHM

    def initial_state(self, card_id: int, due: datetime) -> SrsCardState:
        due = as_utc(due)
        card = Card(card_id=card_id, state=State.Learning, step=0, due=due)
        return SrsCardState(state=SrsState.NEW, due=due, step=0, payload=dict(card.to_dict()))

    def review(
        self, state: SrsCardState, rating: Rating, at: datetime, duration_ms: int | None
    ) -> SrsCardState:
        at = as_utc(at)
        card, _log = self._scheduler.review_card(
            self._to_card(state), FsrsRating(int(rating)), at, duration_ms
        )
        if self._fuzz and card.state == State.Review:
            card.due = at + fuzzed_interval(card.due - at, self._rng)
        return self._from_card(card)

    def retrievability(self, state: SrsCardState, at: datetime) -> float | None:
        if state.state == SrsState.NEW or state.last_review is None:
            return None
        return self._scheduler.get_card_retrievability(self._to_card(state), as_utc(at))

    @staticmethod
    def _to_card(state: SrsCardState) -> Card:
        if state.payload is not None:
            return Card.from_dict(state.payload)
        # Rows written without a payload (hand-built test or demo rows): rebuild from columns.
        return Card(
            card_id=0,
            state=_TO_FSRS[state.state],
            step=0 if state.state == SrsState.NEW else state.step,
            stability=state.stability,
            difficulty=state.difficulty,
            due=as_utc(state.due),
            last_review=as_utc(state.last_review) if state.last_review else None,
        )

    @staticmethod
    def _from_card(card: Card) -> SrsCardState:
        return SrsCardState(
            state=_FROM_FSRS[card.state],
            due=as_utc(card.due),
            step=card.step,
            stability=card.stability,
            difficulty=card.difficulty,
            last_review=as_utc(card.last_review) if card.last_review else None,
            payload=dict(card.to_dict()),
        )


_PRODUCTION_RNG = random.Random()  # noqa: S311 (scheduling jitter, not security)


def default_engine_factory(desired_retention: float) -> SrsEngine:
    """Production engine: FSRS with fuzzing on."""
    return FsrsEngine(desired_retention, rng=_PRODUCTION_RNG)
