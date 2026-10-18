"""Output of the `transcript_analysis` task: the user's turns of a conversation, unit by unit.

Same pieces as `production_correction` (D-128), with units instead of sentences and no target
terms: the service stores the merged output with the `correction-1` keys (`format:
"transcript-1"`), so the screens reuse the highlighted view. The business rules run in a validator
that reads the request from the validation context (`transcript_context`, D-079): a broken rule is
a validation error, so the gateway asks for one repair, then answers `incomplete`. Messages name
locations, never the learner's text.
"""

from typing import Annotated, Any, Self

from pydantic import Field, ValidationInfo, model_validator

from app.ai.schemas import AiOutput
from app.ai.schemas.production_correction import (
    MAX_ALTERNATIVES,
    SLUG,
    Medium,
    ProposedSubcategory,
    SentenceStatus,
    Short,
    _Part,
)
from app.domain.sentences import find_fragment

MAX_ERRORS = 40


class CorrectedUnit(_Part):
    index: Annotated[int, Field(ge=1)]
    corrected: Annotated[str, Field(min_length=1, max_length=1200)]
    status: SentenceStatus


class TranscriptError(_Part):
    unit_index: Annotated[int, Field(ge=1)]
    wrong: Short
    correction: Short
    alternatives: Annotated[list[Short], Field(max_length=MAX_ALTERNATIVES)]
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    proposed_subcategory: ProposedSubcategory | None = None
    explanation_en: Medium
    explanation_fr: Medium


class TranscriptNote(_Part):
    """A correct but unnatural wording: advice, never an error."""

    unit_index: Annotated[int, Field(ge=1)]
    text: Short
    suggestion: Short
    note: Medium


class TranscriptAnalysisOutput(AiOutput):
    units: Annotated[list[CorrectedUnit], Field(min_length=1)]
    errors: list[TranscriptError]
    naturalness_notes: list[TranscriptNote]
    overall_comment: Annotated[str, Field(max_length=600)]

    @model_validator(mode="after")
    def matches_the_request(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        units: dict[int, str] | None = context.get("units")
        if units is None:
            return self
        codes: set[str] = context.get("codes", set())
        problems: list[str] = []
        if [u.index for u in self.units] != sorted(units):
            problems.append(f"units: the indices must be exactly {sorted(units)}, in order")
        if len(self.errors) > MAX_ERRORS:
            problems.append(f"errors: at most {MAX_ERRORS} errors")
        for i, error in enumerate(self.errors):
            problems += _error_problems(i, error, units, codes)
        status = {u.index: u.status for u in self.units}
        for index in sorted({e.unit_index for e in self.errors}):
            if status.get(index) == "correct":
                problems.append(f"units[index={index}]: has an error, so it is not 'correct'")
        for i, note in enumerate(self.naturalness_notes):
            if note.unit_index not in units:
                problems.append(f"naturalness_notes[{i}].unit_index: unknown unit")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _error_problems(
    i: int, error: TranscriptError, units: dict[int, str], codes: set[str]
) -> list[str]:
    at = f"errors[{i}]"
    problems: list[str] = []
    unit = units.get(error.unit_index)
    if unit is None:
        problems.append(f"{at}.unit_index: unknown unit")
    elif find_fragment(unit, error.wrong) is None:
        problems.append(
            f"{at}.wrong: must be copied exactly from unit {error.unit_index} (never from the "
            "context)"
        )
    if " ".join(error.wrong.split()) == " ".join(error.correction.split()):
        problems.append(f"{at}.correction: must differ from wrong")
    if error.category_code not in codes:
        problems.append(f"{at}.category_code: not one of the listed codes")
    proposal = error.proposed_subcategory
    if proposal is not None:
        if proposal.parent_code not in codes:
            problems.append(f"{at}.proposed_subcategory.parent_code: not one of the listed codes")
        if not SLUG.match(proposal.slug):
            problems.append(f"{at}.proposed_subcategory.slug: must match {SLUG.pattern}")
    return problems


def transcript_context(units: dict[int, str], codes: set[str]) -> dict[str, Any]:
    """What the validator needs: the units sent (index -> text) and the codes allowed (active,
    neither spelling nor pronunciation)."""
    return {"units": dict(units), "codes": set(codes)}
