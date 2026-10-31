"""Library endpoints (module A, M3.a): import, terms, decks, triage, duplicates.

Routes stay thin: they validate the shape, call one service in one transaction and commit. User
errors raised by the services (`LibraryError`, `InvalidItemTransition`) become the D-063 format
in `app/api/errors.py`. The Markdown file is read by the browser and sent as JSON text (D-061: no
multipart). Writes are allowed on the demo database (a throwaway sandbox).
"""

from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.base import utcnow
from app.db.engine import get_session
from app.db.models import Deck, DeckItem, LexicalItem, Source
from app.db.settings_store import get_setting
from app.domain.enums import DeckKind, DeckStatus, ItemStatus, ItemType
from app.domain.events import TriageDecision
from app.domain.item_status import InvalidItemTransition, TransitionKind, unarchive_target
from app.domain.markdown_import import MAX_BODY_LINES, ImportHeader
from app.domain.planner import DeadlinePace, PlanWarning, SessionPlan
from app.domain.study_day import study_day_of
from app.domain.tabular_import import ImportFormat
from app.services import decks as deck_service
from app.services import duplicates, enrichment, importing, library, triage
from app.services.items import transition_item, unarchive_item
from app.services.planning import plan_today

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
Name = Annotated[str, Field(min_length=1, max_length=300)]
Text = Annotated[str, Field(max_length=5000)]
# The parser limits a file to 256 KB; a larger JSON string is refused before it reaches it.
MAX_TEXT_CHARS = 300_000


def _study_today(session: Session, now: datetime) -> date:
    tz = ZoneInfo(get_setting(session, "timezone"))
    return study_day_of(now, tz, get_setting(session, "day_start_hour"))


# --- Shapes --------------------------------------------------------------------------------------


class ItemOut(BaseModel):
    id: int
    term: str
    normalized_form: str
    lemma: str | None
    item_type: ItemType
    part_of_speech: str | None
    origin_sentence: str | None
    notes: str | None
    status: ItemStatus
    status_changed_at: datetime
    discovered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    decks: list[library.DeckRef]
    sheet_status: enrichment.SheetState  # current usage sheet (M3.b, additive)


class DeckLinkOut(BaseModel):
    deck_id: int
    deck_name: str
    position: int
    context_sentence: str | None
    added_at: datetime


class ItemDetail(ItemOut):
    deck_links: list[DeckLinkOut]
    has_history: bool  # true: delete is refused, archive instead
    duplicates: list[library.DuplicateCandidate]


class ItemPage(BaseModel):
    total: int
    items: list[ItemOut]


class SourceOut(BaseModel):
    id: int
    title: str


class DeckOut(BaseModel):
    id: int
    name: str
    description: str | None
    domain: str | None
    kind: DeckKind
    status: DeckStatus
    deadline: date | None
    priority: int
    queue_position: int | None
    source: SourceOut | None
    created_at: datetime
    updated_at: datetime
    item_count: int
    items_by_status: dict[str, int]
    # From today's plan (M4): the deadline pace and the plan warnings about this deck.
    pace: DeadlinePace | None
    warnings: list[PlanWarning]


def items_out(session: Session, items: list[LexicalItem]) -> list[ItemOut]:
    decks = library.decks_of(session, (item.id for item in items))
    sheets = enrichment.sheet_states(session, (item.id for item in items))
    return [
        ItemOut.model_validate(
            {
                **_columns(item),
                "decks": decks.get(item.id, []),
                "sheet_status": sheets.get(item.id, enrichment.SheetState.NONE),
            }
        )
        for item in items
    ]


def _columns(item: LexicalItem) -> dict[str, object]:
    computed = ("decks", "sheet_status")
    return {name: getattr(item, name) for name in ItemOut.model_fields if name not in computed}


def _item_detail(
    session: Session, item: LexicalItem, found: list[library.DuplicateCandidate] | None = None
) -> ItemDetail:
    links = session.execute(
        select(DeckItem, Deck.name)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(DeckItem.lexical_item_id == item.id)
        .order_by(Deck.id)
    ).all()
    base = items_out(session, [item])[0]
    return ItemDetail(
        **base.model_dump(),
        deck_links=[
            DeckLinkOut(
                deck_id=link.deck_id,
                deck_name=name,
                position=link.position,
                context_sentence=link.context_sentence,
                added_at=link.added_at,
            )
            for link, name in links
        ],
        has_history=library.item_has_history(session, item.id),
        duplicates=(
            found
            if found is not None
            else library.find_duplicates(session, item.term, exclude_id=item.id)
        ),
    )


def _deck_warnings(plan: SessionPlan, deck_id: int) -> list[PlanWarning]:
    return [
        warning
        for warning in plan.warnings
        if warning.params.get("deck_id") == deck_id
        or deck_id in (warning.params.get("deck_ids") or [])
    ]


