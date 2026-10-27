"""Consolidation tasks (module G, M7.a1): which decks are ready, creating a task, its statuses, the
export for a voice tutor.

Creation (`create_task`, D-038): a short read session checks the deck, picks the terms and reads
their sheets, then closes; the AI is called with no session open; then one short write
transaction re-checks the deck (409 `task_open` when another task appeared meanwhile) and stores
the task with `store_task`. When the AI is unavailable or its answer unusable, the task is built
from a template (`content/consolidation_templates.yaml`) and the result says why: without a key
or a network the user can still consolidate.

Schema (no migration, D-223): `consolidation_task.topic` holds the English title; everything else
(both languages, sections, provenance) is in `suggested_structure` (`format:
"consolidation-task-1"`); the order of the terms is the order of the `consolidation_task_item` rows.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.consolidation_task import ConsolidationTaskOutput, consolidation_context
from app.ai.tasks import CONSOLIDATION_MAX_OUTPUT_TOKENS
from app.ai.types import AiStatus
from app.config import REPO_ROOT
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import (
    Card,
    ConsolidationTask,
    ConsolidationTaskItem,
    Deck,
    DeckItem,
    ErrorEvent,
    EventLog,
    LexicalItem,
    ProductionAttempt,
    Source,
    StudySession,
)
from app.db.settings_store import get_setting
from app.domain import consolidation as rules
from app.domain.consolidation import (
    NotReadyReason,
    ProductiveCard,
    Readiness,
    TaskStatus,
    TaskType,
)
from app.domain.enums import CardDirection, ConsolidationTaskStatus, ItemStatus
from app.domain.events import (
    ConsolidationAttemptChecked,
    ConsolidationTaskCreated,
    ConsolidationTaskStatusChanged,
    EventType,
)
from app.domain.study_day import as_utc
from app.domain.usage_sheet import read_sheet
from app.services.library import DeckNotFound, LibraryError
from app.services.study_sessions import SessionNotFound

TASK = "consolidation_task"
STRUCTURE_FORMAT = "consolidation-task-1"
TEMPLATES_FILE = REPO_ROOT / "content" / "consolidation_templates.yaml"
EXPORT_FILE = REPO_ROOT / "content" / "consolidation_export.yaml"
MAX_PAGE_SIZE = 100
DECK_FIELD_CHARS = 700  # description and source title sent to the AI
DEFINITION_CHARS = 300

SessionFactory = Callable[[], Session]


class TaskNotFound(LibraryError):
    status, code = 404, "task_not_found"


class NotReady(LibraryError):
    status, code = 409, "not_ready"


class TaskOpen(LibraryError):
    status, code = 409, "task_open"


class InvalidTransition(LibraryError):
    status, code = 409, "invalid_transition"


# --- Readiness -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DeckState:
    deck: Deck
    readiness: Readiness
    open_task_id: int | None
    threshold_ratio: float
    min_stability_days: int


def open_task_id(session: Session, deck_id: int) -> int | None:
    return session.scalar(
        select(ConsolidationTask.id)
        .where(
            ConsolidationTask.deck_id == deck_id,
            ConsolidationTask.status.in_(rules.OPEN_STATUSES),
        )
        .order_by(ConsolidationTask.id)
        .limit(1)
    )


def productive_cards(session: Session, deck_id: int) -> list[ProductiveCard]:
    rows = session.execute(
        select(LexicalItem.id, LexicalItem.status, Card.stability)
        .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
        .join(Card, Card.lexical_item_id == LexicalItem.id)
        .where(DeckItem.deck_id == deck_id, Card.direction == CardDirection.PRODUCTIVE)
        .order_by(LexicalItem.id)
    )
    return [ProductiveCard(item_id, ItemStatus(status), stab) for item_id, status, stab in rows]


def deck_state(session: Session, deck: Deck) -> DeckState:
    threshold = rules.clamp_ratio(get_setting(session, "consolidation_share"))
    min_days = get_setting(session, "consolidation_min_stability_days")
    open_id = open_task_id(session, deck.id)
    readiness = rules.deck_readiness(
        kind=deck.kind,
        status=deck.status,
        cards=productive_cards(session, deck.id),
        open_task=open_id is not None,
        threshold_ratio=threshold,
        min_stability_days=min_days,
    )
    return DeckState(deck, readiness, open_id, threshold, min_days)


def deck_overview(session: Session) -> list[DeckState]:
    """One state per deck, in id order."""
    return [deck_state(session, deck) for deck in session.scalars(select(Deck).order_by(Deck.id))]


def _check_ready(state: DeckState) -> None:
    readiness = state.readiness
    if readiness.ready:
        return
    reason = readiness.reason
    if reason is NotReadyReason.TASK_OPEN:
        raise TaskOpen(
            "This deck already has an open consolidation task.", task_id=state.open_task_id
        )
    assert reason is not None  # noqa: S101 (narrowing)
    raise NotReady("This deck is not ready for a consolidation task.", reason=reason.value)


# --- Templates -----------------------------------------------------------------------------------


@cache
def load_templates(path: Path = TEMPLATES_FILE) -> dict[TaskType, rules.TaskTemplate]:
    with path.open(encoding="utf-8") as file:
        return rules.parse_templates(yaml.safe_load(file))


# --- Creation ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Prepared:
    deck_id: int
    deck_name: str
    domain: str | None
    task_type: TaskType
    item_ids: list[int]  # in selection order
    refs: list[str]
    deck_text: str
    terms_text: str
    study_session_id: int | None


def _line(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _definition(session: Session, item: LexicalItem) -> str:
    from app.services.enrichment import current_sheet

    sheet = current_sheet(session, item.id)
    if sheet is None:
        return ""
    content = read_sheet(dict(sheet.content))
    return _line(content.definition_simple or content.meaning_in_context, DEFINITION_CHARS)


def prepare(
    session: Session,
    deck_id: int,
    task_type: TaskType,
    term_count: int | None,
    study_session_id: int | None,
) -> Prepared:
    """Raises DeckNotFound, NotReady, TaskOpen, SessionNotFound."""
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise DeckNotFound(f"There is no deck {deck_id}.")
    if study_session_id is not None and session.get(StudySession, study_session_id) is None:
        raise SessionNotFound(f"There is no study session {study_session_id}.")
    state = deck_state(session, deck)
    _check_ready(state)
    item_ids = rules.select_terms(state.readiness.candidates, term_count)
    items = {
        i.id: i for i in session.scalars(select(LexicalItem).where(LexicalItem.id.in_(item_ids)))
    }
    refs = [rules.term_ref(position) for position in range(len(item_ids))]
    lines = [
        json.dumps(
            {
                "ref": ref,
                "term": items[item_id].term,
                "item_type": str(items[item_id].item_type),
                "definition_simple": _definition(session, items[item_id]),
            },
            ensure_ascii=False,
        )
        for ref, item_id in zip(refs, item_ids, strict=True)
    ]
    source = session.get(Source, deck.source_id) if deck.source_id is not None else None
    deck_text = "\n".join(
        [
            f"Name: {_line(deck.name, 300)}",
            f"Domain: {_line(deck.domain, 200) or '(none)'}",
            f"Description: {_line(deck.description, DECK_FIELD_CHARS) or '(none)'}",
            f"Source: {_line(source.title if source else None, DECK_FIELD_CHARS) or '(none)'}",
        ]
    )
    return Prepared(
        deck_id=deck.id,
        deck_name=deck.name,
        domain=deck.domain,
        task_type=task_type,
        item_ids=item_ids,
        refs=refs,
        deck_text=deck_text,
        terms_text="\n".join(lines),
        study_session_id=study_session_id,
    )


def store_task(
    session: Session,
    *,
    deck_id: int,
    task_type: TaskType,
    output: ConsolidationTaskOutput,
    item_ids: list[int],
    refs: list[str],
    source: Literal["ai", "template"],
    reason: str | None,
    provenance: tuple[str | None, str | None, str | None] = (None, None, None),
    ai_call_id: int | None = None,
    study_session_id: int | None = None,
    at: datetime,
) -> ConsolidationTask:
    """Write a task in the caller's transaction (no commit): the task, its terms in selection
    order and `consolidation.task_created`. The AI path, the template path and the demo come
    through here. Does not check readiness (the caller does)."""
    at = as_utc(at)
    item_of = dict(zip(refs, item_ids, strict=True))
    provider, model, prompt_version = provenance
    structure: dict[str, Any] = {
        "format": STRUCTURE_FORMAT,
        "task_type": task_type.value,
        "source": source,
        "reason": reason,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "ai_call_id": ai_call_id,
        "title": {"en": output.title_en, "fr": output.title_fr},
        "prompt": {"en": output.prompt_en, "fr": output.prompt_fr},
        "audience": {"en": output.audience_en, "fr": output.audience_fr},
        "target_minutes": output.target_minutes,
        "sections": [
            {
                "heading": {"en": s.heading_en, "fr": s.heading_fr},
                "guidance": {"en": s.guidance_en, "fr": s.guidance_fr},
                "item_ids": [item_of[ref] for ref in s.term_refs],
            }
            for s in output.sections
        ],
        "study_session_id": study_session_id,
    }
    task = ConsolidationTask(
        deck_id=deck_id,
        topic=output.title_en,
        task_kind=rules.kind_of(task_type),
        suggested_structure=structure,
        status=ConsolidationTaskStatus.PROPOSED,
        created_at=at,
        updated_at=at,
    )
    session.add(task)
    session.flush()
    for item_id in item_ids:
        session.add(ConsolidationTaskItem(consolidation_task_id=task.id, lexical_item_id=item_id))
        session.flush()  # ids grow in selection order
    record_event(
        session,
        ConsolidationTaskCreated(
            task_id=task.id,
            deck_id=deck_id,
            task_type=task_type.value,
            source=source,
            term_count=len(item_ids),
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    return task


@dataclass(frozen=True)
class CreationResult:
    task_id: int
    source: Literal["ai", "template"]
    reason: str | None  # why a template was used


def create_task(
    session_factory: SessionFactory,
    gateway: Gateway,
    deck_id: int,
    task_type: TaskType,
    *,
    term_count: int | None = None,
    study_session_id: int | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> CreationResult:
    """See the module docstring. Raises DeckNotFound, NotReady, TaskOpen, SessionNotFound. An AI
    failure is not an error: the task comes from a template."""
    with session_factory() as session:
        prepared = prepare(session, deck_id, task_type, term_count, study_session_id)
        session.rollback()  # nothing stays open during the AI call
    result = gateway.generate_json(
        TASK,
        {
            "deck": prepared.deck_text,
            "terms": prepared.terms_text,
            "task_type": task_type.value,
            "term_count": str(len(prepared.item_ids)),
        },
        ConsolidationTaskOutput,
        validation_context=consolidation_context(prepared.refs, task_type.value),
        max_output_tokens=CONSOLIDATION_MAX_OUTPUT_TOKENS,
    )
    source: Literal["ai", "template"]
    if result.status is AiStatus.OK and result.data is not None:
        source, reason = "ai", None
        output = result.data
        provenance = (result.provider, result.model, result.prompt_version)
        call_id = result.call_id
    else:
        source = "template"
        reason = "incomplete" if result.status is AiStatus.INCOMPLETE else str(result.reason)
        built = rules.template_task(
            load_templates()[task_type],
            task_type=task_type,
            deck_name=prepared.deck_name,
            domain=prepared.domain,
            refs=prepared.refs,
        )
        output = ConsolidationTaskOutput.model_validate(
            built, context=consolidation_context(prepared.refs, task_type.value)
        )
        provenance, call_id = (None, None, None), None
    at = as_utc(clock())
    with session_factory() as session:
        deck = session.get(Deck, prepared.deck_id)
        if deck is None:
            raise DeckNotFound(f"There is no deck {deck_id}.")
        state = deck_state(session, deck)
        _check_ready(state)
        still = {c.item_id for c in state.readiness.candidates}
        if not set(prepared.item_ids) <= still:
            raise NotReady("The terms of this deck changed.", reason="candidates_changed")
        task = store_task(
            session,
            deck_id=prepared.deck_id,
            task_type=task_type,
            output=output,
            item_ids=prepared.item_ids,
            refs=prepared.refs,
            source=source,
            reason=reason,
            provenance=provenance,
            ai_call_id=call_id,
            study_session_id=prepared.study_session_id,
            at=at,
        )
        session.commit()
        return CreationResult(task.id, source, reason)


# --- Reading -------------------------------------------------------------------------------------


def get_task(session: Session, task_id: int) -> ConsolidationTask:
    task = session.get(ConsolidationTask, task_id)
    if task is None:
        raise TaskNotFound(f"There is no consolidation task {task_id}.")
    return task


def list_tasks(
    session: Session,
    *,
    deck_id: int | None = None,
    status: TaskStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ConsolidationTask], int]:
    """Newest first."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    condition = ConsolidationTask.id.is_not(None)
    if deck_id is not None:
        condition = condition & (ConsolidationTask.deck_id == deck_id)
    if status is not None:
        condition = condition & (ConsolidationTask.status == rules.db_status(status))
    page = session.scalars(
        select(ConsolidationTask)
        .where(condition)
        .order_by(ConsolidationTask.created_at.desc(), ConsolidationTask.id.desc())
        .limit(limit)
        .offset(max(offset, 0))
    )
    total = session.scalar(select(func.count()).select_from(ConsolidationTask).where(condition))
    return list(page), total or 0


