"""Load and validate the fictional demo dataset in `content/demo/` (D-033)."""

from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import REPO_ROOT
from app.domain.enums import DeckStatus, ItemType, ProductionKind

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


class ProductionPrompt(_Strict):
    kind: Literal[
        ProductionKind.WRITING, ProductionKind.SPEAKING, ProductionKind.TRANSCRIPT_ANALYSIS
    ]
    text: str


class DemoDataset(_Strict):
    dataset_version: int
    decks: list[DemoDeck]
    error_templates: list[ErrorTemplate]
    error_rates: dict[str, tuple[float, float]]
    default_error_rate: float
    prompts: list[ProductionPrompt]
    fillers: list[str]

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
        days = [deck.created_day for deck in self.decks]
        if days != sorted(days):
            raise ValueError("decks must be listed in creation order")
        return self

    def error_codes(self) -> list[str]:
        """Every taxonomy code the dataset uses, sorted."""
        codes = {t.code for t in self.error_templates} | set(self.error_rates)
        codes |= {term.confusion.code for term in self.all_terms() if term.confusion}
        return sorted(codes)

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
    """Read the three demo files; they must share the same `dataset_version`."""
    decks = _read(directory / "dataset.yaml")
    errors = _read(directory / "errors.yaml")
    prompts = _read(directory / "prompts.yaml")
    versions = {decks["dataset_version"], errors["dataset_version"], prompts["dataset_version"]}
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
    )


def anchor_offset_day(anchor: date, offset: int) -> date:
    """Study day `offset` days from the anchor (negative = before)."""
    return date.fromordinal(anchor.toordinal() + offset)
