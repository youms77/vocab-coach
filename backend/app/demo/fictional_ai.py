"""Fictional AI outputs for the demo (D-163, D-190).

The demo never calls an AI. Its corrections, transcript analyses, drills, transcriptions and spoken
corrections are built here from the fictional dataset as the outputs the AI tasks would have
returned, **validated by the real output schemas** with the real validation contexts, then stored by
the same services as a real result (`corrections.store_correction`, `transcripts.store_analysis`,
`drills.store_drill`, `speech.store_recording`, `corrections.store_speaking_correction`). A
template that does not fit its sentence is a bug of the dataset and raises.
"""

import random
import re
from collections.abc import Sequence
from typing import Any

from app.ai.schemas import TranscriptionOutput
from app.ai.schemas.production_correction import (
    ProductionCorrectionOutput,
    correction_context,
)
from app.ai.schemas.speaking_correction import SpeakingCorrectionOutput, speaking_context
from app.ai.schemas.targeted_drill import TargetedDrillOutput, drill_context
from app.ai.schemas.transcript_analysis import TranscriptAnalysisOutput, transcript_context
from app.ai.types import AiResult, AiStatus
from app.demo.dataset import DemoDrill, ErrorTemplate, StructureComment
from app.domain.sentences import find_fragment, split_sentences
from app.domain.transcript_import import Unit
from app.services import corrections, speaking, transcripts

CORRECTION_PROVENANCE = ("demo", None, "demo-correction-v1")
TRANSCRIPT_PROVENANCE = ("demo", None, "demo-transcript-v1")
DRILL_PROVENANCE = ("demo", None, "demo-drill-v1")
SPEAKING_PROVENANCE = ("demo", None, "demo-speaking-v1")
# A transcription records its provider and model, not a prompt version (`production.transcribed`):
# the version goes in the model, the only place it is seen (D-190).
TRANSCRIPTION_PROVIDER = "demo"
TRANSCRIPTION_MODEL = "demo-transcription-v1"
OVERALL_COMMENT = "Fictional correction written for the demo."
# Whisper-like segment scores: confident speech, and a take with nothing said (D-171).
_SPEECH_SCORES = (0.02, -0.25)
_SILENCE_SCORES = (0.92, -1.3)
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _key(text: str) -> str:
    return " ".join(text.split())


def _apply(text: str, templates: list[ErrorTemplate]) -> str:
    """`text` with each template's wrong form replaced by its correction."""
    for template in templates:
        found = find_fragment(text, template.wrong)
        if found is not None:
            text = text[: found[0]] + template.correction + text[found[1] :]
    return text


def _error_data(template: ErrorTemplate, index_key: str, index: int) -> dict[str, Any]:
    return {
        index_key: index,
        "wrong": template.wrong,
        "correction": template.correction,
        "alternatives": list(template.alternatives),
        "category_code": template.code,
        "explanation_en": template.explanation,
        "explanation_fr": template.explanation_fr,
    }


# --- Written production ------------------------------------------------------------------------


def correction_output(
    prepared: corrections.Prepared, made: list[ErrorTemplate]
) -> ProductionCorrectionOutput:
    """The correction of a written production whose sentences are the templates' originals and
    fillers. Raises ValueError when a template matches no sentence."""
    pending = list(made)
    sentences: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    natural: list[str] = []
    for sentence in prepared.sentences:
        match = next((t for t in pending if _key(t.original) == _key(sentence.text)), None)
        if match is None:
            sentences.append(
                {"index": sentence.index, "corrected": sentence.text, "status": "correct"}
            )
            natural.append(sentence.text)
            continue
        pending.remove(match)
        corrected = _apply(sentence.text, [match])
        sentences.append({"index": sentence.index, "corrected": corrected, "status": "corrected"})
        errors.append(_error_data(match, "sentence_index", sentence.index))
        natural.append(match.alternatives[0])
    if pending:
        raise ValueError(f"demo templates match no sentence: {[t.original for t in pending]}")
    data = {
        "sentences": sentences,
        "corrected_text": " ".join(s["corrected"] for s in sentences),
        "natural_text": " ".join(natural),
        "errors": errors,
        "naturalness_notes": [],
        "targets": [],
        "overall_comment": OVERALL_COMMENT,
    }
    return ProductionCorrectionOutput.model_validate(
        data,
        context=correction_context(
            {s.index: s.text for s in prepared.sentences}, set(prepared.taxonomy), set()
        ),
    )


# --- Transcript --------------------------------------------------------------------------------


def transcript_chunk(
    prepared: transcripts.Prepared, chunk: list[Unit], made: list[ErrorTemplate]
) -> TranscriptAnalysisOutput:
    """The analysis of one chunk of units. `made` holds the templates of the whole conversation:
    the ones whose sentence is in this chunk are used. Raises ValueError (via the schema) when an
    output would break a rule."""
    remaining = {unit.index: unit.text for unit in chunk}
    per_unit: dict[int, list[ErrorTemplate]] = {unit.index: [] for unit in chunk}
    for template in made:
        for unit in chunk:
            if _key(template.original) in _key(remaining[unit.index]):
                per_unit[unit.index].append(template)
                remaining[unit.index] = _key(remaining[unit.index]).replace(
                    _key(template.original), "", 1
                )
                break
    units = []
    errors = []
    for unit in chunk:
        found = per_unit[unit.index]
        units.append(
            {
                "index": unit.index,
                "corrected": _apply(unit.text, found),
                "status": "corrected" if found else "correct",
            }
        )
        errors += [_error_data(t, "unit_index", unit.index) for t in found]
    data = {
        "units": units,
        "errors": errors,
        "naturalness_notes": [],
        "overall_comment": OVERALL_COMMENT,
    }
    return TranscriptAnalysisOutput.model_validate(
        data,
        context=transcript_context({u.index: u.text for u in chunk}, set(prepared.taxonomy)),
    )