def decks_out(session: Session, decks: list[Deck], now: datetime) -> list[DeckOut]:
    """Decks with their counts, and the pace and warnings of today's plan (read-only)."""
    plan = plan_today(session, now)
    paces = {pace.deck_id: pace for pace in plan.deadline_paces}
    counts = library.deck_counts(session, (deck.id for deck in decks))
    source_ids = {deck.source_id for deck in decks if deck.source_id is not None}
    sources = {
        source.id: SourceOut(id=source.id, title=source.title)
        for source in session.scalars(select(Source).where(Source.id.in_(source_ids)))
    }
    return [
        DeckOut(
            id=deck.id,
            name=deck.name,
            description=deck.description,
            domain=deck.domain,
            kind=DeckKind(deck.kind),
            status=DeckStatus(deck.status),
            deadline=deck.deadline,
            priority=deck.priority,
            queue_position=deck.queue_position,
            source=sources.get(deck.source_id) if deck.source_id is not None else None,
            created_at=deck.created_at,
            updated_at=deck.updated_at,
            item_count=counts[deck.id].total,
            items_by_status=counts[deck.id].by_status,
            pace=paces.get(deck.id),
            warnings=_deck_warnings(plan, deck.id),
        )
        for deck in decks
    ]


# --- Import --------------------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=MAX_TEXT_CHARS)
    deck_id: int | None = None  # target deck, to flag terms it already holds
    format: ImportFormat = "markdown"  # "csv" and "tsv": column 1 term, column 2 sentence


class CommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: ImportHeader = ImportHeader()
    rows: list[importing.CommitRow] = Field(max_length=MAX_BODY_LINES)
    target: importing.ImportTarget = importing.ImportTarget()
    intake: importing.Intake = "triage"


@router.post("/import/preview", tags=["import"])
def import_preview(body: PreviewRequest, session: SessionDep) -> importing.ImportPreview:
    return importing.preview(
        session, body.text, _study_today(session, utcnow()), deck_id=body.deck_id, fmt=body.format
    )


@router.post("/import/commit", tags=["import"])
def import_commit(body: CommitRequest, session: SessionDep) -> importing.ImportSummary:
    summary = importing.commit(
        session,
        header=body.header,
        rows=body.rows,
        target=body.target,
        intake=body.intake,
        at=utcnow(),
    )
    session.commit()
    return summary


# --- Terms ---------------------------------------------------------------------------------------