def task_item_ids(session: Session, task_id: int) -> list[int]:
    """The terms of a task in selection order."""
    return list(
        session.scalars(
            select(ConsolidationTaskItem.lexical_item_id)
            .where(ConsolidationTaskItem.consolidation_task_id == task_id)
            .order_by(ConsolidationTaskItem.id)
        )
    )


def task_attempts(session: Session, task_id: int) -> list[ProductionAttempt]:
    return list(
        session.scalars(
            select(ProductionAttempt)
            .where(ProductionAttempt.consolidation_task_id == task_id)
            .order_by(ProductionAttempt.created_at, ProductionAttempt.id)
        )
    )


# --- Status --------------------------------------------------------------------------------------


def change_status(
    session: Session, task_id: int, to: TaskStatus, *, at: datetime
) -> ConsolidationTask:
    """In the caller's transaction. Raises TaskNotFound, InvalidTransition."""
    task = get_task(session, task_id)
    source = rules.api_status(task.status)
    if not rules.can_transition(source, to):
        raise InvalidTransition(
            f"A task cannot go from {source.value} to {to.value}.",
            from_status=source.value,
            to_status=to.value,
        )
    at = as_utc(at)
    task.status = rules.db_status(to)
    task.updated_at = at
    if to is TaskStatus.COMPLETED:
        task.completed_at = at
    record_event(
        session,
        ConsolidationTaskStatusChanged(
            task_id=task.id, from_status=source.value, to_status=to.value
        ),
        occurred_at=at,
        study_session_id=(task.suggested_structure or {}).get("study_session_id"),
    )
    return task


