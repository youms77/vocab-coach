"""Output of the `speaking_correction` task: a transcription corrected unit by unit (module F).

The output of `production_correction` (D-128), inherited with every one of its validators (units
are sent as `sentences`, so the screens reuse the highlighted view), plus a comment on the
structure of the speech: its organisation, the connectors the learner said and up to three
suggestions. A unit of transcribed speech can be long (speech recognition punctuates little), so
its corrected text may be longer than a written sentence's. The rules that depend on the request
run in a validator that reads the validation context (`speaking_context`, D-079): a broken rule
is a validation error, so the gateway asks for one repair, then answers `incomplete`. Messages name
locations, never the learner's text.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from app.ai.schemas.production_correction import (
    CorrectedSentence,
    Medium,
    ProductionCorrectionOutput,
    Short,
    _Part,
    correction_context,
)
from app.domain.sentences import find_fragment, split_sentences

MAX_CONNECTORS = 10
MAX_SUGGESTIONS = 3
MAX_COMMENT_SENTENCES = 3
# A unit holds whole sentences of a text of at most 4 000 characters (`speech_units`), and its
# corrected version may add a few words.
MAX_CORRECTED_UNIT_CHARS = 4500

Mode = Literal["answer", "monologue"]


class SpokenUnit(CorrectedSentence):
    corrected: Annotated[str, Field(min_length=1, max_length=MAX_CORRECTED_UNIT_CHARS)]


class StructureSuggestion(_Part):
    text_en: Short
    text_fr: Short


class StructureFeedback(_Part):
    """How the speech is built: never an error, only advice."""

    comment_en: Medium
    comment_fr: Medium
    connectors_used: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=100)]],
        Field(max_length=MAX_CONNECTORS),
    ]
    suggestions: Annotated[list[StructureSuggestion], Field(max_length=MAX_SUGGESTIONS)]


class SpeakingCorrectionOutput(ProductionCorrectionOutput):
    sentences: Annotated[list[SpokenUnit], Field(min_length=1)]  # type: ignore[assignment]
    structure: StructureFeedback | None = None

    @model_validator(mode="after")
    def fits_the_speech(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        if context.get("sentences") is None:
            return self
        text: str = context.get("text", "")
        problems: list[str] = []
        structure = self.structure
        if structure is None:
            if context.get("mode") == "monologue":
                problems.append("structure: required in monologue mode")
        else:
            for name in ("comment_en", "comment_fr"):
                count = len(split_sentences(getattr(structure, name), max_sentences=None))
                if not 1 <= count <= MAX_COMMENT_SENTENCES:
                    problems.append(f"structure.{name}: 1 to {MAX_COMMENT_SENTENCES} sentences")
            for i, connector in enumerate(structure.connectors_used):
                if find_fragment(text, connector) is None:
                    problems.append(
                        f"structure.connectors_used[{i}]: must be copied exactly from the units"
                    )
        if problems:
            raise ValueError("; ".join(problems))
        return self


def speaking_context(
    units: dict[int, str], codes: set[str], target_refs: set[int], mode: Mode, text: str
) -> dict[str, Any]:
    """What the validators need: the units sent (as `sentences`), the codes allowed (active,
    neither spelling nor pronunciation), the refs of the targets sent, the mode and the whole
    transcription (where the connectors must be found)."""
    return correction_context(units, codes, target_refs) | {"mode": mode, "text": text}
