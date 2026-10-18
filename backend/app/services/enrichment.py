"""Usage sheets (module A): batch enrichment through the AI gateway, reading and editing.

**One run = at most one batch** of `ENRICHMENT_BATCH_SIZE` terms:

1. choose the batch in a short read session, then close it;
2. call the gateway with no session open (D-038);
3. `ok`: in one short transaction, check each term again (still there, same spelling, no new
   current sheet since the batch was chosen) and write the sheet, its exercise templates and
   `enrichment.generated`;
4. `incomplete`, or `unavailable(all_failed)` on more than one term: the terms are tried again one
   by one in the same run, under `SPLIT_TIME_CAP_S`; a term that still fails alone gets a skeleton
   sheet (`needs_completion`, no template) that the user can complete;
5. `unavailable` for any other reason (no provider, quota, network, time budget): nothing is
   written, the terms stay pending and the reason is returned. This is the degraded mode.

A process-wide lock refuses a second run while one is going (`EnrichmentRunning`); a run from
another process (the CLI) is caught by the check of step 3.

Reading and editing work in the caller's transaction, like every service (D-023). An edited sheet
is never regenerated without the user's consent (`SheetEdited`), and old versions are kept.
"""

import json
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import Select, case, exists, func, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.enrichment import (
    ENRICHMENT_BATCH_SIZE,
    EnrichmentBatchOutput,
    EnrichmentEntry,
    batch_context,
)
from app.ai.tasks import ENRICHMENT_TOKENS_PER_TERM
from app.ai.types import AiResult, AiStatus, UnavailableReason
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import (
    Deck,
    DeckItem,
    Enrichment,
    ExerciseTemplate,
    LexicalItem,
    ReviewLog,
    Source,
)
from app.domain import exercises as ex
from app.domain.enums import ContentOrigin, EnrichmentStatus, ItemStatus
from app.domain.events import EnrichmentEdited, EnrichmentGenerated, ExerciseTemplateEdited
from app.domain.study_day import as_utc
from app.domain.usage_sheet import SCHEMA_VERSION, UsageSheet, read_sheet, skeleton_sheet
from app.services.library import ItemNotFound, LibraryError, get_deck, get_item

TASK = "enrichment"
PROMPT_LABEL = "enrichment.v1"
# Terms waiting for a sheet are taken from these statuses only (never draft, triage, known,
# archived: a term triaged as known needs no sheet).
AUTO_STATUSES = (
    ItemStatus.DISCOVERING,
    ItemStatus.QUEUED,
    ItemStatus.LEARNING,
    ItemStatus.CONSOLIDATED,
    ItemStatus.ACTIVE,
)
SPLIT_TIME_CAP_S = 150.0  # no new one-term call starts after this, the rest waits for the next run
# Cut before the text goes into the prompt (keeps a batch under `max_input_chars`).
SENTENCE_MAX = 400
DECK_FIELD_MAX = 300

SessionFactory = Callable[[], Session]


# --- Errors --------------------------------------------------------------------------------------


class EnrichmentRunning(LibraryError):
    code = "enrichment_running"


class SheetEdited(LibraryError):
    code = "sheet_edited"


class SheetChanged(LibraryError):
    code = "sheet_changed"


class SheetNotFound(LibraryError):
    status, code = 404, "sheet_not_found"


class ExerciseNotFound(LibraryError):
    status, code = 404, "exercise_not_found"


class ItemArchived(LibraryError):
    code = "item_archived"


class InvalidExercise(LibraryError):
    status, code = 422, "invalid_exercise"


# --- Sheet state ---------------------------------------------------------------------------------


class SheetState(StrEnum):
    NONE = "none"
    COMPLETE = "complete"
    NEEDS_COMPLETION = "needs_completion"
    EDITED = "edited"  # wins over the two above


def current_sheet(session: Session, item_id: int) -> Enrichment | None:
    return session.scalar(
        select(Enrichment).where(Enrichment.lexical_item_id == item_id, Enrichment.is_current)
    )


def sheet_state(enrichment: Enrichment | None) -> SheetState:
    if enrichment is None:
        return SheetState.NONE
    if enrichment.edited_by_user:
        return SheetState.EDITED
    return SheetState(enrichment.status)