# --- Drill -------------------------------------------------------------------------------------


def drill_output(drill: DemoDrill, codes: set[str]) -> TargetedDrillOutput:
    """The drill of one category. `codes` are the category and its active descendants."""
    return TargetedDrillOutput.model_validate(
        drill.output(), context=drill_context(len(drill.items), codes)
    )


# --- Transcription -----------------------------------------------------------------------------


def transcription(text: str, duration_s: float) -> AiResult[TranscriptionOutput]:
    """What the recogniser would have returned for a take of `duration_s` seconds: `text` (empty for
    a silent take) with one segment per sentence, timed by its share of the words."""
    sentences = [s.text for s in split_sentences(text, max_sentences=None)] if text else []
    segments: list[dict[str, float]] = []
    if not sentences:
        no_speech, logprob = _SILENCE_SCORES
        segments.append(
            {"start": 0.0, "end": duration_s, "no_speech_prob": no_speech, "avg_logprob": logprob}
        )
    else:
        total = sum(len(s.split()) for s in sentences)
        start = 0.0
        for sentence in sentences:
            end = round(start + duration_s * len(sentence.split()) / total, 2)
            no_speech, logprob = _SPEECH_SCORES
            segments.append(
                {"start": start, "end": end, "no_speech_prob": no_speech, "avg_logprob": logprob}
            )
            start = end
    output = TranscriptionOutput.model_validate(
        {"text": text, "duration_s": duration_s, "segments": segments}
    )
    return AiResult(
        status=AiStatus.OK,
        data=output,
        provider=TRANSCRIPTION_PROVIDER,
        model=TRANSCRIPTION_MODEL,
    )


def misheard(sentence: str, rng: random.Random, count: int) -> str:
    """`sentence` as a recogniser might have heard it, with `count` words (0 to 2) lost: a final
    -s dropped ("effects" -> "effect") or the word missed altogether. Both are words the
    comparator does not recognise (a final -s is never "close", D-173)."""
    tokens = sentence.split()
    words = [_WORD.search(token) for token in tokens]
    candidates = [i for i, word in enumerate(words) if word and len(word.group(0)) >= 3]
    chosen = sorted(rng.sample(candidates, min(count, len(candidates))), reverse=True)
    for index in chosen:
        token = tokens[index]
        word = _WORD.findall(token)[0]
        if word.lower().endswith("s") and not word.lower().endswith("ss") and len(word) >= 4:
            tokens[index] = token.replace(word, word[:-1], 1)
        else:
            del tokens[index]
    return " ".join(tokens)


# --- Spoken production -------------------------------------------------------------------------


def _connectors_said(text: str, connectors: Sequence[str]) -> list[str]:
    """The connectors said as whole words, in the order of the list, with the case of the text."""
    said = []
    for connector in connectors:
        found = re.search(rf"\b{re.escape(connector)}\b", text, flags=re.IGNORECASE)
        if found is not None:
            said.append(found.group(0))
    return said[:10]


def speaking_output(
    prepared: speaking.PreparedSpeech,
    made: list[ErrorTemplate],
    *,
    structure: StructureComment | None = None,
    connectors: Sequence[str] = (),
    term_used: bool = True,
) -> SpeakingCorrectionOutput:
    """The correction of a transcription whose units are the templates' originals and fillers (a
    free speech, with `structure`), or of a spoken answer (`answer` mode: every target `used`
    as `term_used` says, no structure). Raises ValueError when a template matches no unit."""
    found = prepared.correction
    pending = list(made)
    units: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    natural: list[str] = []
    for unit in found.sentences:
        match = next((t for t in pending if _key(t.original) == _key(unit.text)), None)
        if match is None:
            units.append({"index": unit.index, "corrected": unit.text, "status": "correct"})
            natural.append(unit.text)
            continue
        pending.remove(match)
        units.append(
            {"index": unit.index, "corrected": _apply(unit.text, [match]), "status": "corrected"}
        )
        errors.append(_error_data(match, "sentence_index", unit.index))
        natural.append(match.alternatives[0])
    if pending:
        raise ValueError(f"demo templates match no unit: {[t.original for t in pending]}")
    feedback = None
    if structure is not None:
        feedback = {
            "comment_en": structure.comment_en,
            "comment_fr": structure.comment_fr,
            "connectors_used": _connectors_said(found.text, connectors),
            "suggestions": [s.model_dump() for s in structure.suggestions],
        }
    data = {
        "sentences": units,
        "corrected_text": " ".join(u["corrected"] for u in units),
        "natural_text": " ".join(natural),
        "errors": errors,
        "naturalness_notes": [],
        "targets": [
            {
                "ref": target.ref,
                "used": term_used,
                "used_correctly": term_used,
                "comment": "" if term_used else "The term was not heard.",
            }
            for target in found.targets
        ],
        "structure": feedback,
        "overall_comment": OVERALL_COMMENT,
    }
    return SpeakingCorrectionOutput.model_validate(
        data,
        context=speaking_context(
            {u.index: u.text for u in found.sentences},
            set(found.taxonomy),
            {t.ref for t in found.targets},
            prepared.mode,
            found.text,
        ),
    )
