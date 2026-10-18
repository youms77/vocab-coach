"""Recording limits and the silence rule (app/domain/speech_rules.py)."""

import math

import pytest

from app.domain.enums import ProductionKind
from app.domain.speech_rules import (
    DURATION_BOUNDS,
    MAX_AUDIO_BYTES,
    MAX_TARGET_CHARS,
    DurationProblem,
    duration_problem,
    is_silence,
)

SHADOWING = ProductionKind.SHADOWING


def test_limits() -> None:
    assert MAX_AUDIO_BYTES == 10 * 1024 * 1024
    assert MAX_TARGET_CHARS == 400
    bounds = DURATION_BOUNDS[SHADOWING]
    assert (bounds.min_s, bounds.max_s) == (0.5, 30.0)


@pytest.mark.parametrize(
    ("seconds", "problem"),
    [
        (0.0, DurationProblem.TOO_SHORT),
        (0.49, DurationProblem.TOO_SHORT),
        (0.5, None),
        (12.3, None),
        (30.0, None),
        (30.01, DurationProblem.TOO_LONG),
        (-1.0, DurationProblem.TOO_SHORT),
        (math.nan, DurationProblem.TOO_SHORT),
        (math.inf, DurationProblem.TOO_LONG),
        (-math.inf, DurationProblem.TOO_SHORT),
    ],
)
def test_shadowing_duration_bounds(seconds: float, problem: DurationProblem | None) -> None:
    assert duration_problem(SHADOWING, seconds) is problem


def test_problem_codes_are_the_api_codes() -> None:
    assert DurationProblem.TOO_SHORT == "audio_too_short"
    assert DurationProblem.TOO_LONG == "audio_too_long"


def test_a_kind_without_recordings_has_no_bounds() -> None:
    with pytest.raises(KeyError):
        duration_problem(ProductionKind.WRITING, 5.0)


def test_no_word_is_silence() -> None:
    assert is_silence(0, [])
    assert is_silence(0, [(0.0, -0.1)])  # the text decides first


def test_words_without_segments_are_speech() -> None:
    assert not is_silence(2, [])


def test_whisper_rule_on_every_segment() -> None:
    hallucinated = [(0.9, -1.2), (0.65, -1.0)]  # "Thank you." over silence
    assert is_silence(2, hallucinated)
    assert not is_silence(2, [*hallucinated, (0.1, -0.3)])  # one real segment is enough


@pytest.mark.parametrize(
    "segment",
    [
        (0.6, -1.5),  # not above 0.6
        (0.9, -0.99),  # the model was confident of its words
        (None, -2.0),
        (0.9, None),
    ],
)
def test_segments_that_are_not_silence(segment: tuple[float | None, float | None]) -> None:
    assert not is_silence(1, [segment])
