"""Free speaking and spoken answers, the pure part (M6.a2a): recording bounds, the units of a
transcription, the rating proposed from a spoken check, the speaking topics."""

import random
from typing import Any

import pytest

from app.domain.enums import ProductionKind
from app.domain.grading import production_rating, production_warnings
from app.domain.sentences import split_sentences
from app.domain.speaking_topics import SpeakingTag, SpeakingTopic, parse_speaking_topics
from app.domain.speech_rules import (
    DURATION_BOUNDS,
    MAX_SPEECH_UNITS,
    DurationProblem,
    RecordingKind,
    duration_problem,
    speech_units,
)
from app.domain.srs import Rating
from app.domain.topics import TopicsError, pick_topics

# --- Bounds --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "low", "high"),
    [
        (RecordingKind.SHADOWING, 0.5, 30.0),
        (RecordingKind.SPEAKING, 5.0, 180.0),
        (RecordingKind.SPOKEN_ANSWER, 1.0, 90.0),
    ],
)
def test_each_kind_of_recording_has_its_bounds(
    kind: RecordingKind, low: float, high: float
) -> None:
    assert (DURATION_BOUNDS[kind].min_s, DURATION_BOUNDS[kind].max_s) == (low, high)
    assert duration_problem(kind, low) is None and duration_problem(kind, high) is None
    assert duration_problem(kind, low - 0.01) is DurationProblem.TOO_SHORT
    assert duration_problem(kind, high + 0.01) is DurationProblem.TOO_LONG


def test_the_production_kinds_read_the_same_bounds() -> None:
    assert DURATION_BOUNDS[ProductionKind.SHADOWING] is DURATION_BOUNDS[RecordingKind.SHADOWING]
    assert DURATION_BOUNDS[ProductionKind.SPEAKING] is DURATION_BOUNDS[RecordingKind.SPEAKING]


# --- Units ---------------------------------------------------------------------------------------


def test_a_short_text_has_one_unit_per_sentence() -> None:
    text = "Um, I study statistics. I live in campus.\nAnd I like it"
    assert speech_units(text) == split_sentences(text)


def test_beyond_forty_sentences_they_are_grouped() -> None:
    text = " ".join(f"Sentence number {n} is here." for n in range(1, 101))  # 100 sentences
    units = speech_units(text)
    assert len(units) == MAX_SPEECH_UNITS
    # 100 = 40 x 2 + 20: the first 20 units hold 3 sentences, the others 2.
    assert (
        units[0].text
        == "Sentence number 1 is here. Sentence number 2 is here. Sentence number 3 is here."
    )
    assert units[19].text.startswith("Sentence number 58 ") and units[20].text.startswith(
        "Sentence number 61 "
    )
    assert units[-1].text == "Sentence number 99 is here. Sentence number 100 is here."
    assert [u.index for u in units] == list(range(1, 41))


def test_the_units_keep_every_sentence_once_in_order_with_exact_positions() -> None:
    rng = random.Random(7)
    words = ["so", "um", "I", "think", "we", "study", "data", "here", "since", "two", "years"]
    for _ in range(200):
        sentences = []
        for _ in range(rng.randint(1, 130)):
            body = " ".join(rng.choice(words) for _ in range(rng.randint(1, 8)))
            sentences.append(body.capitalize() + rng.choice([".", "?", "!"]))
        separators = [rng.choice([" ", "  ", "\n", " \n "]) for _ in sentences]
        text = "".join(s + sep for s, sep in zip(sentences, separators, strict=True))
        units = speech_units(text)
        found = split_sentences(text, max_sentences=None)
        assert len(units) == min(len(found), MAX_SPEECH_UNITS)
        assert [u.index for u in units] == list(range(1, len(units) + 1))
        for unit in units:
            assert text[unit.start : unit.end] == unit.text
        # Every sentence lies in exactly one unit, in order, and no unit cuts a sentence.
        owners = []
        for sentence in found:
            [owner] = [
                u.index for u in units if u.start <= sentence.start and sentence.end <= u.end
            ]
            owners.append(owner)
        assert owners == sorted(owners)
        sizes = [owners.count(u.index) for u in units]
        assert max(sizes) - min(sizes) <= 1 and sizes == sorted(sizes, reverse=True)


