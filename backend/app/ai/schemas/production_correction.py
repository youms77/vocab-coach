"""Output of the `production_correction` task: a written production corrected sentence by sentence.

The business rules run in a validator that reads the request from the validation context
(`correction_context`, D-079): a broken rule is a validation error, so the gateway asks for one
repair, then answers `incomplete`. Messages name locations, never the learner's text.
"""

import re
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from app.ai.schemas import AiOutput
from app.domain.sentences import find_fragment

MAX_ERRORS = 30
MAX_ALTERNATIVES = 2
SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

Short = Annotated[str, Field(min_length=1, max_length=300)]
Medium = Annotated[str, Field(min_length=1, max_length=600)]
SentenceStatus = Literal["correct", "corrected", "unnatural"]


class _Part(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CorrectedSentence(_Part):
    index: Annotated[int, Field(ge=0)]
    corrected: Annotated[str, Field(min_length=1, max_length=1200)]
    status: SentenceStatus


class ProposedSubcategory(_Part):
    parent_code: Annotated[str, Field(min_length=1, max_length=200)]
    slug: Annotated[str, Field(min_length=1, max_length=60)]
    label_en: Short
    label_fr: Short
    description_en: Medium


class CorrectionError(_Part):
    sentence_index: Annotated[int, Field(ge=0)]
    wrong: Short
    correction: Short
    alternatives: Annotated[list[Short], Field(max_length=MAX_ALTERNATIVES)]
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    proposed_subcategory: ProposedSubcategory | None = None
    explanation_en: Medium  # the rule in one sentence, simple B1-B2 English
    explanation_fr: Medium
    target_ref: Annotated[int, Field(ge=0)] | None = None


class NaturalnessNote(_Part):
    """A correct but unnatural wording. It is advice, never an error."""

    sentence_index: Annotated[int, Field(ge=0)]
    text: Short
    suggestion: Short
    note: Medium


class TargetCheck(_Part):
    ref: Annotated[int, Field(ge=0)]
    used: bool
    used_correctly: bool
    comment: Annotated[str, Field(max_length=600)]


class ProductionCorrectionOutput(AiOutput):
    sentences: Annotated[list[CorrectedSentence], Field(min_length=1)]
    corrected_text: Annotated[str, Field(min_length=1, max_length=6000)]
    natural_text: Annotated[str, Field(min_length=1, max_length=6000)]
    errors: list[CorrectionError]
    naturalness_notes: list[NaturalnessNote]
    targets: list[TargetCheck]
    overall_comment: Annotated[str, Field(max_length=600)]

    @model_validator(mode="after")
    def matches_the_request(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        sentences: dict[int, str] | None = context.get("sentences")
        if sentences is None:
            return self
        codes: set[str] = context.get("codes", set())
        refs: set[int] = context.get("target_refs", set())
        problems = self._sentence_problems(sentences)
        if len(self.errors) > MAX_ERRORS:
            problems.append(f"errors: at most {MAX_ERRORS} errors")
        status = {s.index: s.status for s in self.sentences}
        with_error = {e.sentence_index for e in self.errors}
        for i, error in enumerate(self.errors):
            problems += _error_problems(i, error, sentences, codes, refs)
        for index in sorted(with_error):
            if status.get(index) == "correct":
                problems.append(f"sentences[index={index}]: has an error, so it is not 'correct'")
        for i, note in enumerate(self.naturalness_notes):
            if note.sentence_index not in sentences:
                problems.append(f"naturalness_notes[{i}].sentence_index: unknown sentence")
        seen: set[int] = set()
        for i, check in enumerate(self.targets):
            if check.ref not in refs:
                problems.append(f"targets[{i}].ref: unknown target")
            elif check.ref in seen:
                problems.append(f"targets[{i}].ref: each target must appear only once")
            seen.add(check.ref)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _sentence_problems(self, sentences: dict[int, str]) -> list[str]:
        given = [s.index for s in self.sentences]
        if given != sorted(sentences):
            return [f"sentences: the indices must be exactly {sorted(sentences)}, in order"]
        return []


def _error_problems(
    i: int, error: CorrectionError, sentences: dict[int, str], codes: set[str], refs: set[int]
) -> list[str]:
    at = f"errors[{i}]"
    problems: list[str] = []
    sentence = sentences.get(error.sentence_index)
    if sentence is None:
        problems.append(f"{at}.sentence_index: unknown sentence")
    elif find_fragment(sentence, error.wrong) is None:
        problems.append(f"{at}.wrong: must be copied exactly from sentence {error.sentence_index}")
    if " ".join(error.wrong.split()) == " ".join(error.correction.split()):
        problems.append(f"{at}.correction: must differ from wrong")
    if error.category_code not in codes:
        problems.append(f"{at}.category_code: not an active code of the taxonomy")
    proposal = error.proposed_subcategory
    if proposal is not None:
        if proposal.parent_code not in codes:
            problems.append(f"{at}.proposed_subcategory.parent_code: not an active code")
        if not SLUG.match(proposal.slug):
            problems.append(f"{at}.proposed_subcategory.slug: must match {SLUG.pattern}")
    if error.target_ref is not None and error.target_ref not in refs:
        problems.append(f"{at}.target_ref: unknown target")
    return problems


def correction_context(
    sentences: dict[int, str], codes: set[str], target_refs: set[int]
) -> dict[str, Any]:
    """What the validator needs: the numbered sentences sent, the active category codes and the
    refs of the targets sent."""
    return {"sentences": dict(sentences), "codes": set(codes), "target_refs": set(target_refs)}
