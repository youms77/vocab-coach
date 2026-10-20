"""The demo's fictional AI outputs (app/demo/fictional_ai.py) fit the real schemas (D-163)."""

import io
import random
import wave

import pytest

from app.ai.schemas.speaking_correction import Mode
from app.db.taxonomy import load_taxonomy
from app.demo import clips, fictional_ai
from app.demo.dataset import DemoDrill, ErrorTemplate, StructureComment, load_dataset
from app.domain.drills import grade_item, options_order
from app.domain.enums import ErrorSource
from app.domain.sentences import find_fragment, split_sentences
from app.domain.speech_compare import compare, words
from app.domain.speech_rules import is_silence, speech_units
from app.domain.transcript_import import split_units
from app.services import corrections, speaking, transcripts

DATASET = load_dataset()
CODES = load_taxonomy().codes
FILLER = DATASET.fillers[0]


def _family(code: str) -> set[str]:
    return {c for c in CODES if c == code or c.startswith(code + ".")}


def _prepared(text: str) -> corrections.Prepared:
    return corrections.Prepared(
        attempt_id=1,
        text=text,
        prompt="",
        source=ErrorSource.WRITING,
        sentences=split_sentences(text),
        targets=[],
        taxonomy=dict.fromkeys(CODES, ""),
    )


@pytest.mark.parametrize("template", DATASET.error_templates, ids=lambda t: t.original[:40])
def test_every_template_gives_a_valid_correction(template: ErrorTemplate) -> None:
    prepared = _prepared(f"{FILLER} {template.original}")
    output = fictional_ai.correction_output(prepared, [template])
    (error,) = output.errors
    assert (error.wrong, error.correction) == (template.wrong, template.correction)
    assert error.explanation_fr == template.explanation_fr
    assert [s.status for s in output.sentences] == ["correct", "corrected"]
    assert template.correction in output.corrected_text


@pytest.mark.parametrize(
    "template",
    [
        t
        for t in DATASET.error_templates
        if not t.code.startswith(transcripts.EXCLUDED_CODE_PREFIXES)
    ],
    ids=lambda t: t.original[:40],
)
def test_every_template_gives_a_valid_transcript_analysis(template: ErrorTemplate) -> None:
    text = f"{FILLER} {template.original}"
    units = split_units(text)
    prepared = transcripts.Prepared(
        attempt_id=1,
        units=units,
        contexts={},
        taxonomy={
            code: "" for code in CODES if not code.startswith(transcripts.EXCLUDED_CODE_PREFIXES)
        },
        errors_at=None,
    )
    output = fictional_ai.transcript_chunk(prepared, units, [template])
    assert [e.wrong for e in output.errors] == [template.wrong]


def test_a_template_that_matches_no_sentence_is_a_dataset_bug() -> None:
    other = DATASET.error_templates[1]
    prepared = _prepared(FILLER)
    with pytest.raises(ValueError, match="match no sentence"):
        fictional_ai.correction_output(prepared, [other])


@pytest.mark.parametrize("drill", DATASET.drills, ids=lambda d: d.code)
def test_every_drill_fits_the_drill_schema_and_its_grading(drill: DemoDrill) -> None:
    output = fictional_ai.drill_output(drill, _family(drill.code))
    assert len(output.items) == len(drill.items)
    for index, (item, demo) in enumerate(zip(output.items, drill.items, strict=True)):
        stored = item.model_dump(mode="json")
        shown = options_order(1, index, stored["options"]) if demo.kind == "choice" else None
        right = grade_item(
            stored,
            shown,
            answer=demo.answer if demo.kind == "gap_fill" else None,
            choice_index=shown.index(demo.answer) if shown else None,
        )
        assert right.outcome == "exact"
        if demo.kind == "gap_fill":
            wrong = grade_item(stored, None, answer=demo.wrong, choice_index=None)
            assert wrong.outcome == "wrong"  # the learner's mistake really is graded as one


def test_the_drills_cover_several_categories_and_themes() -> None:
    assert len({d.code for d in DATASET.drills}) >= 5
    assert {i.theme for d in DATASET.drills for i in d.items} == {
        "campus",
        "data_economics",
        "everyday",
    }


# --- Speaking (M6.a2b) ---------------------------------------------------------------------------

