"""General English tracks (module H): word-list tracks (M8.a1) and speaking scenario units (M8.a2).

`GET /curriculum/tracks`, `GET /curriculum/tracks/{code}?limit&offset`, `POST .../start`,
`POST .../units/{n}/open` (word lists), `GET /curriculum/units/{id}` (a scenario unit carries its
content in `scenario`). Scenario units: `POST .../units/{n}/generate` calls the AI, so it is a
plain `def` route with **no database session in its dependencies** (D-038); an AI failure is an
answer (`status` `incomplete` or `unavailable`, nothing written). `PUT /units/{id}/content`
replaces whole parts under `expected_revision`, `POST /units/{id}/steps/{step}` marks `formulas`
or `dialogue`, `POST /units/{id}/terms` puts formulas in triage. Errors use the D-063 format:
`track_not_found`, `unit_not_found` (404), `wordlist_missing`, `track_not_started`,
`unit_generated`, `unit_changed` (409), `not_a_wordlist_track`, `not_a_scenario_track`,
`not_a_scenario_unit`, `invalid_content` (with `problems`), `invalid_step` (422),
`syllabus_unavailable` (503).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_engine, get_session
from app.services import curriculum, curriculum_units

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


class TermsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indices: list[int] | None = None  # formulas to add (0-based); all when absent


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


@router.post("/curriculum/tracks/{code}/units/{number}/generate", tags=["curriculum"])
def generate_unit(
    code: str, number: int, engine: EngineDep, gateway: GatewayDep, now: NowDep
) -> curriculum_units.GenerationResult:
    """Write a scenario unit with the AI (a few seconds). 200 with `status` `ok` and the unit, or
    `incomplete` / `unavailable` with `reason` and nothing written: try again later."""
    return curriculum_units.generate_unit(
        _factory(engine), gateway, code, number, clock=lambda: now
    )


@router.put("/curriculum/units/{unit_id}/content", tags=["curriculum"])
def edit_content(
    unit_id: int, edit: curriculum_units.ContentEdit, session: SessionDep, now: NowDep
) -> curriculum.UnitOut:
    unit = curriculum_units.edit_content(session, unit_id, edit, now)
    out = curriculum._unit_out(session, unit, curriculum_units.track_code_of(session, unit))
    session.commit()
    return out


@router.post("/curriculum/units/{unit_id}/steps/{step}", tags=["curriculum"])
def mark_step(
    unit_id: int, step: str, session: SessionDep, now: NowDep
) -> curriculum_units.StepResult:
    result = curriculum_units.mark_step(session, unit_id, step, now)
    session.commit()
    return result


@router.post("/curriculum/units/{unit_id}/terms", tags=["curriculum"])
def add_terms(
    unit_id: int, body: TermsRequest, session: SessionDep, now: NowDep
) -> curriculum_units.TermsResult:
    result = curriculum_units.add_terms(session, unit_id, body.indices, now)
    session.commit()
    return result
