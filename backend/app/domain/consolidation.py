"""Consolidation (module G, M7.a1): is a deck ready, which terms to use, the fallback templates.
Pure Python.

A deck is ready for a consolidation task when enough of its productive cards are stable and at
least `MIN_TERMS` of its terms are `consolidated` (not yet `active`). The task makes the learner
use 8 to 15 of those terms in a talk, a speech or an interview answer; a term well used becomes
`active` (M7.a2).

Task types and statuses are named as the API and the CLI name them (`talk`, `completed`); the
database enums keep their older names (`presentation`, `done`), the two are mapped here (D-223).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.enums import (
    ConsolidationTaskKind,
    ConsolidationTaskStatus,
    DeckKind,
    DeckStatus,
    ItemStatus,
)

MIN_TERMS = 8
MAX_TERMS = 15  # the limit of targets of the two correction tasks (D-128, D-180)
DEFAULT_TERMS = 12
RATIO_MIN, RATIO_MAX = 0.5, 1.0
MIN_SECTIONS, MAX_SECTIONS = 3, 6
MIN_MINUTES, MAX_MINUTES = 1, 6


class NotReadyReason(StrEnum):
    EXCLUDED_KIND = "excluded_kind"  # an error_drill deck
    DECK_DONE = "deck_done"
    TASK_OPEN = "task_open"
    NO_PRODUCTIVE_CARDS = "no_productive_cards"
    BELOW_RATIO = "below_ratio"
    NOT_ENOUGH_CANDIDATES = "not_enough_candidates"


# --- Task types and statuses ---------------------------------------------------------------------


class TaskType(StrEnum):
    TALK = "talk"
    SPEECH = "speech"
    INTERVIEW_ANSWER = "interview_answer"


_KIND_OF_TYPE = {
    TaskType.TALK: ConsolidationTaskKind.PRESENTATION,
    TaskType.SPEECH: ConsolidationTaskKind.SPEECH,
    TaskType.INTERVIEW_ANSWER: ConsolidationTaskKind.INTERVIEW_ANSWER,
}
_TYPE_OF_KIND = {kind: task_type for task_type, kind in _KIND_OF_TYPE.items()}


def kind_of(task_type: TaskType) -> ConsolidationTaskKind:
    return _KIND_OF_TYPE[task_type]


def type_of(kind: ConsolidationTaskKind) -> TaskType:
    return _TYPE_OF_KIND[ConsolidationTaskKind(kind)]


class TaskStatus(StrEnum):
    """The statuses as the API names them; the database says `done` for `completed`."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


_DB_OF_STATUS = {
    TaskStatus.PROPOSED: ConsolidationTaskStatus.PROPOSED,
    TaskStatus.ACCEPTED: ConsolidationTaskStatus.ACCEPTED,
    TaskStatus.COMPLETED: ConsolidationTaskStatus.DONE,
    TaskStatus.DISMISSED: ConsolidationTaskStatus.DISMISSED,
}
_STATUS_OF_DB = {db: status for status, db in _DB_OF_STATUS.items()}

OPEN_STATUSES = frozenset({ConsolidationTaskStatus.PROPOSED, ConsolidationTaskStatus.ACCEPTED})

TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PROPOSED: frozenset({TaskStatus.ACCEPTED, TaskStatus.DISMISSED}),
    TaskStatus.ACCEPTED: frozenset({TaskStatus.COMPLETED, TaskStatus.DISMISSED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.DISMISSED: frozenset(),
}


def db_status(status: TaskStatus) -> ConsolidationTaskStatus:
    return _DB_OF_STATUS[status]


def api_status(status: ConsolidationTaskStatus) -> TaskStatus:
    return _STATUS_OF_DB[ConsolidationTaskStatus(status)]


def can_transition(source: TaskStatus, target: TaskStatus) -> bool:
    return target in TRANSITIONS[source]


# --- Readiness -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductiveCard:
    """The productive card of one term of the deck."""

    item_id: int
    item_status: ItemStatus
    stability: float | None  # days; None while the card was never reviewed


@dataclass(frozen=True)
class Candidate:
    item_id: int
    stability: float


@dataclass(frozen=True)
class Readiness:
    ready: bool
    reason: NotReadyReason | None
    ratio: float  # stable cards / productive cards (0 when there is none)
    stable_cards: int
    productive_cards: int
    candidates: tuple[Candidate, ...]  # the most fragile first


# Terms that no longer take part in the count: archived by choice, or already known.
_LEFT_OUT = frozenset({ItemStatus.ARCHIVED, ItemStatus.KNOWN})


def clamp_ratio(value: float) -> float:
    return min(max(value, RATIO_MIN), RATIO_MAX)


def deck_readiness(
    *,
    kind: DeckKind,
    status: DeckStatus,
    cards: Sequence[ProductiveCard],
    open_task: bool,
    threshold_ratio: float,
    min_stability_days: float,
) -> Readiness:
    """Whether a deck can have a consolidation task, and if not, the first reason that applies
    (checked in the order of `NotReadyReason`).

    Denominator: the productive cards of the terms that are neither archived nor known. Numerator:
    those with a stability of at least `min_stability_days`. A paused deck is still eligible: the
    pause only stops new terms (D-026).
    """
    counted = [card for card in cards if card.item_status not in _LEFT_OUT]
    stable = [
        card
        for card in counted
        if card.stability is not None and card.stability >= min_stability_days
    ]
    ratio = len(stable) / len(counted) if counted else 0.0
    candidates = tuple(
        sorted(
            (
                Candidate(card.item_id, card.stability if card.stability is not None else 0.0)
                for card in counted
                if card.item_status is ItemStatus.CONSOLIDATED
            ),
            key=lambda c: (c.stability, c.item_id),
        )
    )
    reason: NotReadyReason | None = None
    if kind is DeckKind.ERROR_DRILL:
        reason = NotReadyReason.EXCLUDED_KIND
    elif status is DeckStatus.DONE:
        reason = NotReadyReason.DECK_DONE
    elif open_task:
        reason = NotReadyReason.TASK_OPEN
    elif not counted:
        reason = NotReadyReason.NO_PRODUCTIVE_CARDS
    elif ratio < clamp_ratio(threshold_ratio):
        reason = NotReadyReason.BELOW_RATIO
    elif len(candidates) < MIN_TERMS:
        reason = NotReadyReason.NOT_ENOUGH_CANDIDATES
    return Readiness(reason is None, reason, ratio, len(stable), len(counted), candidates)


def term_count(requested: int | None, available: int) -> int:
    """How many terms a task uses: `requested` (default `DEFAULT_TERMS`) kept within
    `MIN_TERMS`..`MAX_TERMS`, and never more than `available`."""
    wanted = DEFAULT_TERMS if requested is None else requested
    return max(0, min(max(wanted, MIN_TERMS), MAX_TERMS, available))


def select_terms(candidates: Sequence[Candidate], n: int | None = None) -> list[int]:
    """The item ids of the `n` most fragile candidates (lowest stability first, then lowest id)."""
    ordered = sorted(candidates, key=lambda c: (c.stability, c.item_id))
    return [c.item_id for c in ordered[: term_count(n, len(ordered))]]


def term_ref(position: int) -> str:
    """The reference of the term at `position` (from 0) in the AI prompt and the task."""
    return f"t{position + 1}"


# --- Fallback templates --------------------------------------------------------------------------

Short = Annotated[str, Field(min_length=1, max_length=300)]
Long = Annotated[str, Field(min_length=1, max_length=900)]


class Bilingual(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    en: Short
    fr: Short


class LongBilingual(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    en: Long
    fr: Long


class TemplateSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heading: Bilingual
    guidance: LongBilingual


class TaskTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: Bilingual
    prompt: LongBilingual
    audience: Bilingual
    target_minutes: Annotated[int, Field(ge=MIN_MINUTES, le=MAX_MINUTES)]
    sections: Annotated[list[TemplateSection], Field(min_length=4, max_length=5)]


class TemplatesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    templates: dict[TaskType, TaskTemplate]


class TemplatesError(ValueError):
    """The templates file is malformed."""


def parse_templates(data: Any) -> dict[TaskType, TaskTemplate]:
    """The templates of `content/consolidation_templates.yaml`: one per task type."""
    try:
        parsed = TemplatesFile.model_validate(data)
    except ValidationError as exc:
        raise TemplatesError(f"invalid consolidation templates file: {exc}") from exc
    missing = [t.value for t in TaskType if t not in parsed.templates]
    if missing:
        raise TemplatesError(f"consolidation templates: missing {', '.join(missing)}")
    return parsed.templates


_PLACEHOLDER = re.compile(r"\{(deck|domain)\}")
_NO_DOMAIN = {"en": "your field", "fr": "votre domaine"}


def _fill(text: str, deck: str, domain: str) -> str:
    return _PLACEHOLDER.sub(lambda m: deck if m.group(1) == "deck" else domain, text)


def template_task(
    template: TaskTemplate,
    *,
    task_type: TaskType,
    deck_name: str,
    domain: str | None,
    refs: list[str],
) -> dict[str, Any]:
    """A task built from a template, in the shape of the `consolidation_task` output: the terms
    (`refs`, in selection order) are spread over the sections in turn."""
    section_refs: list[list[str]] = [[] for _ in template.sections]
    for position, ref in enumerate(refs):
        section_refs[position % len(template.sections)].append(ref)

    def both(text_en: str, text_fr: str) -> tuple[str, str]:
        return (
            _fill(text_en, deck_name, domain or _NO_DOMAIN["en"]),
            _fill(text_fr, deck_name, domain or _NO_DOMAIN["fr"]),
        )

    title_en, title_fr = both(template.title.en, template.title.fr)
    prompt_en, prompt_fr = both(template.prompt.en, template.prompt.fr)
    audience_en, audience_fr = both(template.audience.en, template.audience.fr)
    return {
        "task_type": task_type.value,
        "title_en": title_en,
        "title_fr": title_fr,
        "prompt_en": prompt_en,
        "prompt_fr": prompt_fr,
        "audience_en": audience_en,
        "audience_fr": audience_fr,
        "target_minutes": template.target_minutes,
        "sections": [
            {
                "heading_en": section.heading.en,
                "heading_fr": section.heading.fr,
                "guidance_en": section.guidance.en,
                "guidance_fr": section.guidance.fr,
                "term_refs": section_refs[i],
            }
            for i, section in enumerate(template.sections)
        ],
    }
