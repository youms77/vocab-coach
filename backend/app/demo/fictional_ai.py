"""Fictional AI outputs for the demo (D-163).

The demo never calls an AI. Its corrections, transcript analyses and drills are built here from the
fictional dataset as the outputs the AI tasks would have returned, **validated by the real output
schemas** with the real validation contexts, then stored by the same services as a real result
(`corrections.store_correction`, `transcripts.store_analysis`, `drills.store_drill`). A template
that does not fit its sentence is a bug of the dataset and raises.
"""

from typing import Any

from app.ai.schemas.production_correction import (
    ProductionCorrectionOutput,
    correction_context,
)
from app.ai.schemas.targeted_drill import TargetedDrillOutput, drill_context
from app.ai.schemas.transcript_analysis import TranscriptAnalysisOutput, transcript_context
from app.demo.dataset import DemoDrill, ErrorTemplate
from app.domain.sentences import find_fragment
from app.domain.transcript_import import Unit
from app.services import corrections, transcripts

CORRECTION_PROVENANCE = ("demo", None, "demo-correction-v1")
TRANSCRIPT_PROVENANCE = ("demo", None, "demo-transcript-v1")
DRILL_PROVENANCE = ("demo", None, "demo-drill-v1")
OVERALL_COMMENT = "Fictional correction written for the demo."


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