def sheet_states(session: Session, item_ids: Iterable[int]) -> dict[int, SheetState]:
    """State of the current sheet of each term (terms without one are absent: `none`)."""
    ids = list(set(item_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(Enrichment.lexical_item_id, Enrichment.status, Enrichment.edited_by_user).where(
            Enrichment.lexical_item_id.in_(ids), Enrichment.is_current
        )
    )
    return {
        item_id: SheetState.EDITED if edited else SheetState(status)
        for item_id, status, edited in rows
    }


def _no_current_sheet() -> Any:
    return ~exists().where(Enrichment.lexical_item_id == LexicalItem.id, Enrichment.is_current)


def _incomplete_sheet() -> Any:
    return exists().where(
        Enrichment.lexical_item_id == LexicalItem.id,
        Enrichment.is_current,
        Enrichment.status == EnrichmentStatus.NEEDS_COMPLETION,
        ~Enrichment.edited_by_user,
    )


def _status_rank() -> Any:
    return case(
        {status: rank for rank, status in enumerate(AUTO_STATUSES)}, value=LexicalItem.status
    )


def _pending_query(deck_id: int | None, include_incomplete: bool) -> Select[tuple[LexicalItem]]:
    waiting = _no_current_sheet()
    if include_incomplete:
        waiting = waiting | _incomplete_sheet()
    stmt = select(LexicalItem).where(LexicalItem.status.in_(AUTO_STATUSES), waiting)
    if deck_id is not None:
        return (
            stmt.join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
            .where(DeckItem.deck_id == deck_id)
            .order_by(DeckItem.position, LexicalItem.id)
        )
    return stmt.order_by(_status_rank(), LexicalItem.created_at, LexicalItem.id)


def list_pending(
    session: Session, *, deck_id: int | None = None, include_incomplete: bool = False
) -> list[LexicalItem]:
    """Terms waiting for a sheet, in the order runs take them (deck order when a deck is given;
    else discovering first, then queued, then the others, oldest first)."""
    if deck_id is not None:
        get_deck(session, deck_id)
    return list(session.scalars(_pending_query(deck_id, include_incomplete)))


# --- Batch selection -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    item_id: int
    term: str
    item_type: str
    part_of_speech: str | None
    sentence: str | None
    deck_name: str | None
    deck_domain: str | None
    deck_context: str | None
    base_id: int | None  # current sheet when the batch was chosen (None: no sheet)
    base_edited: bool = False


def _cut(text: str | None, limit: int) -> str | None:
    if not text or not text.strip():
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _candidate(session: Session, item: LexicalItem) -> Candidate:
    """Context of a term for the prompt: its first deck link (oldest) and that deck's sentence,
    else the term's own sentence."""
    first = session.execute(
        select(DeckItem, Deck, Source)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .outerjoin(Source, Source.id == Deck.source_id)
        .where(DeckItem.lexical_item_id == item.id)
        .order_by(DeckItem.added_at, DeckItem.id)
        .limit(1)
    ).first()
    link, deck, source = first if first is not None else (None, None, None)
    context = None
    if deck is not None:
        context = deck.description or (source.context if source is not None else None)
    current = current_sheet(session, item.id)
    return Candidate(
        item_id=item.id,
        term=item.term,
        item_type=str(item.item_type),
        part_of_speech=item.part_of_speech,
        sentence=_cut(
            (link.context_sentence if link else None) or item.origin_sentence, SENTENCE_MAX
        ),
        deck_name=_cut(deck.name if deck else None, DECK_FIELD_MAX),
        deck_domain=_cut(deck.domain if deck else None, DECK_FIELD_MAX),
        deck_context=_cut(context, DECK_FIELD_MAX),
        base_id=current.id if current is not None else None,
        base_edited=bool(current is not None and current.edited_by_user),
    )


def explicit_waiting(session: Session, item_ids: Sequence[int]) -> list[LexicalItem]:
    """Terms asked for by id: any status but archived; terms that already have a complete or
    edited sheet are left out (regenerating one is `regenerate`, with consent when edited)."""
    ids = list(dict.fromkeys(item_ids))
    items = {i.id: i for i in session.scalars(select(LexicalItem).where(LexicalItem.id.in_(ids)))}
    missing = [item_id for item_id in ids if item_id not in items]
    if missing:
        raise ItemNotFound(f"There is no term {missing[0]}.", item_ids=missing)
    archived = [item_id for item_id in ids if items[item_id].status == ItemStatus.ARCHIVED]
    if archived:
        raise ItemArchived("Archived terms get no sheet; nothing was run.", item_ids=archived)
    states = sheet_states(session, ids)
    waiting = (SheetState.NONE, SheetState.NEEDS_COMPLETION)
    return [items[i] for i in ids if states.get(i, SheetState.NONE) in waiting]


def _choose(
    session: Session,
    *,
    deck_id: int | None,
    item_ids: Sequence[int] | None,
    include_incomplete: bool,
    regenerate_id: int | None,
) -> list[Candidate]:
    if regenerate_id is not None:
        item = get_item(session, regenerate_id)
        if item.status == ItemStatus.ARCHIVED:
            raise ItemArchived("Archived terms get no sheet.", item_ids=[item.id])
        return [_candidate(session, item)]
    if item_ids:
        waiting = explicit_waiting(session, item_ids)
    else:
        waiting = list_pending(session, deck_id=deck_id, include_incomplete=include_incomplete)
    return [_candidate(session, item) for item in waiting[:ENRICHMENT_BATCH_SIZE]]


def _prompt_terms(batch: Sequence[Candidate]) -> str:
    lines = []
    for ref, c in enumerate(batch):
        line = {
            "ref": ref,
            "term": c.term,
            "type": c.item_type,
            "sentence": c.sentence or "",
            "deck": {"name": c.deck_name, "domain": c.deck_domain, "context": c.deck_context},
        }
        lines.append(json.dumps(line, ensure_ascii=False))
    return "\n".join(lines)


def _call(gateway: Gateway, batch: Sequence[Candidate]) -> AiResult[EnrichmentBatchOutput]:
    return gateway.generate_json(
        TASK,
        {"terms": _prompt_terms(batch)},
        EnrichmentBatchOutput,
        validation_context=batch_context({ref: c.term for ref, c in enumerate(batch)}),
        max_output_tokens=ENRICHMENT_TOKENS_PER_TERM * len(batch),
    )


# --- Writing -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    provider: str | None
    model: str | None
    prompt_version: str | None


def templates_of(entry: EnrichmentEntry) -> list[tuple[str, dict[str, Any]]]:
    """Exercise templates of one generated entry: (type, validated content)."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for gap in entry.gap_fills:
        rows.append((ex.GAP_FILL, gap.model_dump()))
    typed = ex.typed_recall_content(
        entry.term, entry.translation_fr, entry.definition_simple, entry.answer_forms()
    )
    if typed is not None:
        rows.append((ex.TYPED_RECALL, typed))
    for recognition in entry.recognitions:
        rows.append((ex.RECOGNITION, recognition.model_dump()))
    rows.append((ex.LISTENING, entry.recognitions[0].model_dump()))
    for production in entry.productions:
        rows.append((ex.SENTENCE_PRODUCTION, production.model_dump()))
    rows.append((ex.SPOKEN_ANSWER, entry.spoken.model_dump()))
    return [(kind, ex.validate_content(kind, content)) for kind, content in rows]


def _replaceable(
    session: Session, item_id: int, types: Iterable[str] | None = None
) -> list[ExerciseTemplate]:
    """Templates a regeneration may delete: not edited by the user and never used in a review."""
    used = exists().where(ReviewLog.exercise_template_id == ExerciseTemplate.id)
    stmt = select(ExerciseTemplate).where(
        ExerciseTemplate.lexical_item_id == item_id,
        ~ExerciseTemplate.edited_by_user,
        ExerciseTemplate.origin != ContentOrigin.DEMO,
        ~used,
    )
    if types is not None:
        stmt = stmt.where(ExerciseTemplate.exercise_type.in_(list(types)))
    return list(session.scalars(stmt))


def _replace_templates(
    session: Session,
    item_id: int,
    rows: Sequence[tuple[str, dict[str, Any]]],
    *,
    origin: ContentOrigin,
    prompt_version: str | None,
    at: datetime,
    only_types: Iterable[str] | None = None,
) -> None:
    for old in _replaceable(session, item_id, only_types):
        session.delete(old)
    session.flush()
    _insert_templates(session, item_id, rows, origin=origin, prompt_version=prompt_version, at=at)


def _insert_templates(
    session: Session,
    item_id: int,
    rows: Sequence[tuple[str, dict[str, Any]]],
    *,
    origin: ContentOrigin,
    prompt_version: str | None,
    at: datetime,
) -> None:
    for kind, content in rows:
        session.add(
            ExerciseTemplate(
                lexical_item_id=item_id,
                exercise_type=kind,
                direction=ex.EXERCISE_TYPES[kind][0],
                content=content,
                origin=origin,
                prompt_version=prompt_version,
                edited_by_user=False,
                created_at=at,
                updated_at=at,
            )
        )
    session.flush()


def _new_version(
    session: Session,
    item_id: int,
    content: dict[str, Any],
    *,
    status: EnrichmentStatus,
    provenance: Provenance,
    edited: bool,
    at: datetime,
) -> tuple[Enrichment, int | None]:
    """A new current sheet; the previous current one stays in the history."""
    previous = current_sheet(session, item_id)
    if previous is not None:
        previous.is_current = False
        session.flush()  # the partial unique index allows one current sheet per term
    sheet = Enrichment(
        lexical_item_id=item_id,
        content=content,
        schema_version=SCHEMA_VERSION,
        status=status,
        provider=provenance.provider,
        model=provenance.model,
        prompt_version=provenance.prompt_version,
        edited_by_user=edited,
        edited_at=at if edited else None,
        is_current=True,
        created_at=at,
        updated_at=at,
    )
    session.add(sheet)
    session.flush()
    return sheet, previous.id if previous is not None else None


def _still_valid(session: Session, candidate: Candidate) -> bool:
    """The term was not deleted, renamed, or given another current sheet during the AI call."""
    item = session.get(LexicalItem, candidate.item_id)
    if item is None or item.term != candidate.term or item.status == ItemStatus.ARCHIVED:
        return False
    current = current_sheet(session, item.id)
    return (current.id if current is not None else None) == candidate.base_id


@dataclass
class _Tally:
    generated: list[int] = field(default_factory=list)
    needs_completion: list[int] = field(default_factory=list)
    superseded: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)  # failed, existing sheet kept


def _write(
    session_factory: SessionFactory,
    outcomes: Sequence[tuple[Candidate, EnrichmentEntry | None]],
    provenance: Provenance,
    at: datetime,
    tally: _Tally,
) -> None:
    """One short transaction: each candidate gets its sheet (an entry) or a skeleton (None)."""
    with session_factory() as session:
        for candidate, entry in outcomes:
            if not _still_valid(session, candidate):
                tally.superseded.append(candidate.item_id)
                continue
            if entry is None:
                if candidate.base_id is not None and not _is_incomplete(session, candidate.base_id):
                    # A regeneration that failed never replaces a usable sheet by a skeleton.
                    tally.failed.append(candidate.item_id)
                    continue
                content = skeleton_sheet(candidate.part_of_speech)
                status = EnrichmentStatus.NEEDS_COMPLETION
            else:
                content = entry.to_stored().model_dump(mode="json")
                status = EnrichmentStatus.COMPLETE
            sheet, replaced = _new_version(
                session,
                candidate.item_id,
                content,
                status=status,
                provenance=provenance,
                edited=False,
                at=at,
            )
            if entry is not None:
                _replace_templates(
                    session,
                    candidate.item_id,
                    templates_of(entry),
                    origin=ContentOrigin.AI,
                    prompt_version=provenance.prompt_version,
                    at=at,
                )
                tally.generated.append(candidate.item_id)
            else:
                tally.needs_completion.append(candidate.item_id)
            record_event(
                session,
                EnrichmentGenerated(
                    enrichment_id=sheet.id,
                    lexical_item_id=candidate.item_id,
                    status=status,
                    provider=provenance.provider,
                    model=provenance.model,
                    prompt_version=provenance.prompt_version,
                    replaced_enrichment_id=replaced,
                ),
                occurred_at=at,
            )
        session.commit()


def _is_incomplete(session: Session, enrichment_id: int) -> bool:
    sheet = session.get(Enrichment, enrichment_id)
    return bool(
        sheet is not None
        and sheet.status == EnrichmentStatus.NEEDS_COMPLETION
        and not sheet.edited_by_user
    )


def _provenance(result: AiResult[Any]) -> Provenance:
    return Provenance(result.provider, result.model, result.prompt_version or PROMPT_LABEL)


# --- Runs ----------------------------------------------------------------------------------------


class RunReport(BaseModel):
    status: Literal["ok", "partial", "unavailable"]
    reason: UnavailableReason | None = None
    generated: int = 0
    needs_completion: int = 0
    superseded: int = 0  # changed during the call: the result was dropped
    failed: int = 0  # regeneration failed: the existing sheet is kept
    remaining: int = 0  # still waiting in the same scope after this run
    item_ids: list[int] = []  # the terms of this run's batch


_RUN_LOCK = threading.Lock()


def run_enrichment(
    session_factory: SessionFactory,
    gateway: Gateway,
    *,
    deck_id: int | None = None,
    item_ids: Sequence[int] | None = None,
    include_incomplete: bool = False,
    regenerate_id: int | None = None,
    confirm_overwrite: bool = False,
    clock: Callable[[], datetime] = utcnow,
) -> RunReport:
    """Enrich one batch (see the module docstring). Raises EnrichmentRunning, ItemNotFound,
    DeckNotFound, ItemArchived, SheetEdited (regeneration of an edited sheet without consent)."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise EnrichmentRunning("Usage sheets are already being generated; try again in a moment.")
    try:
        return _run(
            session_factory,
            gateway,
            deck_id=deck_id,
            item_ids=item_ids,
            include_incomplete=include_incomplete,
            regenerate_id=regenerate_id,
            confirm_overwrite=confirm_overwrite,
            clock=clock,
        )
    finally:
        _RUN_LOCK.release()


def _run(
    session_factory: SessionFactory,
    gateway: Gateway,
    *,
    deck_id: int | None,
    item_ids: Sequence[int] | None,
    include_incomplete: bool,
    regenerate_id: int | None,
    confirm_overwrite: bool,
    clock: Callable[[], datetime],
) -> RunReport:
    started = clock()
    with session_factory() as session:
        batch = _choose(
            session,
            deck_id=deck_id,
            item_ids=item_ids,
            include_incomplete=include_incomplete,
            regenerate_id=regenerate_id,
        )
        session.rollback()  # nothing stays open during the AI call
    if regenerate_id is not None:
        candidate = batch[0]
        if candidate.base_edited and not confirm_overwrite:
            raise SheetEdited(
                "This sheet was edited by you; confirm to replace it (the old one is kept)."
            )
    if not batch:
        return RunReport(status="ok")

    tally = _Tally()
    reason: UnavailableReason | None = None
    result = _call(gateway, batch)
    split = result.status is AiStatus.INCOMPLETE or (
        result.status is AiStatus.UNAVAILABLE and result.reason is UnavailableReason.ALL_FAILED
    )
    if result.ok and result.data is not None:
        entries = {entry.ref: entry for entry in result.data.sheets}
        _write(
            session_factory,
            [(c, entries[ref]) for ref, c in enumerate(batch)],
            _provenance(result),
            clock(),
            tally,
        )
    elif split and len(batch) == 1:
        _write(session_factory, [(batch[0], None)], _provenance(result), clock(), tally)
    elif split:
        for candidate in batch:
            if (clock() - started).total_seconds() >= SPLIT_TIME_CAP_S:
                break  # the remaining terms wait for the next run
            single = _call(gateway, [candidate])
            if single.ok and single.data is not None:
                outcome = [(candidate, single.data.sheets[0])]
            elif single.status is AiStatus.INCOMPLETE or (
                single.reason is UnavailableReason.ALL_FAILED
            ):
                outcome = [(candidate, None)]
            else:
                reason = single.reason
                break
            _write(session_factory, outcome, _provenance(single), clock(), tally)
    else:
        reason = result.reason

    with session_factory() as session:
        if regenerate_id is not None:
            remaining = 0
        elif item_ids:
            remaining = len(explicit_waiting(session, item_ids))
        else:
            remaining = len(
                list_pending(session, deck_id=deck_id, include_incomplete=include_incomplete)
            )
        session.rollback()
    written = len(tally.generated) + len(tally.needs_completion)
    settled = written + len(tally.superseded)
    status: Literal["ok", "partial", "unavailable"]
    if reason is not None and written == 0:
        status = "unavailable"
    elif tally.needs_completion or tally.failed or reason is not None or settled < len(batch):
        status = "partial"
    else:
        status = "ok"
    return RunReport(
        status=status,
        reason=reason,
        generated=len(tally.generated),
        needs_completion=len(tally.needs_completion),
        superseded=len(tally.superseded),
        failed=len(tally.failed),
        remaining=remaining,
        item_ids=[c.item_id for c in batch],
    )


# --- Reading and editing (caller's transaction) --------------------------------------------------


class SheetVersion(BaseModel):
    enrichment_id: int
    version: int  # 1 = oldest
    is_current: bool
    status: EnrichmentStatus
    sheet_status: SheetState
    edited_by_user: bool
    edited_at: datetime | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    schema_version: int
    created_at: datetime
    content: dict[str, Any]


def _versions(session: Session, item_id: int) -> list[Enrichment]:
    return list(
        session.scalars(
            select(Enrichment)
            .where(Enrichment.lexical_item_id == item_id)
            .order_by(Enrichment.id)  # insertion order: clocks may disagree
        )
    )


def _view(sheet: Enrichment, version: int) -> SheetVersion:
    return SheetVersion(
        enrichment_id=sheet.id,
        version=version,
        is_current=sheet.is_current,
        status=EnrichmentStatus(sheet.status),
        sheet_status=sheet_state(sheet),
        edited_by_user=sheet.edited_by_user,
        edited_at=sheet.edited_at,
        provider=sheet.provider,
        model=sheet.model,
        prompt_version=sheet.prompt_version,
        schema_version=sheet.schema_version,
        created_at=sheet.created_at,
        content=read_sheet(sheet.content).model_dump(mode="json"),
    )


def list_versions(session: Session, item_id: int) -> list[SheetVersion]:
    """Every version of a term's sheet, newest first."""
    get_item(session, item_id)
    versions = [_view(sheet, n) for n, sheet in enumerate(_versions(session, item_id), start=1)]
    return list(reversed(versions))


def get_sheet(session: Session, item_id: int) -> SheetVersion:
    """The current sheet. Raises ItemNotFound, SheetNotFound."""
    get_item(session, item_id)
    for n, sheet in enumerate(_versions(session, item_id), start=1):
        if sheet.is_current:
            return _view(sheet, n)
    raise SheetNotFound("This term has no usage sheet yet.")


def save_sheet(
    session: Session,
    item_id: int,
    sheet: UsageSheet,
    at: datetime,
    *,
    base_enrichment_id: int | None = None,
    provenance: Provenance | None = None,
) -> SheetVersion:
    """Save the user's sheet as a new current version (edit, or manual entry when the term has
    none). Provenance is copied from the edited version unless `provenance` is given (the demo's
    hand-typed sheets, provider "demo"). Raises ItemNotFound, SheetChanged."""
    at = as_utc(at)
    item = get_item(session, item_id)
    base = current_sheet(session, item.id)
    if base_enrichment_id is not None and (base is None or base.id != base_enrichment_id):
        raise SheetChanged(
            "The sheet changed since you opened it; reload it before saving.",
            current_enrichment_id=base.id if base is not None else None,
        )
    if provenance is None:
        provenance = (
            Provenance(base.provider, base.model, base.prompt_version)
            if base is not None
            else Provenance(None, None, None)
        )
    new, _ = _new_version(
        session,
        item.id,
        sheet.model_dump(mode="json"),
        status=EnrichmentStatus.COMPLETE,
        provenance=provenance,
        edited=True,
        at=at,
    )
    _refresh_typed_recall(session, item, sheet, at)
    record_event(
        session,
        EnrichmentEdited(
            enrichment_id=new.id,
            lexical_item_id=item.id,
            base_enrichment_id=base.id if base is not None else None,
        ),
        occurred_at=at,
    )
    session.flush()
    return get_sheet(session, item.id)


def store_generated_sheet(
    session: Session, item_id: int, sheet: UsageSheet, at: datetime, provenance: Provenance
) -> Enrichment:
    """A first sheet made by the app itself (provider "error" for a card made from an error),
    saved as the current version. Unlike `save_sheet` it derives no typed-recall template: the
    caller owns the term's exercises. Raises ItemNotFound."""
    at = as_utc(at)
    get_item(session, item_id)
    new, _ = _new_version(
        session,
        item_id,
        sheet.model_dump(mode="json"),
        status=EnrichmentStatus.COMPLETE,
        provenance=provenance,
        edited=False,
        at=at,
    )
    return new


def add_templates(
    session: Session,
    item_id: int,
    rows: Sequence[tuple[str, dict[str, Any]]],
    at: datetime,
    *,
    origin: ContentOrigin,
    prompt_version: str | None = None,
) -> None:
    """Add exercise templates to a term (content validated for its type); nothing is deleted.
    Used by the demo (origin `demo`). Raises ValueError / ValidationError on invalid content."""
    at = as_utc(at)
    get_item(session, item_id)
    validated = [(kind, ex.validate_content(kind, content)) for kind, content in rows]
    _insert_templates(
        session, item_id, validated, origin=origin, prompt_version=prompt_version, at=at
    )


def _refresh_typed_recall(
    session: Session, item: LexicalItem, sheet: UsageSheet, at: datetime
) -> None:
    """French / definition -> English recall follows the user's sheet (D-082)."""
    forms = []
    for template in session.scalars(
        select(ExerciseTemplate).where(
            ExerciseTemplate.lexical_item_id == item.id,
            ExerciseTemplate.exercise_type == ex.GAP_FILL,
        )
    ):
        forms += [template.content.get("answer", ""), *template.content.get("accepted", [])]
    content = ex.typed_recall_content(
        item.term, sheet.translation_fr, sheet.definition_simple, [f for f in forms if f]
    )
    existing = session.scalar(
        select(func.count())
        .select_from(ExerciseTemplate)
        .where(
            ExerciseTemplate.lexical_item_id == item.id,
            ExerciseTemplate.exercise_type == ex.TYPED_RECALL,
        )
    )
    # An edited (or already reviewed) recall template stays, and no second one is added.
    kept = existing != len(_replaceable(session, item.id, [ex.TYPED_RECALL]))
    rows = [(ex.TYPED_RECALL, content)] if content is not None and not kept else []
    _replace_templates(
        session,
        item.id,
        rows,
        origin=ContentOrigin.USER,
        prompt_version=None,
        at=at,
        only_types=[ex.TYPED_RECALL],
    )


class ExerciseOut(BaseModel):
    id: int
    lexical_item_id: int
    exercise_type: str
    direction: str | None
    origin: ContentOrigin
    prompt_version: str | None
    edited_by_user: bool
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime


def _exercise_out(template: ExerciseTemplate) -> ExerciseOut:
    return ExerciseOut(
        id=template.id,
        lexical_item_id=template.lexical_item_id,
        exercise_type=template.exercise_type,
        direction=str(template.direction) if template.direction is not None else None,
        origin=ContentOrigin(template.origin),
        prompt_version=template.prompt_version,
        edited_by_user=template.edited_by_user,
        content=dict(template.content),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def list_exercises(session: Session, item_id: int) -> list[ExerciseOut]:
    get_item(session, item_id)
    templates = session.scalars(
        select(ExerciseTemplate)
        .where(ExerciseTemplate.lexical_item_id == item_id)
        .order_by(ExerciseTemplate.id)
    )
    return [_exercise_out(t) for t in templates]


def update_exercise(
    session: Session, exercise_id: int, content: dict[str, Any], at: datetime
) -> ExerciseOut:
    """Replace a template's content (validated for its type); it is then never regenerated.
    Raises ExerciseNotFound, InvalidExercise."""
    at = as_utc(at)
    template = session.get(ExerciseTemplate, exercise_id)
    if template is None:
        raise ExerciseNotFound(f"There is no exercise {exercise_id}.")
    try:
        validated = ex.validate_content(template.exercise_type, content)
    except ValidationError as exc:
        errors = [
            {"loc": [str(part) for part in error["loc"]], "message": str(error["msg"])}
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise InvalidExercise("This exercise content is invalid.", errors=errors) from exc
    except ValueError as exc:
        raise InvalidExercise(str(exc), errors=[]) from exc
    template.content = validated
    template.edited_by_user = True
    template.updated_at = at
    record_event(
        session,
        ExerciseTemplateEdited(
            exercise_template_id=template.id,
            lexical_item_id=template.lexical_item_id,
            exercise_type=template.exercise_type,
        ),
        occurred_at=at,
    )
    session.flush()
    return _exercise_out(template)
