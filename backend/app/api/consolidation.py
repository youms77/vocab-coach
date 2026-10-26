"""Consolidation (module G, M7.a1): which decks are ready, tasks (talk, speech, interview answer),
their statuses and the Markdown export for a voice tutor.

`POST /consolidation/tasks` calls the AI, so it is a plain `def` route with **no database session
in its dependencies** (D-038). An AI failure is not an error: the task is made from a template and
the answer says so (`source: "template"`, `reason`). Errors use the D-063 format: `deck_not_found`,
`task_not_found`, `not_ready` (with `reason`), `task_open` (with `task_id`), `invalid_transition`,
`invalid_request`.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_engine, get_session
from app.db.models import ConsolidationTask, Deck, LexicalItem, ProductionTarget
from app.domain import consolidation as rules
from app.domain.consolidation import NotReadyReason, TaskStatus, TaskType
from app.services import consolidation

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


# --- Shapes --------------------------------------------------------------------------------------


class DeckReadinessOut(BaseModel):
    deck_id: int
    name: str
    ready: bool
    reason: NotReadyReason | None
    ratio: float
    stable_cards: int
    productive_cards: int
    threshold_ratio: float
    min_stability_days: int
    candidates: int  # consolidated terms that could be used
    open_task_id: int | None


class Bilingual(BaseModel):
    en: str
    fr: str


class SectionOut(BaseModel):
    heading: Bilingual
    guidance: Bilingual
    item_ids: list[int]


class DeckRefOut(BaseModel):
    id: int
    name: str


class TargetOut(BaseModel):
    item_id: int
    term: str
    item_status: str
    used_correctly_count: int


class AttemptOut(BaseModel):
    production_id: int
    modality: str
    corrected: bool
    created_at: datetime


class TaskOut(BaseModel):
    id: int
    deck: DeckRefOut
    status: TaskStatus
    task_type: TaskType
    source: Literal["ai", "template"]
    title: Bilingual
    prompt: Bilingual
    audience: Bilingual
    target_minutes: int
    sections: list[SectionOut]
    targets: list[TargetOut]
    attempts: list[AttemptOut]
    created_at: datetime


def task_out(session: Session, task: ConsolidationTask) -> TaskOut:
    structure: dict[str, Any] = dict(task.suggested_structure or {})
    deck = session.get(Deck, task.deck_id)
    item_ids = consolidation.task_item_ids(session, task.id)
    items = {
        item.id: item
        for item in session.scalars(select(LexicalItem).where(LexicalItem.id.in_(item_ids)))
    }
    attempts = consolidation.task_attempts(session, task.id)
    correct: dict[int, int] = {}
    if attempts:
        for item_id in session.scalars(
            select(ProductionTarget.lexical_item_id).where(
                ProductionTarget.production_attempt_id.in_([a.id for a in attempts]),
                ProductionTarget.used_correctly.is_(True),
            )
        ):
            correct[item_id] = correct.get(item_id, 0) + 1
    return TaskOut(
        id=task.id,
        deck=DeckRefOut(id=task.deck_id, name=deck.name if deck else ""),
        status=rules.api_status(task.status),
        task_type=rules.type_of(task.task_kind),
        source=structure.get("source", "ai"),
        title=Bilingual(**structure["title"]),
        prompt=Bilingual(**structure["prompt"]),
        audience=Bilingual(**structure["audience"]),
        target_minutes=structure["target_minutes"],
        sections=[SectionOut(**section) for section in structure["sections"]],
        targets=[
            TargetOut(
                item_id=item_id,
                term=items[item_id].term,
                item_status=str(items[item_id].status),
                used_correctly_count=correct.get(item_id, 0),
            )
            for item_id in item_ids
            if item_id in items
        ],
        attempts=[
            AttemptOut(
                production_id=a.id,
                modality=str(a.modality),
                corrected=a.ai_feedback is not None,
                created_at=a.created_at,
            )
            for a in attempts
        ],
        created_at=task.created_at,
    )


# --- Decks ---------------------------------------------------------------------------------------


@router.get("/consolidation/decks", tags=["consolidation"])
def decks(session: SessionDep) -> list[DeckReadinessOut]:
    """Every deck with whether it can have a consolidation task now, and if not, the first reason
    (`excluded_kind`, `deck_done`, `task_open`, `no_productive_cards`, `below_ratio`,
    `not_enough_candidates`)."""
    return [
        DeckReadinessOut(
            deck_id=state.deck.id,
            name=state.deck.name,
            ready=state.readiness.ready,
            reason=state.readiness.reason,
            ratio=state.readiness.ratio,
            stable_cards=state.readiness.stable_cards,
            productive_cards=state.readiness.productive_cards,
            threshold_ratio=state.threshold_ratio,
            min_stability_days=state.min_stability_days,
            candidates=len(state.readiness.candidates),
            open_task_id=state.open_task_id,
        )
        for state in consolidation.deck_overview(session)
    ]


# --- Tasks ---------------------------------------------------------------------------------------


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck_id: int
    task_type: TaskType
    term_count: Annotated[int, Field(ge=rules.MIN_TERMS, le=rules.MAX_TERMS)] | None = None
    study_session_id: int | None = None


class TaskCreatedOut(BaseModel):
    status: Literal["ok"] = "ok"
    source: Literal["ai", "template"]
    reason: str | None  # why a template was used (an AI failure), else null
    task: TaskOut


@router.post("/consolidation/tasks", status_code=201, tags=["consolidation"])
def create_task(
    body: TaskRequest, engine: EngineDep, gateway: GatewayDep, now: NowDep
) -> TaskCreatedOut:
    """Have the AI write a task for a ready deck (8 to 15 of its most fragile consolidated terms;
    12 by default). Takes a few seconds. Without AI the task comes from a template."""
    result = consolidation.create_task(
        _factory(engine),
        gateway,
        body.deck_id,
        body.task_type,
        term_count=body.term_count,
        study_session_id=body.study_session_id,
        clock=lambda: now,
    )
    with Session(engine) as session:
        task = consolidation.get_task(session, result.task_id)
        return TaskCreatedOut(
            source=result.source, reason=result.reason, task=task_out(session, task)
        )


class TaskPageOut(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int


@router.get("/consolidation/tasks", tags=["consolidation"])
def list_tasks(
    session: SessionDep,
    deck_id: int | None = None,
    status: TaskStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=consolidation.MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskPageOut:
    """Newest first."""
    page, total = consolidation.list_tasks(
        session, deck_id=deck_id, status=status, limit=limit, offset=offset
    )
    return TaskPageOut(
        items=[task_out(session, task) for task in page], total=total, limit=limit, offset=offset
    )


@router.get("/consolidation/tasks/{task_id}", tags=["consolidation"])
def get_task(task_id: int, session: SessionDep) -> TaskOut:
    return task_out(session, consolidation.get_task(session, task_id))


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: TaskStatus


@router.post("/consolidation/tasks/{task_id}/status", tags=["consolidation"])
def change_status(task_id: int, body: StatusRequest, session: SessionDep, now: NowDep) -> TaskOut:
    """`proposed` to `accepted` or `dismissed`, `accepted` to `completed` or `dismissed`; any
    other move is 409 `invalid_transition`."""
    task = consolidation.change_status(session, task_id, body.to, at=now)
    session.commit()
    return task_out(session, task)


@router.get("/consolidation/tasks/{task_id}/export", tags=["consolidation"])
def export_task(task_id: int, session: SessionDep, lang: Literal["en", "fr"] = "en") -> Response:
    """A Markdown page to paste into a voice chat with a tutor: the task, its structure, the terms
    with their simple definitions and what the tutor must do."""
    task = consolidation.get_task(session, task_id)
    content = consolidation.export_markdown(session, task, lang)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="consolidation-task-{task_id}-{lang}.md"'
        },
    )