# --- Export --------------------------------------------------------------------------------------


class _Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    en: str
    fr: str


class _ExportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    role: _Pair
    headings: dict[str, _Pair]
    labels: dict[str, _Pair]
    instructions: dict[str, list[str]]


@cache
def load_export_texts(path: Path = EXPORT_FILE) -> _ExportFile:
    with path.open(encoding="utf-8") as file:
        try:
            return _ExportFile.model_validate(yaml.safe_load(file))
        except ValidationError as exc:
            raise ValueError(f"invalid consolidation export file: {exc}") from exc


def export_markdown(session: Session, task: ConsolidationTask, lang: Literal["en", "fr"]) -> str:
    """A page to paste into a voice conversation with a tutor: role, task, structure, the terms
    with their simple definitions, and what the tutor must do. Nothing personal."""
    texts = load_export_texts()
    structure = dict(task.suggested_structure or {})
    items = {
        i.id: i
        for i in session.scalars(
            select(LexicalItem).where(LexicalItem.id.in_(task_item_ids(session, task.id)))
        )
    }
    lines = [
        f"# {structure['title'][lang]}",
        "",
        f"## {getattr(texts.headings['role'], lang)}",
        getattr(texts.role, lang),
        "",
        f"## {getattr(texts.headings['topic'], lang)}",
        structure["prompt"][lang],
        "",
        f"- {getattr(texts.labels['audience'], lang)}: {structure['audience'][lang]}",
        f"- {getattr(texts.labels['length'], lang)}: {structure['target_minutes']} "
        f"{getattr(texts.labels['minutes'], lang)}",
        "",
        f"## {getattr(texts.headings['structure'], lang)}",
    ]
    for number, section in enumerate(structure["sections"], start=1):
        lines.append(f"{number}. **{section['heading'][lang]}**: {section['guidance'][lang]}")
    lines += ["", f"## {getattr(texts.headings['terms'], lang)}"]
    for item_id in task_item_ids(session, task.id):
        item = items[item_id]
        definition = _definition(session, item)
        lines.append(f"- **{item.term}**" + (f": {definition}" if definition else ""))
    lines += ["", f"## {getattr(texts.headings['instructions'], lang)}"]
    for number, text in enumerate(texts.instructions[lang], start=1):
        lines.append(f"{number}. {text}")
    return "\n".join(lines) + "\n"


