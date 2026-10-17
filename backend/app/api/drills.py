"""Targeted drills (module E, M5.a2).

`POST /drills` calls the AI, so it is a plain `def` route with **no database session in its
dependencies** (D-038). An AI failure is not an HTTP error: the answer is 200 with `status`
(`incomplete` or `unavailable`), `reason` and `drill: null`; success is 201. Active recall
(D-103): an unanswered item never carries its answer, accepted forms, right option or
explanations; the rule is shown from the start. Errors use the D-063 format.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_engine, get_session
from app.db.models import ProductionAttempt
from app.domain import drills as rules
from app.services import drills, error_log

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


# --- Shapes --------------------------------------------------------------------------------------


class DrillCategoryOut(BaseModel):
    code: str
    label_en: str
    label_fr: str


class ItemResultOut(BaseModel):
    outcome: Literal["exact", "wrong", "empty"]
    expected: str
    accepted: list[str]
    correct_index: int | None  # into the `options` as shown; null for a gap-fill
    explanation_en: str
    explanation_fr: str
    given: str


class DrillItemOut(BaseModel):
    index: int  # from 0
    kind: Literal["gap_fill", "choice"]
    sentence: str  # with one `___`
    options: list[str] | None  # shuffled by the server, same order on every read
    answered: bool
    result: ItemResultOut | None  # only once answered


class ScoreOut(BaseModel):
    correct: int
    wrong: int
    empty: int
    answered: int
    total: int


class DrillOut(BaseModel):
    id: int
    category: DrillCategoryOut
    rule_en: str
    rule_fr: str
    items: list[DrillItemOut]
    completed: bool
    score: ScoreOut
    created_at: datetime


def drill_out(session: Session, attempt: ProductionAttempt) -> DrillOut:
    feedback: dict[str, Any] = dict(attempt.ai_feedback or {})
    code = feedback["category_code"]
    category = error_log.category_by_code(session, code)
    answers = drills.answers_by_index(feedback)
    items: list[DrillItemOut] = []
    for index, item in enumerate(feedback["items"]):
        public = rules.public_item(attempt.id, index, item)
        answer = answers.get(index)
        result = (
            ItemResultOut(
                **rules.item_result(
                    attempt.id, index, item, outcome=answer["outcome"], given=answer["given"]
                )
            )
            if answer is not None
            else None
        )
        items.append(DrillItemOut(**public, answered=answer is not None, result=result))
    score = rules.score(len(items), list(answers.values()))
    return DrillOut(
        id=attempt.id,
        category=DrillCategoryOut(
            code=code,
            label_en=category.label_en if category else code,
            label_fr=category.label_fr if category else code,
        ),
        rule_en=feedback["rule_en"],
        rule_fr=feedback["rule_fr"],
        items=items,
        completed=score["answered"] == score["total"],
        score=ScoreOut(**score),
        created_at=attempt.created_at,
    )


# --- Generation ----------------------------------------------------------------------------------


class DrillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    count: Annotated[int, Field(ge=rules.MIN_ITEMS, le=rules.MAX_ITEMS)] = rules.DEFAULT_ITEMS
    study_session_id: int | None = None


class DrillCreatedOut(BaseModel):
    status: Literal["ok", "incomplete", "unavailable"]
    reason: str | None
    drill: DrillOut | None


@router.post("/drills", status_code=201, tags=["drills"])
def create_drill(
    body: DrillRequest, response: Response, engine: EngineDep, gateway: GatewayDep, now: NowDep
) -> DrillCreatedOut:
    """Have the AI write a drill on one category (level 2 or more, not pronunciation). Takes a
    few seconds. 201 with the drill; 200 with `status` `unavailable` or `incomplete` and no drill
    when the AI failed (nothing was written, try again)."""
    result = drills.generate_drill(
        _factory(engine),
        gateway,
        body.category_code,
        count=body.count,
        study_session_id=body.study_session_id,
        clock=lambda: now,
    )
    if result.drill_id is None:
        response.status_code = 200
        return DrillCreatedOut(
            status=result.status,
            reason=str(result.reason) if result.reason is not None else None,
            drill=None,
        )
    with Session(engine) as session:
        attempt = drills.get_drill(session, result.drill_id)
        return DrillCreatedOut(status="ok", reason=None, drill=drill_out(session, attempt))


# --- Reading -------------------------------------------------------------------------------------


class DrillPageOut(BaseModel):
    items: list[DrillOut]
    total: int
    limit: int
    offset: int


@router.get("/drills", tags=["drills"])
def list_drills(
    session: SessionDep,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=drills.MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DrillPageOut:
    """Newest first; `category` is a code prefix."""
    page, total = drills.list_drills(session, category=category, limit=limit, offset=offset)
    return DrillPageOut(
        items=[drill_out(session, attempt) for attempt in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/drills/{drill_id}", tags=["drills"])
def get_drill(drill_id: int, session: SessionDep) -> DrillOut:
    return drill_out(session, drills.get_drill(session, drill_id))


# --- Answering -----------------------------------------------------------------------------------


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Annotated[str, Field(max_length=200)] | None = None  # a gap-fill
    choice_index: Annotated[int, Field(ge=0)] | None = None  # a choice, into the shown options
    response_time_ms: Annotated[int, Field(ge=0)]


class AnswerOut(BaseModel):
    result: ItemResultOut
    error_event_id: int | None  # the error logged for a wrong answer
    drill: DrillOut


@router.post("/drills/{drill_id}/items/{index}/answer", tags=["drills"])
def answer_item(
    drill_id: int, index: int, body: AnswerRequest, session: SessionDep, now: NowDep
) -> AnswerOut:
    """Grade one item exactly (no typo tolerance) and show its solution. A wrong answer is
    logged as an error (source `drill`); an empty one is not."""
    outcome = drills.answer_item(
        session,
        drill_id,
        index,
        answer=body.answer,
        choice_index=body.choice_index,
        response_time_ms=body.response_time_ms,
        at=now,
    )
    session.commit()
    attempt = drills.get_drill(session, drill_id)
    return AnswerOut(
        result=ItemResultOut(**outcome.result),
        error_event_id=outcome.error_event_id,
        drill=drill_out(session, attempt),
    )
