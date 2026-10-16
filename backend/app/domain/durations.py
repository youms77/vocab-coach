"""Duration estimates for planning (docs/SPEC.md module D). Pure Python.

Defaults are used until there is enough data; observed medians then replace them (D-027).
Reading the data from the database is the job of app/services/durations.py.
"""

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from app.domain.enums import CardDirection

# Default durations, in seconds.
RECEPTIVE_CARD_SECONDS = 15.0  # recognise or understand a term
PRODUCTIVE_TYPED_CARD_SECONDS = 25.0  # recall and type the English term
ORAL_ANSWER_SECONDS = 60.0  # produce a sentence or a spoken answer
DISCOVERY_SECONDS = 150.0  # the whole first-encounter sequence of module B
TARGETED_PRACTICE_BLOCK_SECONDS = 300.0  # one targeted-practice block (module E)
CONSOLIDATION_BLOCK_SECONDS = 600.0  # one consolidation block (module G)

OBSERVATION_WINDOW = timedelta(days=30)
MIN_REVIEWS_FOR_MEDIAN = 30  # per duration class
MIN_DISCOVERIES_FOR_MEDIAN = 10

# Exercise types answered orally. Open set: modules B, C and F add their spoken exercise types.
ORAL_EXERCISE_TYPES = frozenset({"spoken_answer"})


class DurationClass(StrEnum):
    RECEPTIVE = "receptive"
    PRODUCTIVE_TYPED = "productive_typed"
    ORAL = "oral"


def duration_class(direction: CardDirection, exercise_type: str) -> DurationClass:
    """Class of a recorded review, used to group observed response times."""
    if exercise_type in ORAL_EXERCISE_TYPES:
        return DurationClass.ORAL
    if direction == CardDirection.RECEPTIVE:
        return DurationClass.RECEPTIVE
    return DurationClass.PRODUCTIVE_TYPED


@dataclass(frozen=True)
class DurationEstimates:
    """Seconds per unit of work. `observed` names the estimates that come from data."""

    receptive: float = RECEPTIVE_CARD_SECONDS
    productive_typed: float = PRODUCTIVE_TYPED_CARD_SECONDS
    oral: float = ORAL_ANSWER_SECONDS
    discovery: float = DISCOVERY_SECONDS
    targeted_practice_block: float = TARGETED_PRACTICE_BLOCK_SECONDS
    consolidation_block: float = CONSOLIDATION_BLOCK_SECONDS
    observed: frozenset[str] = field(default=frozenset())

    def for_due_card(self, direction: CardDirection) -> float:
        """Planned time for a due card. The exercise itself is chosen at review time (M4), so the
        estimate goes by direction: receptive, or typed productive recall."""
        return self.receptive if direction == CardDirection.RECEPTIVE else self.productive_typed

    @property
    def average_card(self) -> float:
        return (self.receptive + self.productive_typed) / 2


def median_if_enough(values: Sequence[float], minimum: int) -> float | None:
    """Median of `values` when there are at least `minimum`, else None (the default applies)."""
    return statistics.median(values) if len(values) >= minimum else None


def estimate_durations(
    review_samples: Iterable[tuple[DurationClass, float]],
    discovery_samples: Iterable[float],
) -> DurationEstimates:
    """Estimates from observed seconds: reviews by class, and whole discoveries."""
    by_class: dict[DurationClass, list[float]] = {c: [] for c in DurationClass}
    for duration_cls, seconds in review_samples:
        by_class[duration_cls].append(seconds)
    defaults = DurationEstimates()
    values: dict[str, float] = {}
    for duration_cls, samples in by_class.items():
        median = median_if_enough(samples, MIN_REVIEWS_FOR_MEDIAN)
        if median is not None:
            values[duration_cls.value] = median
    discovery = median_if_enough(list(discovery_samples), MIN_DISCOVERIES_FOR_MEDIAN)
    if discovery is not None:
        values["discovery"] = discovery
    return DurationEstimates(
        receptive=values.get("receptive", defaults.receptive),
        productive_typed=values.get("productive_typed", defaults.productive_typed),
        oral=values.get("oral", defaults.oral),
        discovery=values.get("discovery", defaults.discovery),
        observed=frozenset(values),
    )
