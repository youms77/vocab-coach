"""Exercise choice: direction x maturity x available templates (app/domain/exercise_choice.py)."""

import pytest

from app.domain import exercises as ex
from app.domain.enums import CardDirection, SrsState
from app.domain.exercise_choice import (
    MATURE_STABILITY_DAYS,
    ExerciseChoice,
    TemplateRef,
    choose_exercise,
    is_mature,
)

R, P = CardDirection.RECEPTIVE, CardDirection.PRODUCTIVE
ALL = [
    TemplateRef(1, ex.GAP_FILL),
    TemplateRef(2, ex.TYPED_RECALL),
    TemplateRef(3, ex.RECOGNITION),
    TemplateRef(4, ex.LISTENING),
    TemplateRef(5, ex.SENTENCE_PRODUCTION),
    TemplateRef(6, ex.SPOKEN_ANSWER),
]
YOUNG = (SrsState.REVIEW, 5.0)
MATURE = (SrsState.REVIEW, MATURE_STABILITY_DAYS)


def test_maturity_threshold() -> None:
    assert MATURE_STABILITY_DAYS == 21.0
    assert is_mature(SrsState.REVIEW, 21.0)
    assert not is_mature(SrsState.REVIEW, 20.99)
    assert not is_mature(SrsState.REVIEW, None)
    # A relearning card is young whatever its stability.
    assert not is_mature(SrsState.RELEARNING, 40.0)
    assert not is_mature(SrsState.NEW, None)


@pytest.mark.parametrize(
    ("direction", "state", "stability", "reps", "expected"),
    [
        (R, SrsState.NEW, None, 0, ex.RECOGNITION),
        (R, *YOUNG, 1, ex.RECOGNITION),
        (R, *MATURE, 4, ex.LISTENING),
        (R, *MATURE, 5, ex.RECOGNITION),
        (P, SrsState.NEW, None, 0, ex.TYPED_RECALL),
        (P, SrsState.LEARNING, 0.5, 1, ex.GAP_FILL),
        (P, SrsState.RELEARNING, 30.0, 2, ex.TYPED_RECALL),
        (P, *YOUNG, 3, ex.GAP_FILL),
        (P, *MATURE, 6, ex.SENTENCE_PRODUCTION),
        (P, *MATURE, 7, ex.SPOKEN_ANSWER),
    ],
)
def test_all_templates_present(
    direction: CardDirection, state: SrsState, stability: float | None, reps: int, expected: str
) -> None:
    choice = choose_exercise(direction, state, stability, reps, ALL)
    assert choice.exercise_type == expected
    assert choice.template_id == next(t.id for t in ALL if t.exercise_type == expected)


def test_alternation_is_deterministic() -> None:
    first = [choose_exercise(P, *MATURE, reps, ALL).exercise_type for reps in range(6)]
    again = [choose_exercise(P, *MATURE, reps, ALL).exercise_type for reps in range(6)]
    assert first == again
    assert first == [ex.SENTENCE_PRODUCTION, ex.SPOKEN_ANSWER] * 3


def test_fallback_to_the_other_type_of_the_pair() -> None:
    only_gap = [TemplateRef(1, ex.GAP_FILL)]
    assert choose_exercise(P, SrsState.NEW, None, 0, only_gap) == ExerciseChoice(ex.GAP_FILL, 1)
    only_recognition = [TemplateRef(3, ex.RECOGNITION)]
    assert choose_exercise(R, *MATURE, 0, only_recognition).exercise_type == ex.RECOGNITION


def test_fallback_to_another_template_of_the_direction() -> None:
    # A mature productive card with only young templates: one of them, not self-assessment.
    young_only = [TemplateRef(1, ex.GAP_FILL), TemplateRef(2, ex.TYPED_RECALL)]
    assert choose_exercise(P, *MATURE, 0, young_only).exercise_type in (
        ex.GAP_FILL,
        ex.TYPED_RECALL,
    )
    # A young receptive card with only a listening template.
    listening = [TemplateRef(4, ex.LISTENING)]
    assert choose_exercise(R, *YOUNG, 0, listening) == ExerciseChoice(ex.LISTENING, 4)


@pytest.mark.parametrize("direction", [R, P])
@pytest.mark.parametrize("state", [(SrsState.NEW, None), YOUNG, MATURE])
def test_self_assessment_without_templates_of_the_direction(
    direction: CardDirection, state: tuple[SrsState, float | None]
) -> None:
    other = [t for t in ALL if ex.EXERCISE_TYPES[t.exercise_type][0] != direction]
    for templates in ([], other):
        choice = choose_exercise(direction, *state, 3, templates)
        assert choice == ExerciseChoice(ex.SELF_ASSESSMENT, None)


def test_several_templates_of_one_type_rotate_with_reps() -> None:
    gaps = [
        TemplateRef(12, ex.GAP_FILL),
        TemplateRef(10, ex.GAP_FILL),
        TemplateRef(11, ex.GAP_FILL),
    ]
    # Only gap-fills: every review is a gap-fill, the sentence changes every two reviews.
    ids = [choose_exercise(P, SrsState.NEW, None, reps, gaps).template_id for reps in range(8)]
    assert ids == [10, 10, 11, 11, 12, 12, 10, 10]
    # With typed recall, gap-fills come on odd reps and still rotate.
    mixed = [*gaps, TemplateRef(2, ex.TYPED_RECALL)]
    odd = [choose_exercise(P, *YOUNG, reps, mixed).template_id for reps in (1, 3, 5, 7)]
    assert odd == [10, 11, 12, 10]
