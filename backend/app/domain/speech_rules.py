"""Limits of recordings and the silence rule (module F). Pure Python.

The audio limits are checked before anything is written; the silence rule reads the per-segment
probabilities of a Whisper `verbose_json` answer, passed as plain numbers (no AI type here).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.enums import ProductionKind

# Well below Groq's 25 MB per file on the free plan (`app/ai/providers/groq.py`).
MAX_AUDIO_BYTES = 10 * 1024 * 1024
# The sentence a shadowing repeats.
MAX_TARGET_CHARS = 400
# What `speech compare` accepts as the heard text: the alignment is O(target x heard).
MAX_HEARD_CHARS = 2000

# Whisper's own defaults (openai/whisper, `transcribe.py`: `no_speech_threshold=0.6`,
# `logprob_threshold=-1.0`): a segment is skipped as silence when its no-speech probability is
# above 0.6 and its average log-probability is not above -1.0.
NO_SPEECH_THRESHOLD = 0.6
LOGPROB_THRESHOLD = -1.0


@dataclass(frozen=True)
class DurationBounds:
    min_s: float
    max_s: float


# Per kind of production; M6.a2 adds free speaking (about 180 s).
DURATION_BOUNDS: dict[ProductionKind, DurationBounds] = {
    ProductionKind.SHADOWING: DurationBounds(min_s=0.5, max_s=30.0),
}


class DurationProblem(StrEnum):
    TOO_SHORT = "audio_too_short"
    TOO_LONG = "audio_too_long"


def duration_problem(kind: ProductionKind, seconds: float) -> DurationProblem | None:
    """Whether a recording of this kind is too short or too long (NaN is too short, an infinite
    duration too long). Raises KeyError for a kind that takes no recording."""
    bounds = DURATION_BOUNDS[kind]
    if math.isnan(seconds) or seconds < bounds.min_s:
        return DurationProblem.TOO_SHORT
    if seconds > bounds.max_s:
        return DurationProblem.TOO_LONG
    return None


def _silent_segment(no_speech_prob: float | None, avg_logprob: float | None) -> bool:
    if no_speech_prob is None or avg_logprob is None:
        return False  # without the numbers, trust the text
    return no_speech_prob > NO_SPEECH_THRESHOLD and avg_logprob <= LOGPROB_THRESHOLD


def is_silence(
    heard_word_count: int, segments: Sequence[tuple[float | None, float | None]]
) -> bool:
    """No word was heard, or every segment is silence by Whisper's rule. Whisper sometimes writes a
    short sentence over silence ("Thank you."): its segments then carry a high no-speech
    probability. `segments` are (no_speech_prob, avg_logprob) pairs; none means only the text
    decides."""
    if heard_word_count == 0:
        return True
    return bool(segments) and all(_silent_segment(p, lp) for p, lp in segments)