@router.get("/items", tags=["items"])
def list_items(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=300)] = None,
    deck_id: int | None = None,
    domain: str | None = None,
    source_id: int | None = None,
    item_type: ItemType | None = None,
    status: Annotated[list[ItemStatus] | None, Query()] = None,
    include_archived: bool = False,
    sheet: library.SheetFilter | None = None,
    sort: library.ItemSort = "created_at",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPage:
    query = library.ItemQuery(
        q=q,
        deck_id=deck_id,
        domain=domain,
        source_id=source_id,
        item_type=item_type,
        statuses=tuple(status or ()),
        include_archived=include_archived,
        sheet=sheet,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    total, items = library.list_items(session, query)
    return ItemPage(total=total, items=items_out(session, items))


class QuickAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(max_length=2000)
    sentence: Text | None = None
    deck_id: int | None = None
    item_type: ItemType | None = None
    on_duplicate: Literal["attach", "new"] | None = None
    attach_to: int | None = None


class QuickAddOut(BaseModel):
    item: ItemOut
    deck_id: int
    attached: bool
    duplicates: list[library.DuplicateCandidate]


@router.post("/items", status_code=201, tags=["items"])
def quick_add(body: QuickAddRequest, session: SessionDep) -> QuickAddOut:
    result = library.quick_add(
        session,
        term=body.term,
        sentence=body.sentence,
        deck_id=body.deck_id,
        item_type=body.item_type,
        on_duplicate=body.on_duplicate,
        attach_to=body.attach_to,
        at=utcnow(),
    )
    session.commit()
    return QuickAddOut(
        item=items_out(session, [result.item])[0],
        deck_id=result.deck.id,
        attached=result.attached,
        duplicates=result.duplicates,
    )


@router.get("/items/{item_id}", tags=["items"])
def get_item(item_id: int, session: SessionDep) -> ItemDetail:
    return _item_detail(session, library.get_item(session, item_id))


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str | None = Field(default=None, max_length=2000)
    origin_sentence: Text | None = None
    item_type: ItemType | None = None
    part_of_speech: Annotated[str, Field(max_length=50)] | None = None
    notes: Text | None = None


@router.patch("/items/{item_id}", tags=["items"])
def update_item(item_id: int, body: ItemPatch, session: SessionDep) -> ItemDetail:
    item = library.get_item(session, item_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("term", "item_type"):
        if required in changes and changes[required] is None:
            raise library.InvalidTerm(f"`{required}` cannot be empty.")
    found = library.update_item(session, item, changes, utcnow())
    session.commit()
    return _item_detail(session, item, found)


@router.delete("/items/{item_id}", status_code=204, tags=["items"])
def delete_item(item_id: int, session: SessionDep) -> Response:
    library.delete_item(session, library.get_item(session, item_id), utcnow())
    session.commit()
    return Response(status_code=204)


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: ItemStatus


@router.post("/items/{item_id}/status", tags=["items"])
def change_status(item_id: int, body: StatusRequest, session: SessionDep) -> ItemOut:
    """Manual transitions of D-025 (triage, queue, known, archive...) and unarchive."""
    item = library.get_item(session, item_id)
    now = utcnow()
    if item.status == ItemStatus.ARCHIVED:
        target = unarchive_target(library.has_cards(session, item.id))
        if body.to != target:
            raise InvalidItemTransition(item.id, item.status, body.to, TransitionKind.UNARCHIVE)
        unarchive_item(session, item, now)
    else:
        transition_item(session, item, body.to, now)
    session.commit()
    return items_out(session, [item])[0]


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    into: int


@router.post("/items/{item_id}/merge", tags=["items"])
def merge_item(item_id: int, body: MergeRequest, session: SessionDep) -> duplicates.MergeResult:
    result = duplicates.merge_items(session, item_id, body.into, utcnow())
    session.commit()
    return result


# --- Decks ---------------------------------------------------------------------------------------


@router.get("/decks", tags=["decks"])
def list_decks(session: SessionDep, now: NowDep) -> list[DeckOut]:
    return decks_out(session, library.list_decks(session), now)


class DeckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Text | None = None
    domain: Annotated[str, Field(max_length=200)] | None = None
    deadline: date | None = None
    source_id: int | None = None


@router.post("/decks", status_code=201, tags=["decks"])
def create_deck(body: DeckCreate, session: SessionDep, now: NowDep) -> DeckOut:
    if body.source_id is not None and session.get(Source, body.source_id) is None:
        raise library.SourceNotFound(f"There is no source {body.source_id}.")
    deck = library.create_deck(
        session,
        name=body.name.strip(),
        description=body.description,
        domain=body.domain,
        deadline=body.deadline,
        source_id=body.source_id,
        at=now,
    )
    session.commit()
    return decks_out(session, [deck], now)[0]


@router.get("/decks/{deck_id}", tags=["decks"])
def get_deck(deck_id: int, session: SessionDep, now: NowDep) -> DeckOut:
    return decks_out(session, [library.get_deck(session, deck_id)], now)[0]


class DeckPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Text | None = None
    domain: Annotated[str, Field(max_length=200)] | None = None
    deadline: date | None = None
    priority: Annotated[int, Field(ge=-1000, le=1000)] | None = None


@router.patch("/decks/{deck_id}", tags=["decks"])
def update_deck(deck_id: int, body: DeckPatch, session: SessionDep, now: NowDep) -> DeckOut:
    deck = library.get_deck(session, deck_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "priority"):
        if required in changes and changes[required] is None:
            raise library.InvalidTerm(f"`{required}` cannot be empty.")
    library.update_deck(session, deck, changes, now)
    session.commit()
    return decks_out(session, [deck], now)[0]


class DeckStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: DeckStatus


@router.post("/decks/{deck_id}/status", tags=["decks"])
def change_deck_status(
    deck_id: int, body: DeckStatusRequest, session: SessionDep, now: NowDep
) -> DeckOut:
    """Pause, resume, mark done or reopen a deck (D-026). Reviews of its cards never stop."""
    deck = library.get_deck(session, deck_id)
    deck_service.change_deck_status(session, deck, body.to, now)
    session.commit()
    return decks_out(session, [deck], now)[0]


class QueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck_ids: list[int] = Field(max_length=1000)


class InvalidQueue(library.LibraryError):
    status, code = 422, "invalid_queue"


@router.put("/decks/queue", tags=["decks"])
def reorder_queue(body: QueueRequest, session: SessionDep, now: NowDep) -> list[DeckOut]:
    """New manual order of the queue: every deck that is not done, exactly once (D-027)."""
    try:
        deck_service.reorder_queue(session, body.deck_ids, now)
    except ValueError as exc:
        raise InvalidQueue(str(exc)) from exc
    session.commit()
    return decks_out(session, library.list_decks(session), now)


class DeckDeleted(BaseModel):
    deck_id: int
    deleted_item_ids: list[int]


@router.delete("/decks/{deck_id}", tags=["decks"])
def delete_deck(deck_id: int, session: SessionDep) -> DeckDeleted:
    deleted = library.delete_deck(session, library.get_deck(session, deck_id), utcnow())
    session.commit()
    return DeckDeleted(deck_id=deck_id, deleted_item_ids=deleted)


# --- Triage and duplicates -----------------------------------------------------------------------


@router.get("/triage", tags=["triage"])
def list_triage(session: SessionDep, deck_id: int | None = None) -> list[triage.TriageEntry]:
    return triage.list_triage(session, deck_id)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    decision: TriageDecision


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[Decision] = Field(min_length=1, max_length=MAX_BODY_LINES)


@router.post("/triage", tags=["triage"])
def apply_triage(body: TriageRequest, session: SessionDep) -> dict[str, int]:
    counts = triage.apply_triage(
        session, [(d.item_id, d.decision) for d in body.decisions], utcnow()
    )
    session.commit()
    return counts


@router.get("/duplicates", tags=["duplicates"])
def list_duplicates(session: SessionDep) -> list[duplicates.DuplicateGroup]:
    return duplicates.list_groups(session)