SPOKEN_CODES = {c: "" for c in CODES if not c.startswith(transcripts.EXCLUDED_CODE_PREFIXES)}
SPOKEN_TEMPLATES = [
    t for t in DATASET.error_templates if not t.code.startswith(transcripts.EXCLUDED_CODE_PREFIXES)
]
SENTENCES = [term.sentence for term in DATASET.all_terms() if term.sentence]


def _speech(text: str, mode: Mode = "monologue", targets: int = 0) -> speaking.PreparedSpeech:
    prepared = corrections.Prepared(
        attempt_id=1,
        text=text,
        prompt="",
        source=ErrorSource.SPEAKING if mode == "monologue" else ErrorSource.REVIEW,
        sentences=speech_units(text),
        targets=[
            corrections.Target(ref, ref + 1, "rule out", "phrase", "") for ref in range(targets)
        ],
        taxonomy=SPOKEN_CODES,
    )
    return speaking.PreparedSpeech(prepared, mode)


@pytest.mark.parametrize("template", SPOKEN_TEMPLATES, ids=lambda t: t.original[:40])
def test_every_spoken_template_gives_a_valid_speaking_correction(template: ErrorTemplate) -> None:
    text = f"{FILLER} {template.original}"
    output = fictional_ai.speaking_output(
        _speech(text),
        [template],
        structure=DATASET.speech.structure[0],
        connectors=DATASET.speech.connectors,
    )
    (error,) = output.errors
    assert (error.wrong, error.correction) == (template.wrong, template.correction)
    assert output.structure is not None


@pytest.mark.parametrize("comment", DATASET.speech.structure, ids=lambda c: c.comment_en[:30])
def test_every_structure_comment_fits_the_schema(comment: StructureComment) -> None:
    text = " ".join(DATASET.fillers)
    output = fictional_ai.speaking_output(
        _speech(text), [], structure=comment, connectors=DATASET.speech.connectors
    )
    assert output.structure is not None
    used = output.structure.connectors_used
    assert used and all(find_fragment(text, c) for c in used)  # "So", "also", "When"...


def test_a_monologue_needs_a_structure() -> None:
    with pytest.raises(ValueError, match="structure"):
        fictional_ai.speaking_output(_speech(FILLER), [])


@pytest.mark.parametrize("used", [True, False])
def test_a_spoken_answer_says_whether_the_term_was_heard(used: bool) -> None:
    answer = DATASET.speech.forgotten_answers[0]
    output = fictional_ai.speaking_output(_speech(answer, "answer", targets=1), [], term_used=used)
    assert output.structure is None
    assert [(t.used, t.used_correctly) for t in output.targets] == [(used, used)]


def test_a_transcription_has_one_segment_per_sentence() -> None:
    text = " ".join(DATASET.fillers[:3])
    result = fictional_ai.transcription(text, 9.0)
    assert result.ok and result.data is not None
    assert (result.provider, result.model) == ("demo", "demo-transcription-v1")
    assert (result.data.text, result.data.duration_s, len(result.data.segments)) == (text, 9.0, 3)
    assert result.data.segments[-1].end == pytest.approx(9.0, abs=0.05)
    scores = [(s.no_speech_prob, s.avg_logprob) for s in result.data.segments]
    assert not is_silence(len(words(text)), scores)


def test_a_silent_take_is_silence() -> None:
    result = fictional_ai.transcription("", 6.0)
    assert result.data is not None and result.data.text == ""
    scores = [(s.no_speech_prob, s.avg_logprob) for s in result.data.segments]
    assert is_silence(0, scores)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_misheard_sentences_lose_exactly_that_many_words(count: int) -> None:
    for seed, sentence in enumerate(SENTENCES):
        heard = fictional_ai.misheard(sentence, random.Random(seed), count)
        comparison = compare(sentence, heard)
        assert len(comparison.unrecognized) == count, (sentence, heard)
        assert len(sentence.split()) - len(heard.split()) <= count


def test_the_clips_are_short_wav_files() -> None:
    for data in (clips.tone(), clips.silence()):
        with wave.open(io.BytesIO(data)) as clip:
            assert (clip.getnchannels(), clip.getsampwidth()) == (1, 2)
            assert clip.getnframes() / clip.getframerate() == pytest.approx(1.0)
    with wave.open(io.BytesIO(clips.silence())) as clip:
        assert set(clip.readframes(clip.getnframes())) == {0}
    with wave.open(io.BytesIO(clips.tone())) as clip:
        assert set(clip.readframes(clip.getnframes())) != {0}
