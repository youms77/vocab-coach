"""Internal spaced-repetition interface (docs/SPEC.md module C). Pure Python.

Services only see these types; the FSRS library stays behind `SrsEngine` (see `fsrs_engine.py`),
so the algorithm can be replaced without touching the services.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Protocol

from app.domain.enums import SrsState


class Rating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


@dataclass(frozen=True)
class SrsCardState:
    """Scheduling state of one card, independent of the library.

    `payload` is the engine's own serialised state (for FSRS, `Card.to_dict()`), kept for an exact
    restore; the other fields mirror it in plain columns.
    """

    state: SrsState
    due: datetime
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None
    payload: dict[str, Any] | None = None


class SrsEngine(Protocol):
    """An SRS algorithm configured with a target retention. Never reads the clock."""

    @property
    def algorithm(self) -> str:
        """Name and version stored in `card.srs_algorithm` and `review_log.srs_algorithm`."""
        ...

    def initial_state(self, card_id: int, due: datetime) -> SrsCardState:
        """State of a card that was never reviewed (`new`), due at `due`."""
        ...

    def review(
        self, state: SrsCardState, rating: Rating, at: datetime, duration_ms: int | None
    ) -> SrsCardState:
        """New state after a review at `at`."""
        ...

    def retrievability(self, state: SrsCardState, at: datetime) -> float | None:
        """Predicted recall probability at `at`; None for a card never reviewed."""
        ...


# Builds an engine for a target retention. Services call it at every review, so a retention
# change applies to the next reviews only (due dates already set are not recomputed).
EngineFactory = Callable[[float], SrsEngine]
