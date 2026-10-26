"""General English tracks (module H, M8.a1): word-list tracks and their units. No AI call.

`GET /curriculum/tracks`, `GET /curriculum/tracks/{code}?limit&offset`, `POST .../start`,
`POST .../units/{n}/open`, `GET /curriculum/units/{id}`. Errors use the D-063 format:
`track_not_found`, `unit_not_found` (404), `wordlist_missing`, `track_not_started` (409),
`not_a_wordlist_track` (422), `syllabus_unavailable` (503).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.services import curriculum

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/curriculum/tracks", tags=["curriculum"])
def list_tracks(session: SessionDep) -> list[curriculum.TrackSummary]:
    return curriculum.list_tracks(session)


@router.get("/curriculum/tracks/{code}", tags=["curriculum"])
def track_detail(
    code: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=curriculum.MAX_LIMIT)] = curriculum.DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> curriculum.TrackDetail:
    return curriculum.track_detail(session, code, limit=limit, offset=offset)


@router.post("/curriculum/tracks/{code}/start", tags=["curriculum"])
def start_track(code: str, session: SessionDep, now: NowDep) -> curriculum.StartResult:
    result = curriculum.start_track(session, code, now)
    session.commit()
    return result


@router.post("/curriculum/tracks/{code}/units/{number}/open", tags=["curriculum"])
def open_unit(code: str, number: int, session: SessionDep, now: NowDep) -> curriculum.OpenResult:
    result = curriculum.open_unit(session, code, number, now)
    session.commit()
    return result


@router.get("/curriculum/units/{unit_id}", tags=["curriculum"])
def get_unit(unit_id: int, session: SessionDep) -> curriculum.UnitOut:
    return curriculum.get_unit(session, unit_id)
