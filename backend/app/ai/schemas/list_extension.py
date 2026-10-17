"""Output of the `list_extension` task: related terms suggested for a deck.

No definition on purpose: the suggestions go through the intake triage, which must not be biased
by a sheet (D-075). The example sentence becomes the deck's context sentence of the new term.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.schemas import AiOutput
from app.domain.enums import ItemType
from app.domain.exercises import contains_term

MIN_COUNT, MAX_COUNT, DEFAULT_COUNT = 10, 30, 20
MAX_TERM_WORDS = 10


class SuggestionCategory(StrEnum):
    TECHNICAL = "technical"  # terms of the deck's field
    ACADEMIC = "academic"  # general academic vocabulary
    SPOKEN = "spoken"  # spoken formulas to present the topic


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    term: Annotated[str, Field(min_length=1, max_length=300)]
    item_type: ItemType
    category: SuggestionCategory
    example_sentence: Annotated[str, Field(min_length=1, max_length=400)]


class ListExtensionOutput(AiOutput):
    suggestions: Annotated[list[Suggestion], Field(min_length=1, max_length=MAX_COUNT + 5)]

    @model_validator(mode="after")
    def usable_terms(self) -> Self:
        problems = []
        for i, suggestion in enumerate(self.suggestions):
            term = suggestion.term
            if "|" in term or "\n" in term or len(term.split()) > MAX_TERM_WORDS:
                problems.append(f"suggestions[{i}].term: one short term, no '|' nor line break")
            elif not contains_term(term, suggestion.example_sentence):
                problems.append(f"suggestions[{i}].example_sentence: must contain the term")
        if problems:
            raise ValueError("; ".join(problems[:8]))
        return self
