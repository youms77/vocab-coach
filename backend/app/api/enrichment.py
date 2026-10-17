"""Usage sheet and list-extension endpoints (module A, M3.b).

Routes that call the AI (`/enrichment/run`, `/items/{id}/sheet/regenerate`, `/decks/{id}/extension`)
are plain `def` routes with **no database session in their dependencies**: the service opens short
sessions itself and none is open while the provider answers (D-038). An AI failure is not an HTTP
error: the answer is 200 with `status` and `reason`, and the page explains it (degraded mode).
Errors use the D-063 format (`LibraryError` subclasses, see `app/api/errors.py`).
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.ai.schemas.list_extension import DEFAULT_COUNT, MAX_COUNT, MIN_COUNT
from app.api.errors import require_database
from app.api.library import ItemOut, items_out
from app.db.base import utcnow
from app.db.engine import get_engine, get_session
from app.db.models import LexicalItem
from app.domain.enums import ItemStatus
from app.domain.usage_sheet import UsageSheet
from app.services import enrichment, extension

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


# --- Batch enrichment ----------------------------------------------------------------------------


class PendingItem(BaseModel):
    item_id: int
    term: str
    status: ItemStatus


class PendingOut(BaseModel):
    count: int
    items: list[PendingItem]


@router.get("/enrichment/pending", tags=["enrichment"])
def pending(
    session: SessionDep, deck_id: int | None = None, include_incomplete: bool = False
) -> PendingOut:
    items = enrichment.list_pending(session, deck_id=deck_id, include_incomplete=include_incomplete)
    return PendingOut(
        count=len(items),
        items=[PendingItem(item_id=i.id, term=i.term, status=ItemStatus(i.status)) for i in items],
    )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck_id: int | None = None
    item_ids: Annotated[list[int], Field(max_length=200)] | None = None
    include_incomplete: bool = False


@router.post("/enrichment/run", tags=["enrichment"])
def run(body: RunRequest, engine: EngineDep, gateway: GatewayDep) -> enrichment.RunReport:
    """One batch (at most 5 terms). Can take a few minutes when the batch has to be split."""
    return enrichment.run_enrichment(
        _factory(engine),
        gateway,
        deck_id=body.deck_id,
        item_ids=body.item_ids,
        include_incomplete=body.include_incomplete,
    )


# --- Sheets --------------------------------------------------------------------------------------


@router.get("/items/{item_id}/sheet", tags=["enrichment"])
def get_sheet(item_id: int, session: SessionDep) -> enrichment.SheetVersion:
    return enrichment.get_sheet(session, item_id)


@router.get("/items/{item_id}/sheet/versions", tags=["enrichment"])
def sheet_versions(item_id: int, session: SessionDep) -> list[enrichment.SheetVersion]:
    return enrichment.list_versions(session, item_id)


class SheetPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: UsageSheet
    # The version the user started from: 409 `sheet_changed` if it is no longer the current one.
    base_enrichment_id: int | None = None


@router.put("/items/{item_id}/sheet", tags=["enrichment"])
def put_sheet(item_id: int, body: SheetPut, session: SessionDep) -> enrichment.SheetVersion:
    """Save an edited sheet, or type one by hand for a term that has none."""
    view = enrichment.save_sheet(
        session, item_id, body.content, utcnow(), base_enrichment_id=body.base_enrichment_id
    )
    session.commit()
    return view


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_overwrite: bool = False


@router.post("/items/{item_id}/sheet/regenerate", tags=["enrichment"])
def regenerate(
    item_id: int, body: RegenerateRequest, engine: EngineDep, gateway: GatewayDep
) -> enrichment.RunReport:
    """A new AI version; an edited sheet needs `confirm_overwrite` (409 `sheet_edited`)."""
    return enrichment.run_enrichment(
        _factory(engine),
        gateway,
        regenerate_id=item_id,
        confirm_overwrite=body.confirm_overwrite,
    )


# --- Exercises -----------------------------------------------------------------------------------


@router.get("/items/{item_id}/exercises", tags=["enrichment"])
def list_exercises(item_id: int, session: SessionDep) -> list[enrichment.ExerciseOut]:
    return enrichment.list_exercises(session, item_id)


class ExercisePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]


@router.patch("/exercises/{exercise_id}", tags=["enrichment"])
def patch_exercise(
    exercise_id: int, body: ExercisePatch, session: SessionDep
) -> enrichment.ExerciseOut:
    out = enrichment.update_exercise(session, exercise_id, body.content, utcnow())
    session.commit()
    return out


# --- List extension ------------------------------------------------------------------------------


class ExtensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: Annotated[int, Field(ge=MIN_COUNT, le=MAX_COUNT)] = DEFAULT_COUNT


class ExtensionOut(BaseModel):
    status: str  # ok | incomplete | unavailable
    reason: str | None
    created: list[ItemOut]
    suggested: int
    dropped_existing: int
    dropped_in_batch: int
    possible_duplicates: list[extension.PossibleDuplicate]


@router.post("/decks/{deck_id}/extension", status_code=201, tags=["enrichment"])
def extend_deck(
    deck_id: int,
    engine: EngineDep,
    gateway: GatewayDep,
    response: Response,
    body: ExtensionRequest | None = None,
) -> ExtensionOut:
    """201 with the new terms (waiting for triage); 200 with `status` when the AI failed."""
    report = extension.extend_deck(
        _factory(engine), gateway, deck_id, count=(body or ExtensionRequest()).count
    )
    if report.status != "ok":
        response.status_code = 200
    with _factory(engine)() as session:
        items = [session.get(LexicalItem, item_id) for item_id in report.created]
        created = items_out(session, [item for item in items if item is not None])
    return ExtensionOut(
        status=report.status,
        reason=report.reason.value if report.reason is not None else None,
        created=created,
        suggested=report.suggested,
        dropped_existing=report.dropped_existing,
        dropped_in_batch=report.dropped_in_batch,
        possible_duplicates=report.possible_duplicates,
    )
