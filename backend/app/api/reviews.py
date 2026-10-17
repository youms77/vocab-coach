"""Review endpoints (module C, M4.a): grade an attempt, record the final rating, reveal.

`grade` and `reveal` write nothing. `POST /reviews` grades the answer again on the server: the
client never sends the proposed rating (an unknown field is refused). No AI call here.
"""

from datetime import datetime
from typing import Annotated, Any, Self

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.domain.enums import ItemStatus, SrsState
from app.domain.grading import DiffPart
from app.domain.srs import Rating
from app.services import review_flow, study_sessions

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
Answer = Annotated[str, Field(max_length=2000)]
ExerciseType = Annotated[str, Field(min_length=1, max_length=64)]
# Pydantic refuses a negative time; `record` caps a long one at MAX_RESPONSE_TIME_MS.
ResponseTime = Annotated[int, Field(ge=0)]


class GradeRequest(BaseModel):
    """A card (review) or a term being discovered (its immediate exercises): exactly one."""

    model_config = ConfigDict(extra="forbid")

    card_id: int | None = None
    item_id: int | None = None
    exercise_type: ExerciseType
    exercise_template_id: int | None = None
    answer: Answer | None = None
    choice_index: int | None = None
    response_time_ms: ResponseTime

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if (self.card_id is None) == (self.item_id is None):
            raise ValueError("send exactly one of `card_id` and `item_id`")
        return self


class DiffOut(BaseModel):
    op: str
    given: str
    expected: str


class GradeOut(BaseModel):
    outcome: str | None
    proposed_rating: int | None
    expected: str | None
    accepted: list[str]
    diff: list[DiffOut] | None
    warnings: list[str]
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


def _diff(parts: list[DiffPart] | None) -> list[DiffOut] | None:
    if parts is None:
        return None
    return [DiffOut(op=p.op, given=p.given, expected=p.expected) for p in parts]


def _context(
    session: Session,
    card_id: int | None,
    item_id: int | None,
    exercise_type: str,
    template_id: int | None,
) -> review_flow.ExerciseContext:
    if card_id is not None:
        return review_flow.card_context(session, card_id, exercise_type, template_id)
    assert item_id is not None  # noqa: S101 (checked by the request model)
    return review_flow.discovery_context(session, item_id, exercise_type, template_id)


@router.post("/reviews/grade", tags=["reviews"])
def grade(body: GradeRequest, session: SessionDep, now: NowDep) -> GradeOut:
    """Grade an attempt and return the solution. Writes nothing."""
    ctx = _context(
        session, body.card_id, body.item_id, body.exercise_type, body.exercise_template_id
    )
    graded = review_flow.grade(
        session,
        ctx,
        answer=body.answer,
        choice_index=body.choice_index,
        response_time_ms=review_flow.clamp_response_time(body.response_time_ms),
        now=now,
    )
    session.rollback()  # nothing to keep: make sure of it
    result = graded.result
    return GradeOut(
        outcome=result.outcome.value if result.outcome is not None else None,
        proposed_rating=int(result.proposed_rating) if result.proposed_rating else None,
        expected=result.expected,
        accepted=result.accepted,
        diff=_diff(result.diff),
        warnings=result.warnings,
        solution=graded.solution,
        sheet_summary=graded.sheet_summary,
    )


class RecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: int
    session_id: int
    exercise_type: ExerciseType
    exercise_template_id: int | None = None
    answer: Answer | None = None
    choice_index: int | None = None
    response_time_ms: ResponseTime
    final_rating: Annotated[int, Field(ge=1, le=4)]
    expected_reps: Annotated[int, Field(ge=0)]


class RecordOut(BaseModel):
    review_log_id: int
    due_after: datetime
    state_after: SrsState
    item_status: ItemStatus
    item_status_changed: bool


@router.post("/reviews", tags=["reviews"])
def record(body: RecordRequest, session: SessionDep, now: NowDep) -> RecordOut:
    """Record the final rating (the user may override the proposed one)."""
    study = study_sessions.require_open(session, body.session_id)
    ctx = review_flow.card_context(
        session, body.card_id, body.exercise_type, body.exercise_template_id
    )
    recorded = review_flow.record(
        session,
        ctx,
        answer=body.answer,
        choice_index=body.choice_index,
        response_time_ms=body.response_time_ms,
        final_rating=Rating(body.final_rating),
        expected_reps=body.expected_reps,
        study_session_id=study.id,
        now=now,
    )
    session.commit()
    return RecordOut(
        review_log_id=recorded.review_log_id,
        due_after=recorded.due_after,
        state_after=recorded.state_after,
        item_status=recorded.item_status,
        item_status_changed=recorded.item_status_changed,
    )


class RevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: int
    exercise_type: ExerciseType
    exercise_template_id: int | None = None


class RevealOut(BaseModel):
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


@router.post("/reviews/reveal", tags=["reviews"])
def reveal(body: RevealRequest, session: SessionDep) -> RevealOut:
    """The solution of a self-graded exercise, after the user's attempt. Writes nothing."""
    ctx = review_flow.card_context(
        session, body.card_id, body.exercise_type, body.exercise_template_id
    )
    solution, summary = review_flow.reveal(ctx)
    return RevealOut(solution=solution, sheet_summary=summary)
