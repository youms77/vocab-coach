"""Today's session endpoints (module D, M4.a): plan, start, next step, end.

The current time comes from `NowDep` (D-097), so tests drive a whole day with one fake clock.
Writes are allowed on the demo database. Errors use the D-063 format.
"""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.db.models import StudySession
from app.domain.planner import SessionPlan
from app.services import study_sessions
from app.services.planning import plan_today

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]


class SessionOut(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime | None
    study_day: date
    planned: dict[str, Any]
    summary: dict[str, Any] | None


class TodayOut(BaseModel):
    plan: SessionPlan
    open_session: SessionOut | None


def session_out(session: Session, study: StudySession) -> SessionOut:
    return SessionOut(
        id=study.id,
        started_at=study.started_at,
        ended_at=study.ended_at,
        study_day=study_sessions.study_day_of_session(session, study),
        planned=dict(study.planned or {}),
        summary=dict(study.summary) if study.summary is not None else None,
    )


@router.get("/session/today", tags=["session"])
def today(session: SessionDep, now: NowDep) -> TodayOut:
    """Today's plan (computed now, nothing written) and today's open session, if any."""
    plan = plan_today(session, now)
    study = study_sessions.open_session_of_day(session, plan.study_day)
    return TodayOut(plan=plan, open_session=session_out(session, study) if study else None)


@router.post("/session/start", tags=["session"])
def start(session: SessionDep, now: NowDep, response: Response) -> SessionOut:
    """201 with a new session (plan frozen); 200 with today's session when one is open. A session
    left open on an earlier study day is closed first."""
    study, created = study_sessions.start_session(session, now)
    session.commit()
    response.status_code = 201 if created else 200
    return session_out(session, study)


@router.get("/session/{session_id}/next", tags=["session"])
def next_step(
    session_id: int, session: SessionDep, now: NowDep, practice_seen: bool = False
) -> study_sessions.Step:
    """The next step, computed live. Never contains a solution (active recall)."""
    study = study_sessions.get_study_session(session, session_id)
    return study_sessions.next_step(session, study, now, practice_seen=practice_seen)


@router.post("/session/{session_id}/end", tags=["session"])
def end(session_id: int, session: SessionDep, now: NowDep) -> SessionOut:
    study = study_sessions.get_study_session(session, session_id)
    study_sessions.end_session(session, study, now)
    session.commit()
    return session_out(session, study)
