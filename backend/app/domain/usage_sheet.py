"""Usage sheet, schema version 1 (docs/SPEC.md module A). Pure Python: Pydantic models only.

Two models share the same field names:

- `UsageSheet` is the **stored** form (`enrichment.content`). It is lenient, because a sheet typed
  or edited by hand may be partial; it only asks for a simple definition or a French translation.
  A skeleton sheet (`needs_completion`, written when the AI failed) is the one exception: it is
  built by `skeleton_sheet()` and validated with the `skeleton` context.
- `GeneratedSheet` is what the AI must return. Every main field is required and lists have the
  minimum sizes of the SPEC. `to_stored()` turns it into a `UsageSheet`.

The schema stays shallow (at most two object levels inside a sheet) and has two enumerations only:
Gemini may refuse large or deeply nested schemas (D-056).
"""

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

SCHEMA_VERSION = 1

Short = Annotated[str, Field(max_length=300)]
Long = Annotated[str, Field(max_length=1200)]
Req = Annotated[str, Field(min_length=1, max_length=300)]
ReqLong = Annotated[str, Field(min_length=1, max_length=1200)]


class Register(StrEnum):
    ACADEMIC = "academic"
    NEUTRAL = "neutral"
    SPOKEN = "spoken"
    INFORMAL = "informal"


class ExampleKind(StrEnum):
    ACADEMIC = "academic"
    SPOKEN = "spoken"
    GENERAL = "general"


class _Part(BaseModel):
    """Entries of a sheet: unknown keys are dropped, never an error."""

    model_config = ConfigDict(extra="ignore")


# --- Entries (shared by both forms; `GeneratedSheet` requires the text) -------------------------


class OtherMeaning(_Part):
    definition: Req
    translation_fr: Req


class Collocation(_Part):
    pattern: Req
    example: Short | None = None


class Example(_Part):
    sentence: Req
    kind: ExampleKind


class WordForm(_Part):
    form: Annotated[str, Field(min_length=1, max_length=100)]
    part_of_speech: Annotated[str, Field(min_length=1, max_length=50)]


class Pitfall(_Part):
    wrong: Req
    right: Req
    explanation: Req


class Confusable(_Part):
    term: Annotated[str, Field(min_length=1, max_length=100)]
    difference: Req


class Pronunciation(_Part):
    ipa_us: Short | None = None
    stressed_syllable: Annotated[str, Field(max_length=50)] | None = None
    note: Short | None = None


class GeneratedPronunciation(_Part):
    ipa_us: Req
    stressed_syllable: Annotated[str, Field(min_length=1, max_length=50)]
    note: Short | None = None


# --- Stored form ---------------------------------------------------------------------------------


def _filled(value: str | None) -> bool:
    return bool(value and value.strip())


class UsageSheet(BaseModel):
    """`enrichment.content`, schema version 1. Lenient: a hand-typed sheet may be partial."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    part_of_speech: Annotated[str, Field(max_length=50)] | None = None
    register_level: Register | None = None
    register_note: Short | None = None
    meaning_in_context: Long | None = None
    definition_simple: Long | None = None
    translation_fr: Annotated[list[Req], Field(max_length=3)] = []
    other_meanings: Annotated[list[OtherMeaning], Field(max_length=3)] = []
    usage_notes: Long | None = None
    collocations: Annotated[list[Collocation], Field(max_length=8)] = []
    examples: Annotated[list[Example], Field(max_length=5)] = []
    word_family: Annotated[list[WordForm], Field(max_length=6)] = []
    pronunciation: Pronunciation | None = None
    french_speaker_pitfalls: Annotated[list[Pitfall], Field(max_length=4)] = []
    confusables: Annotated[list[Confusable], Field(max_length=3)] = []

    @model_validator(mode="after")
    def needs_a_meaning(self, info: ValidationInfo) -> Self:
        if (info.context or {}).get("skeleton"):
            return self
        if not _filled(self.definition_simple) and not any(map(_filled, self.translation_fr)):
            raise ValueError("a sheet needs at least a simple definition or a French translation")
        return self


def skeleton_sheet(part_of_speech: str | None = None) -> dict[str, Any]:
    """Minimal content of a `needs_completion` sheet: the AI failed, the user completes it."""
    sheet = UsageSheet.model_validate(
        {"part_of_speech": part_of_speech}, context={"skeleton": True}
    )
    return sheet.model_dump(mode="json")


def is_usable(status: str, content: dict[str, Any]) -> bool:
    """Can the term be discovered with this sheet? A complete sheet (AI or the user's) with a
    simple definition or a French translation; a `needs_completion` skeleton is not usable."""
    if status != "complete":
        return False
    sheet = read_sheet(content)
    return _filled(sheet.definition_simple) or any(map(_filled, sheet.translation_fr))


def read_sheet(content: dict[str, Any]) -> UsageSheet:
    """A stored sheet, skeletons included (the content was validated when it was written)."""
    return UsageSheet.model_validate(content, context={"skeleton": True})


# --- AI form -------------------------------------------------------------------------------------


class GeneratedSheet(BaseModel):
    """The sheet fields of the AI output: strict. Business rules (the term in every example...)
    are checked by `app/domain/exercises.py` through the batch schema."""

    model_config = ConfigDict(extra="ignore")

    part_of_speech: Annotated[str, Field(min_length=1, max_length=50)]
    register_level: Register
    register_note: Short | None = None
    meaning_in_context: ReqLong
    definition_simple: ReqLong
    translation_fr: Annotated[list[Req], Field(min_length=1, max_length=3)]
    other_meanings: Annotated[list[OtherMeaning], Field(max_length=3)]
    usage_notes: ReqLong
    collocations: Annotated[list[Collocation], Field(min_length=3, max_length=8)]
    examples: Annotated[list[Example], Field(min_length=3, max_length=5)]
    word_family: Annotated[list[WordForm], Field(max_length=6)]
    pronunciation: GeneratedPronunciation
    french_speaker_pitfalls: Annotated[list[Pitfall], Field(max_length=4)]
    confusables: Annotated[list[Confusable], Field(max_length=3)]

    def to_stored(self) -> UsageSheet:
        return UsageSheet.model_validate(self.model_dump(mode="json", include=set(SHEET_FIELDS)))


# The sheet fields, in display order (both models share them; a test checks it).
SHEET_FIELDS: tuple[str, ...] = tuple(
    name for name in UsageSheet.model_fields if name != "schema_version"
)
