"""CSV export of the event tables (module I, M9.a). Read-only; no audio, no settings, no secret."""

import tempfile
from collections.abc import Iterator
from typing import IO, Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import Engine

from app.api.clock import NowDep
from app.api.errors import api_error, require_database
from app.db.engine import get_engine
from app.services import export
from app.services.stats import context, read_only

router = APIRouter(prefix="/export", tags=["export"], dependencies=[Depends(require_database)])

EngineDep = Annotated[Engine, Depends(get_engine)]
CHUNK = 64 * 1024
IN_MEMORY_LIMIT = 32 * 1024 * 1024  # larger archives spill to a temporary file


def _chunks(stream: IO[bytes]) -> Iterator[bytes]:
    try:
        stream.seek(0)
        while chunk := stream.read(CHUNK):
            yield chunk
    finally:
        stream.close()


@router.get(
    "/csv",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def export_csv(engine: EngineDep, now: NowDep) -> StreamingResponse:
    """A zip archive `vocab-coach-export-YYYYMMDD.zip`: one CSV per table, `manifest.json` and
    `data_dictionary.md`. Every table is read in one read transaction."""
    stream = tempfile.SpooledTemporaryFile(max_size=IN_MEMORY_LIMIT)  # noqa: SIM115 (closed by _chunks)
    try:
        with read_only(engine) as session:
            ctx = context(session, now)
            export.write_archive(session, ctx, stream)
    except BaseException:
        stream.close()
        raise
    name = export.archive_name(ctx.today)
    return StreamingResponse(
        _chunks(stream),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/csv/{table}", responses={200: {"content": {"text/csv": {}}}})
def export_table(table: str, engine: EngineDep, now: NowDep) -> Response:
    """One table as CSV (same format as in the archive). 404 `unknown_table` otherwise."""
    try:
        body = export.table_csv(engine, table, now)
    except export.UnknownTable as exc:
        raise api_error(
            404,
            "unknown_table",
            f"There is no exported table {table!r}.",
            tables=list(export.EXPORT_TABLES),
        ) from exc
    return Response(
        body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )
