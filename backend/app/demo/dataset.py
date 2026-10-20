"""Load and validate the fictional demo dataset in `content/demo/` (D-033)."""

from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import REPO_ROOT
from app.domain.enums import DeckStatus, ItemType, ProductionKind
from app.domain.exercises import (
    GapFillContent,
    RecognitionContent,
    SentenceProductionContent,
    SpokenAnswerContent,
)
from app.domain.usage_sheet import UsageSheet

DEMO_CONTENT_DIR = REPO_ROOT / "content" / "demo"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Fate(StrEnum):
    """Final status the simulation guarantees for a term (others follow the simulation)."""

    DRAFT = "draft"
    TRIAGE = "triage"
    KNOWN = "known"
    ARCHIVED = "archived"
    ACTIVE = "active"


class Confusion(_Strict):
    """A lexical error made when a productive review of the term fails."""

    prompt: str
    wrong: str
    code: str
    explanation: str


class DemoTerm(_Strict):
    term: str
    type: ItemType
    pos: str | None = None
    sentence: str | None = None
    fate: Fate | None = None
    confusion: Confusion | None = None


class DemoTermRef(_Strict):
    """A term already defined in an earlier deck, linked to this one too."""

    ref: str


class DemoSource(_Strict):
    title: str
    author: str | None = None


class StatusEvent(_Strict):
    day: Annotated[int, Field(lt=0)]
    to: DeckStatus


class TriageBatch(_Strict):
    day: Annotated[int, Field(lt=0)]
    count: Annotated[int, Field(ge=1)]


class DemoDeck(_Strict):
    key: str
    name: str
    domain: str | None = None
    description: str | None = None
    source: DemoSource | None = None
    created_day: Annotated[int, Field(lt=0)]
    intake: Literal["queue", "triage"]
    queue: Literal["back", "front"] = "back"
    # Relative to the anchor; negative days are scaled with the history, positive ones are not.
    deadline_day: int | None = None
    status_events: list[StatusEvent] = []
    triage_batches: list[TriageBatch] = []
    terms: list[DemoTerm | DemoTermRef]

    def own_terms(self) -> list[DemoTerm]:
        return [entry for entry in self.terms if isinstance(entry, DemoTerm)]


class ErrorTemplate(_Strict):
    code: str
    original: str
    wrong: str
    correction: str
    alternatives: Annotated[list[str], Field(min_length=1, max_length=2)]
    explanation: str
    explanation_fr: str


class ProductionPrompt(_Strict):
    kind: Literal[
        ProductionKind.WRITING, ProductionKind.SPEAKING, ProductionKind.TRANSCRIPT_ANALYSIS
    ]
    text: str


class DemoDrillItem(_Strict):
    """An item of the `targeted_drill` schema plus what the simulated learner types when they
    miss it (`wrong`, gap-fill only)."""

    kind: Literal["gap_fill", "choice"]
    sentence: str
    answer: str
    accepted: list[str] = []
    options: list[str] | None = None
    category_code: str
    theme: Literal["campus", "data_economics", "everyday"]
    explanation_en: str
    explanation_fr: str
    wrong: str | None = None

    @model_validator(mode="after")
    def a_gap_fill_has_a_wrong_answer(self) -> "DemoDrillItem":
        if self.kind == "gap_fill" and not self.wrong:
            raise ValueError(f"gap-fill item {self.sentence!r} needs a `wrong` answer")
        return self


class DemoDrill(_Strict):
    """A drill as the AI would have written it (`TargetedDrillOutput`), for one category."""

    code: str
    rule_en: str
    rule_fr: str
    items: Annotated[list[DemoDrillItem], Field(min_length=5, max_length=15)]

    def output(self) -> dict[str, Any]:
        """The `targeted_drill` output (the demo-only `wrong` left out)."""
        return {
            "rule_en": self.rule_en,
            "rule_fr": self.rule_fr,
            "items": [item.model_dump(exclude={"wrong"}) for item in self.items],
        }


class StructureSuggestion(_Strict):
    text_en: str
    text_fr: str


class StructureComment(_Strict):
    """A fictional comment on how a free speech is organised (`speaking_correction.structure`)."""

    comment_en: str
    comment_fr: str
    suggestions: Annotated[list[StructureSuggestion], Field(max_length=3)] = []


class DemoSpeech(_Strict):
    """What the fictional recogniser and corrector of spoken productions need (M6.a2b)."""

    connectors: Annotated[list[str], Field(min_length=1)]
    structure: Annotated[list[StructureComment], Field(min_length=1)]
    # What the learner says in a spoken answer when the term does not come.
    forgotten_answers: Annotated[list[str], Field(min_length=1)]


class DemoExercises(_Strict):
    """The exercise templates of a full demo sheet (one of each type; listening reuses the
    recognition sentence, typed recall is derived from the sheet)."""

    gap_fill: GapFillContent
    recognition_in_sentence: RecognitionContent
    sentence_production: SentenceProductionContent
    spoken_answer: SpokenAnswerContent


class DemoSheet(_Strict):
    """A hand-typed usage sheet: full (with exercises) or minimal (French translation only)."""

    term: str
    sheet: UsageSheet
    exercises: DemoExercises | None = None

    @property
    def full(self) -> bool:
        return self.exercises is not None


class DemoDataset(_Strict):
    dataset_version: int
    decks: list[DemoDeck]
    error_templates: list[ErrorTemplate]
    error_rates: dict[str, tuple[float, float]]
    default_error_rate: float
    prompts: list[ProductionPrompt]
    fillers: list[str]
    tutor_lines: Annotated[list[str], Field(min_length=1)]
    speech: DemoSpeech
    sheets: list[DemoSheet] = []
    drills: list[DemoDrill] = []

    @model_validator(mode="after")
    def check_consistency(self) -> "DemoDataset":
        defined: set[str] = set()
        for deck in self.decks:
            in_deck: set[str] = set()
            for entry in deck.terms:
                name = entry.ref if isinstance(entry, DemoTermRef) else entry.term
                key = name.lower()
                if key in in_deck:
                    raise ValueError(f"deck {deck.key}: term {name!r} listed twice")
                in_deck.add(key)
                if isinstance(entry, DemoTermRef):
                    if key not in defined:
                        raise ValueError(f"deck {deck.key}: ref {name!r} is not defined earlier")
                elif key in defined:
                    raise ValueError(f"deck {deck.key}: {name!r} is defined twice; use `ref`")
                else:
                    defined.add(key)
        sheet_terms = [sheet.term.lower() for sheet in self.sheets]
        if len(sheet_terms) != len(set(sheet_terms)):
            raise ValueError("sheets.yaml: a term has two sheets")
        unknown = sorted(set(sheet_terms) - defined)
        if unknown:
            raise ValueError(f"sheets.yaml: terms not in the dataset: {', '.join(unknown)}")
        codes = [drill.code for drill in self.drills]
        if len(codes) != len(set(codes)):
            raise ValueError("drills.yaml: a category has two drills")
        for drill in self.drills:
            wrong_codes = {i.category_code for i in drill.items if i.category_code != drill.code}
            if wrong_codes:
                raise ValueError(f"drills.yaml: items of {drill.code} use {sorted(wrong_codes)}")
        days = [deck.created_day for deck in self.decks]
        if days != sorted(days):
            raise ValueError("decks must be listed in creation order")
        return self

    def error_codes(self) -> list[str]:
        """Every taxonomy code the dataset uses, sorted."""
        codes = {t.code for t in self.error_templates} | set(self.error_rates)
        codes |= {term.confusion.code for term in self.all_terms() if term.confusion}
        codes |= {drill.code for drill in self.drills}
        return sorted(codes)

    def sheet_of(self, term: str) -> DemoSheet | None:
        return next((s for s in self.sheets if s.term.lower() == term.lower()), None)

    def all_terms(self) -> Iterable[DemoTerm]:
        for deck in self.decks:
            yield from deck.own_terms()

    def check_codes(self, known_codes: Iterable[str]) -> None:
        """Raise ValueError if a code is missing from the error taxonomy."""
        missing = sorted(set(self.error_codes()) - set(known_codes))
        if missing:
            raise ValueError(f"error codes missing from the taxonomy: {', '.join(missing)}")


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_dataset(directory: Path = DEMO_CONTENT_DIR) -> DemoDataset:
    """Read the five demo files; they must share the same `dataset_version`."""
    decks = _read(directory / "dataset.yaml")
    errors = _read(directory / "errors.yaml")
    prompts = _read(directory / "prompts.yaml")
    sheets = _read(directory / "sheets.yaml")
    drills = _read(directory / "drills.yaml")
    versions = {
        decks["dataset_version"],
        errors["dataset_version"],
        prompts["dataset_version"],
        sheets["dataset_version"],
        drills["dataset_version"],
    }
    if len(versions) != 1:
        raise ValueError(f"content/demo files disagree on dataset_version: {sorted(versions)}")
    return DemoDataset(
        dataset_version=decks["dataset_version"],
        decks=decks["decks"],
        error_templates=errors["templates"],
        error_rates=errors.get("rates", {}),
        default_error_rate=errors["default_rate"],
        prompts=prompts["prompts"],
        fillers=prompts["fillers"],
        tutor_lines=prompts["tutor_lines"],
        speech=prompts["speech"],
        sheets=sheets["sheets"],
        drills=drills["drills"],
    )


def anchor_offset_day(anchor: date, offset: int) -> date:
    """Study day `offset` days from the anchor (negative = before)."""
    return date.fromordinal(anchor.toordinal() + offset)
