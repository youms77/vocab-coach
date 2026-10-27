"""Limits of recordings, the silence rule and the units of a spoken text (module F). Pure Python.

The audio limits are checked before anything is written; the silence rule reads the per-segment
probabilities of a Whisper `verbose_json` answer, passed as plain numbers (no AI type here). A
transcription is cut into at most `MAX_SPEECH_UNITS` numbered units for its correction
(`speech_units`).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.enums import ProductionKind
from app.domain.sentences import Sentence, split_sentences

# Well below Groq's 25 MB per file on the free plan (`app/ai/providers/groq.py`).
MAX_AUDIO_BYTES = 10 * 1024 * 1024
# The sentence a shadowing repeats.
MAX_TARGET_CHARS = 400
# What `speech compare` accepts as the heard text: the alignment is O(target x heard).
MAX_HEARD_CHARS = 2000
# A transcription longer than this is not corrected (as a written text: `MAX_TEXT_CHARS` of
# `services/productions.py`); three minutes of speech at a learner's pace are about 2 500.
MAX_SPEAKING_CHARS = 4000
# The units sent to the correction, as the 40 sentences of a written text (D-131).
MAX_SPEECH_UNITS = 40

# Whisper's own defaults (openai/whisper, `transcribe.py`: `no_speech_threshold=0.6`,
# `logprob_threshold=-1.0`): a segment is skipped as silence when its no-speech probability is
# above 0.6 and its average log-probability is not above -1.0.
NO_SPEECH_THRESHOLD = 0.6
LOGPROB_THRESHOLD = -1.0


class RecordingKind(StrEnum):
    """What a recording is for. The values of `shadowing` and `speaking` are those of
    `ProductionKind`, so `DURATION_BOUNDS[ProductionKind.SHADOWING]` reads the same bounds; a spoken
    answer in a review is a `speaking` production with its own bounds."""

    SHADOWING = "shadowing"  # a sentence repeated after the speech synthesis
    SPEAKING = "speaking"  # free speaking on a topic (SPEC: 1 to 2 minutes, up to 3 accepted)
    SPOKEN_ANSWER = "spoken_answer"  # the answer to the question of a mature productive card
    CONSOLIDATION = "consolidation"  # the talk of a consolidation task (module G, M7.a2)


@dataclass(frozen=True)
class DurationBounds:
    min_s: float
    max_s: float


DURATION_BOUNDS: dict[RecordingKind, DurationBounds] = {
    RecordingKind.SHADOWING: DurationBounds(min_s=0.5, max_s=30.0),
    # Under 5 s there is nothing to correct; 180 s keeps a take that runs over the screen's 1 to 2
    # minutes (a lost recording costs more than a long one).
    RecordingKind.SPEAKING: DurationBounds(min_s=5.0, max_s=180.0),
    # One answer to one question: a few words to a minute and a half.
    RecordingKind.SPOKEN_ANSWER: DurationBounds(min_s=1.0, max_s=90.0),
    # A talk of 2 to 4 minutes for 8 to 15 terms; 240 s are about 3 800 characters, under
    # `MAX_SPEAKING_CHARS`.
    RecordingKind.CONSOLIDATION: DurationBounds(min_s=20.0, max_s=240.0),
}


class DurationProblem(StrEnum):
    TOO_SHORT = "audio_too_short"
    TOO_LONG = "audio_too_long"


def duration_problem(
    kind: RecordingKind | ProductionKind, seconds: float
) -> DurationProblem | None:
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


def speech_units(text: str) -> list[Sentence]:
    """The numbered units of a spoken text, each a run of whole consecutive sentences.

    Up to `MAX_SPEECH_UNITS` sentences, each sentence is a unit. Beyond, consecutive sentences are
    grouped into `MAX_SPEECH_UNITS` units of balanced sizes (the first `n % MAX_SPEECH_UNITS` units
    hold one sentence more), never cutting a sentence: three minutes of speech can hold more
    sentences than a written paragraph. A unit's text is the original text between the start of its
    first sentence and the end of its last (`start` and `end` in Unicode code points), indexed
    from 1.
    """
    sentences = split_sentences(text, max_sentences=None)
    if len(sentences) <= MAX_SPEECH_UNITS:
        return sentences
    size, extra = divmod(len(sentences), MAX_SPEECH_UNITS)
    units: list[Sentence] = []
    position = 0
    for index in range(1, MAX_SPEECH_UNITS + 1):
        taken = size + (1 if index <= extra else 0)
        first, last = sentences[position], sentences[position + taken - 1]
        units.append(Sentence(index, text[first.start : last.end], first.start, last.end))
        position += taken
    return units
