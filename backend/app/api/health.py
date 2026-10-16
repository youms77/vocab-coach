"""Health check, used by the frontend home screen and by the launch scripts."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, text

from app import __version__
from app.db.demo_marker import has_demo_marker
from app.db.engine import get_engine, sqlite_file
from app.db.migrate import schema_status

router = APIRouter(tags=["health"])


class DatabaseHealth(BaseModel):
    ok: bool
    revision: str | None
    at_head: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    database: DatabaseHealth
    # True when the database holds generated demo data (it carries the demo marker).
    demo: bool


def database_health(engine: Engine) -> DatabaseHealth:
    db_file = sqlite_file(engine.url.render_as_string(hide_password=False))
    if db_file is not None and not db_file.exists():
        # Do not create an empty file just by checking: `db upgrade` creates the database.
        return DatabaseHealth(ok=False, revision=None, at_head=False)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        status = schema_status(engine)
    except Exception:
        return DatabaseHealth(ok=False, revision=None, at_head=False)
    return DatabaseHealth(ok=True, revision=status.revision, at_head=status.at_head)


def is_demo_database(engine: Engine, database: DatabaseHealth) -> bool:
    if not database.ok:
        return False
    try:
        return has_demo_marker(engine)
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health(engine: Annotated[Engine, Depends(get_engine)]) -> HealthResponse:
    # `status` stays "ok" while the API answers; the database state is reported separately.
    database = database_health(engine)
    return HealthResponse(
        status="ok",
        version=__version__,
        database=database,
        demo=is_demo_database(engine, database),
    )