def test_an_empty_transcription_has_no_unit() -> None:
    assert speech_units("   ") == []


# --- Rating of a spoken answer -------------------------------------------------------------------


def _spoken(*, used: bool, correct: bool | None, error_ref: int | None = None) -> dict[str, Any]:
    errors = [] if error_ref is None else [{"target_ref": error_ref}]
    return {
        "format": "speaking-1",
        "output": {"errors": errors},
        "targets": [{"ref": 0, "lexical_item_id": 7, "used": used, "used_correctly": correct}],
    }


@pytest.mark.parametrize(
    ("feedback", "rating", "warnings"),
    [
        (_spoken(used=True, correct=True), Rating.GOOD, []),
        (_spoken(used=True, correct=False), Rating.AGAIN, []),
        (_spoken(used=True, correct=True, error_ref=0), Rating.AGAIN, []),
        (_spoken(used=True, correct=True, error_ref=3), Rating.GOOD, []),
        (_spoken(used=True, correct=None), None, []),
        # Not heard: the learner may have left it out or the recogniser missed it.
        (_spoken(used=False, correct=False), None, ["term_not_heard"]),
        (None, None, []),
        ({"format": "speaking-1", "targets": []}, None, []),
    ],
)
def test_the_rating_of_a_spoken_answer(
    feedback: dict[str, Any] | None, rating: Rating | None, warnings: list[str]
) -> None:
    assert production_rating(feedback, 7) == rating
    assert production_warnings(feedback, 7) == warnings


def test_a_written_sentence_without_the_term_is_still_again() -> None:
    written = _spoken(used=False, correct=False) | {"format": "correction-1"}
    assert production_rating(written, 7) == Rating.AGAIN
    assert production_warnings(written, 7) == []


def test_never_easy_nor_hard() -> None:
    proposed = {
        production_rating(_spoken(used=used, correct=correct, error_ref=ref), 7)
        for used in (True, False)
        for correct in (True, False, None)
        for ref in (None, 0)
    }
    assert proposed <= {Rating.GOOD, Rating.AGAIN, None}


# --- Speaking topics -----------------------------------------------------------------------------


def _topic(n: int, *tags: SpeakingTag) -> SpeakingTopic:
    return SpeakingTopic(id=f"s{n}", en=f"Talk {n}.", fr=f"Parlez {n}.", tags=list(tags))


def test_speaking_topics_use_their_own_tags_and_the_shared_pick() -> None:
    topics = [
        _topic(1, SpeakingTag.PRESENTING),
        _topic(2, SpeakingTag.INTERVIEW),
        _topic(3, SpeakingTag.PRESENTING, SpeakingTag.DATA_SCIENCE),
    ]
    picked = pick_topics(topics, day_number=1, count=1, tag=SpeakingTag.PRESENTING)
    assert [t.id for t in picked] == ["s3"]
    assert [t.id for t in pick_topics(topics, day_number=0, recent_prompts=["talk 1."])] == [
        "s2",
        "s3",
    ]


def test_a_malformed_speaking_file_is_refused() -> None:
    topic = {"id": "a1", "en": "A.", "fr": "A.", "tags": ["presenting"]}
    assert parse_speaking_topics({"version": 1, "topics": [topic]})[0].tags == [
        SpeakingTag.PRESENTING
    ]
    with pytest.raises(TopicsError, match="speaking topics file: duplicate"):
        parse_speaking_topics({"version": 1, "topics": [topic, topic]})
    with pytest.raises(TopicsError):
        parse_speaking_topics({"version": 1, "topics": [{**topic, "tags": ["campus_life"]}]})
    with pytest.raises(TopicsError):
        parse_speaking_topics({"version": 1, "topics": [{**topic, "tags": []}]})
