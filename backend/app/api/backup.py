"""Full backup (module J, M10.a): download an archive, status of the automatic copy, run it now.

Errors follow D-063. The archive holds all personal data and no key. No path is ever returned: the
status only says whether a folder is configured.
"""

import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import api_error, require_database
from app.api.export import IN_MEMORY_LIMIT, _chunks
from app.config import get_settings
from app.db.engine import get_engine
from app.db.settings_store import get_setting
from app.services import backup, backup_auto, backup_format
from app.services.backup import BackupError
from app.services.demo_guard import is_demo
from app.services.stats import context, read_only
from app.speech.audio_store import AudioStore

router = APIRouter(prefix="/backup", tags=["backup"], dependencies=[Depends(require_database)])

EngineDep = Annotated[Engine, Depends(get_engine)]


class BackupStatus(BaseModel):
    auto_folder_configured: bool
    last_auto_at: str | None
    last_auto_error: str | None
    last_manual_at: str | None
    keep: int
    demo: bool


def _status(engine: Engine) -> BackupStatus:
    settings = get_settings()
    with Session(engine) as session:
        folder = str(get_setting(session, "backup_auto_folder"))
        keep = int(get_setting(session, "backup_auto_keep"))
        last_auto = backup_auto.last_event_at(session, "auto")
        last_manual = backup_auto.last_event_at(session, "manual")
    return BackupStatus(
        auto_folder_configured=folder != "",
        last_auto_at=None
        if last_auto is None
        else backup_format.encode_stored("datetime", last_auto),
        last_auto_error=backup_auto.state.last_error,
        last_manual_at=(
            None if last_manual is None else backup_format.encode_stored("datetime", last_manual)
        ),
        keep=keep,
        demo=is_demo(settings, engine),
    )


@router.post(
    "",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_backup(engine: EngineDep, now: NowDep) -> StreamingResponse:
    """A zip `vocab-coach-backup-YYYYMMDD-HHMMSS.zip`: every table as JSON lines, the recordings
    and a manifest. Read in one read transaction; the only write is the `backup.created` event."""
    stream = tempfile.SpooledTemporaryFile(max_size=IN_MEMORY_LIMIT)  # noqa: SIM115 (closed by _chunks)
    try:
        info = backup.write_backup(
            engine, now, AudioStore.for_settings(get_settings()).root, stream, kind="manual"
        )
        backup.record_created(engine, info, now)
    except BackupError as exc:
        stream.close()
        raise api_error(409, exc.code, exc.message) from None
    except BaseException:
        stream.close()
        raise
    with read_only(engine) as session:
        name = backup_format.backup_file_name(now, context(session, now).tz)
    return StreamingResponse(
        _chunks(stream),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/status")
def backup_status(engine: EngineDep) -> BackupStatus:
    return _status(engine)


@router.post("/auto/run")
def run_auto_backup(engine: EngineDep, now: NowDep) -> BackupStatus:
    """Make an automatic copy now. 409 `backup_not_configured` without a folder, 409
    `demo_read_only` on the demo; a copy that fails is reported in `last_auto_error`."""
    try:
        backup_auto.run_auto(engine, get_settings(), now)
    except BackupError as exc:
        raise api_error(409, exc.code, exc.message) from None
    return _status(engine)
