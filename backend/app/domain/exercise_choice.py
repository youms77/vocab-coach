"""Which exercise a due card gets (docs/SPEC.md module C). Pure Python, deterministic.

The type depends on the card's direction and maturity, and on the templates stored for the term:

| Direction | Young (new, learning, relearning, review < 21 days) | Mature (review, >= 21 days) |
|---|---|---|
| receptive | `recognition_in_sentence` | `listening_comprehension` / `recognition_in_sentence` |
| productive | `typed_recall` / `gap_fill` | `sentence_production` / `spoken_answer` |

"a / b" alternates on the parity of `reps` (a when even). When the wanted template is missing,
another template of the same direction is used; with none at all, `self_assessment` (degraded
mode: no stored template, the user grades themselves after the reveal).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain import exercises as ex
from app.domain.enums import CardDirection, SrsState

# Same threshold as the demo's learner (D-034).
MATURE_STABILITY_DAYS = 21.0

_PREFERENCES: dict[tuple[CardDirection, bool], tuple[str, str]] = {
    (CardDirection.RECEPTIVE, False): (ex.RECOGNITION, ex.RECOGNITION),
    (CardDirection.RECEPTIVE, True): (ex.LISTENING, ex.RECOGNITION),
    (CardDirection.PRODUCTIVE, False): (ex.TYPED_RECALL, ex.GAP_FILL),
    (CardDirection.PRODUCTIVE, True): (ex.SENTENCE_PRODUCTION, ex.SPOKEN_ANSWER),
}


@dataclass(frozen=True)
class TemplateRef:
    id: int
    exercise_type: str


@dataclass(frozen=True)
class ExerciseChoice:
    exercise_type: str
    template_id: int | None  # None for `self_assessment`


def is_mature(state: SrsState, stability: float | None) -> bool:
    return state == SrsState.REVIEW and stability is not None and stability >= MATURE_STABILITY_DAYS


def preferred_types(
    direction: CardDirection, state: SrsState, stability: float | None, reps: int
) -> list[str]:
    """Types to try, in order: the alternation for this maturity, then the direction's others."""
    first, second = _PREFERENCES[(direction, is_mature(state, stability))]
    wanted = [first, second] if reps % 2 == 0 else [second, first]
    others = [
        kind
        for kind, (kind_direction, _) in ex.EXERCISE_TYPES.items()
        if kind_direction == direction
    ]
    result: list[str] = []
    for kind in [*wanted, *others]:
        if kind not in result:
            result.append(kind)
    return result


def choose_exercise(
    direction: CardDirection,
    state: SrsState,
    stability: float | None,
    reps: int,
    templates: Sequence[TemplateRef],
) -> ExerciseChoice:
    """The exercise for one review. Several templates of the chosen type: the one at index
    `(reps // 2) % n` by id, so the sentence changes between reviews (`reps % n` would always
    pick the same one, since the type itself alternates on the parity of `reps`)."""
    for kind in preferred_types(direction, state, stability, reps):
        candidates = sorted((t for t in templates if t.exercise_type == kind), key=lambda t: t.id)
        if candidates:
            return ExerciseChoice(kind, candidates[(reps // 2) % len(candidates)].id)
    return ExerciseChoice(ex.SELF_ASSESSMENT, None)
