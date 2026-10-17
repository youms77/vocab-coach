"""Step prompts never contain the solution (app/domain/review_steps.py)."""

from typing import Any

import pytest

from app.domain import exercises as ex
from app.domain.enums import CardDirection
from app.domain.review_steps import (
    SOLUTION_KEYS,
    build_prompt,
    build_solution,
    confusion_words,
    gapped,
    option_seed,
    prompt_has_cue,
    sheet_summary,
    shuffled_options,
)
from app.domain.usage_sheet import UsageSheet

RECOGNITION = {
    "sentence": "We cannot rule out reverse causality.",
    "meaning": "to exclude a possibility",
    "meaning_fr": "exclure",
    "distractors": ["to confirm", "to measure", "to ignore"],
}
CONTENTS: dict[str, dict[str, Any]] = {
    ex.RECOGNITION: RECOGNITION,
    ex.LISTENING: RECOGNITION,
    ex.GAP_FILL: {
        "sentence": "We cannot ___ this.",
        "answer": "rule out",
        "accepted": ["ruled out"],
    },
    ex.TYPED_RECALL: {
        "cue_fr": "exclure",
        "cue_definition": None,
        "answer": "rule out",
        "accepted": [],
    },
    ex.SENTENCE_PRODUCTION: {
        "situation": "Say a cause is impossible.",
        "example_answer": "We rule it out.",
    },
    ex.SPOKEN_ANSWER: {
        "question": "What can't you exclude?",
        "example_answer": "I can't rule out X.",
    },
}
SHEET = UsageSheet.model_validate(
    {
        "definition_simple": "to say that something is not possible",
        "translation_fr": ["exclure"],
        "examples": [{"sentence": "They ruled out fraud.", "kind": "general"}],
        "confusables": [{"term": "rule over", "difference": "govern"}],
        "french_speaker_pitfalls": [
            {"wrong": "exclude out", "right": "rule out", "explanation": "x"}
        ],
    }
)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


@pytest.mark.parametrize("exercise_type", [*CONTENTS, ex.SELF_ASSESSMENT])
@pytest.mark.parametrize("direction", list(CardDirection))
def test_prompt_never_contains_solution_keys(exercise_type: str, direction: CardDirection) -> None:
    content = CONTENTS.get(exercise_type)
    prompt = build_prompt(
        exercise_type,
        direction,
        content,
        term="rule out",
        origin_sentence=None,
        sheet=SHEET,
        seed="s",
    )
    assert not _keys(prompt) & SOLUTION_KEYS
    if direction == CardDirection.PRODUCTIVE:
        assert "term" not in prompt


def test_choice_options_are_shuffled_deterministically() -> None:
    first = shuffled_options(RECOGNITION, option_seed(7, 3))
    assert first == shuffled_options(RECOGNITION, option_seed(7, 3))
    options, correct = first
    assert sorted(options) == sorted([RECOGNITION["meaning"], *RECOGNITION["distractors"]])
    assert options[correct] == RECOGNITION["meaning"]
    # Seeds change the order sometimes (not always the same position for the right answer).
    positions = {shuffled_options(RECOGNITION, option_seed(7, reps))[1] for reps in range(20)}
    assert len(positions) > 1
    solution = build_solution(
        ex.RECOGNITION,
        RECOGNITION,
        term="rule out",
        origin_sentence=None,
        sheet=None,
        seed=option_seed(7, 3),
    )
    assert solution["correct_index"] == correct


def test_listening_sends_the_sentence() -> None:
    prompt = build_prompt(
        ex.LISTENING,
        CardDirection.RECEPTIVE,
        RECOGNITION,
        term="x",
        origin_sentence=None,
        sheet=None,
        seed="s",
    )
    assert prompt["sentence"] == RECOGNITION["sentence"]


def test_self_assessment_prompts() -> None:
    receptive = build_prompt(
        ex.SELF_ASSESSMENT,
        CardDirection.RECEPTIVE,
        None,
        term="rule out",
        origin_sentence="We cannot rule out chance.",
        sheet=SHEET,
        seed="s",
    )
    assert receptive == {"term": "rule out", "sentence": "We cannot rule out chance."}
    productive = build_prompt(
        ex.SELF_ASSESSMENT,
        CardDirection.PRODUCTIVE,
        None,
        term="rule out",
        origin_sentence=None,
        sheet=SHEET,
        seed="s",
    )
    assert productive == {
        "cue_fr": "exclure",
        "cue_definition": "to say that something is not possible",
        "sentence_gapped": "They ___ fraud.",
    }
    nothing = build_prompt(
        ex.SELF_ASSESSMENT,
        CardDirection.PRODUCTIVE,
        None,
        term="x",
        origin_sentence=None,
        sheet=None,
        seed="s",
    )
    assert not prompt_has_cue(nothing)


@pytest.mark.parametrize(
    ("sentence", "term", "expected"),
    [
        ("We account for regional effects.", "to account for", "We ___ regional effects."),
        ("They Ruled it Out quickly.", "rule sth out", "They ___ quickly."),
        ("Studies show it.", "study", "___ show it."),
        ("Nothing here.", "rule out", None),
    ],
)
def test_gapped(sentence: str, term: str, expected: str | None) -> None:
    assert gapped(sentence, term) == expected


def test_solutions_and_summary() -> None:
    gap = build_solution(
        ex.GAP_FILL,
        CONTENTS[ex.GAP_FILL],
        term="rule out",
        origin_sentence=None,
        sheet=None,
        seed="s",
    )
    assert gap == {
        "answer": "rule out",
        "accepted": ["ruled out"],
        "sentence": "We cannot rule out this.",
    }
    self_graded = build_solution(
        ex.SELF_ASSESSMENT, None, term="rule out", origin_sentence=None, sheet=SHEET, seed="s"
    )
    assert self_graded["translation_fr"] == ["exclure"]
    summary = sheet_summary("rule out", SHEET)
    assert summary is not None and summary["examples"] == ["They ruled out fraud."]
    assert sheet_summary("rule out", None) is None
    assert confusion_words(SHEET) == ["rule over", "exclude out"]