# --- Productions of a task (M7.a2) ---------------------------------------------------------------


class TaskClosed(LibraryError):
    """The task is `completed` or `dismissed`: it takes no new attempt."""

    status, code = 409, "task_closed"


def ensure_open(session: Session, task_id: int) -> ConsolidationTask:
    """The task, if it still takes attempts. Raises TaskNotFound, TaskClosed."""
    task = get_task(session, task_id)
    if task.status not in rules.OPEN_STATUSES:
        raise TaskClosed(
            "This task is closed: start a new one.",
            task_status=rules.api_status(task.status).value,
        )
    return task


def note_attempt(session: Session, task_id: int, at: datetime) -> None:
    """The first attempt on a `proposed` task makes it `accepted`, in the transaction that
    creates the attempt. Raises TaskNotFound, TaskClosed."""
    task = ensure_open(session, task_id)
    if task.status is ConsolidationTaskStatus.PROPOSED:
        change_status(session, task_id, TaskStatus.ACCEPTED, at=at)


def apply_result(session: Session, attempt_id: int, at: datetime) -> dict[str, Any] | None:
    """Apply a corrected consolidation production to the terms of its task, in the caller's
    transaction (the one that stores the correction; no commit). Per term (D-229):

    - used correctly (`used`, `used_correctly`, no error tied to the term): `learning` or
      `consolidated` becomes `active`; `active` stays; `archived` and `known` are ignored;
    - used wrongly: a FSRS Again on the productive card (`consolidation_misuse`, no
      `production_attempt_id`: the unique index of D-127 allows one review per production);
    - absent, not heard, or without a verdict: nothing.

    Writes `consolidation.attempt_checked` and returns its payload (None for a production that is
    not a task's, or already applied).
    """
    from app.services import productions  # late: productions does not import this module
    from app.services.items import mark_active
    from app.services.reviews import ReviewNotAllowed, record_review

    attempt = session.get(ProductionAttempt, attempt_id)
    if attempt is None or attempt.consolidation_task_id is None:
        return None
    already = session.scalar(
        select(EventLog.id).where(
            EventLog.event_type == EventType.CONSOLIDATION_ATTEMPT_CHECKED.value,
            EventLog.payload["production_attempt_id"].as_integer() == attempt_id,
        )
    )
    if already is not None:
        return None
    at = as_utc(at)
    tied = set(
        session.scalars(
            select(ErrorEvent.lexical_item_id).where(
                ErrorEvent.production_attempt_id == attempt_id,
                ErrorEvent.lexical_item_id.is_not(None),
            )
        )
    )
    activated: list[int] = []
    reinforced: list[int] = []
    counts = {"used": 0, "correct": 0, "misused": 0, "absent": 0}
    rows = productions.targets_of(session, attempt_id)
    for target, item in rows:
        outcome = rules.classify_target(
            used=target.used,
            used_correctly=target.used_correctly,
            has_error=item.id in tied,
        )
        if target.used:
            counts["used"] += 1
        if outcome is rules.TargetOutcome.ABSENT:
            counts["absent"] += 1
        elif outcome is rules.TargetOutcome.CORRECT:
            counts["correct"] += 1
            if item.status in (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED):
                mark_active(session, item, at)
                activated.append(item.id)
        elif outcome is rules.TargetOutcome.MISUSED:
            counts["misused"] += 1
            if item.status in (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED, ItemStatus.ACTIVE):
                card = session.scalar(
                    select(Card).where(
                        Card.lexical_item_id == item.id,
                        Card.direction == CardDirection.PRODUCTIVE,
                    )
                )
                if card is not None:
                    try:
                        record_review(
                            session,
                            card,
                            1,
                            at,
                            None,
                            "consolidation_misuse",
                            auto_rating=1,
                            study_session_id=attempt.study_session_id,
                        )
                    except ReviewNotAllowed:
                        continue
                    reinforced.append(card.id)
    summary: dict[str, Any] = {
        "task_id": attempt.consolidation_task_id,
        "production_attempt_id": attempt_id,
        "modality": attempt.modality.value,
        "targets": len(rows),
        "used": counts["used"],
        "used_correctly": counts["correct"],
        "misused": counts["misused"],
        "absent": counts["absent"],
        "activated_item_ids": activated,
        "reinforced_card_ids": reinforced,
    }
    record_event(
        session,
        ConsolidationAttemptChecked(**summary),
        occurred_at=at,
        study_session_id=attempt.study_session_id,
    )
    return summary
