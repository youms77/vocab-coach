"""Automatic backup copy into a folder of the owner's choice, with rotation (M10.a, D-307).

A copy is made after a study session ends, when the API starts if the last automatic copy is more
than 24 hours old, and on demand (`POST /api/backup/auto/run`, `backup auto`). Never on the demo
database. There is no thread of our own: the caller is a FastAPI `BackgroundTasks` function or the
startup hook.

The folder is checked when it is saved and again at every copy: absolute, existing, writable, and
not inside a Git repository (a backup holds all personal data; `data/` of the repository is the one
exception, it is ignored by Git). The archive is written to a temporary file in the folder, then
`os.replace`d; if a cloud-sync client holds the target, three more attempts 200 ms apart (as in
D-062). A failure is logged and kept in memory for the status route, and **never** blocks the user.

Rotation deletes the oldest files beyond `backup_auto_keep` among those whose name matches the
application's pattern exactly. No other file of the folder is touched.
"""

import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.models import EventLog
from app.db.settings_store import get_setting
from app.domain.events import EventType
from app.services import backup, backup_format
from app.services.backup import BackupError
from app.services.demo_guard import is_demo
from app.services.stats import context
from app.speech.audio_store import AudioStore

logger = logging.getLogger(__name__)

STARTUP_AFTER = timedelta(hours=24)
FOLDER_REASONS = ("not_absolute", "not_found", "not_writable", "inside_repository")


class FolderError(ValueError):
    """The folder cannot be used; `reason` is one of FOLDER_REASONS."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _State:
    last_error: str | None = None


# Kept in memory only (the status route reads it): an error is not worth a table.
state = _State()


def _repository_root(folder: Path) -> Path | None:
    for candidate in (folder, *folder.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def validate_folder(value: str) -> None:
    """Raise FolderError unless `value` is a usable backup folder. "" (disabled) is fine."""
    if value == "":
        return
    folder = Path(value)
    if not folder.is_absolute():
        raise FolderError("not_absolute")
    if not folder.is_dir():
        raise FolderError("not_found")
    root = _repository_root(folder.resolve())
    if root is not None and not folder.resolve().is_relative_to(root / "data"):
        raise FolderError("inside_repository")
    try:
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError:
        raise FolderError("not_writable") from None


def last_event_at(session: Session, kind: str) -> datetime | None:
    """When the last `backup.created` of this kind was recorded (its `occurred_at`)."""
    query = select(func.max(EventLog.occurred_at)).where(
        EventLog.event_type == EventType.BACKUP_CREATED.value,
        EventLog.payload["kind"].as_string() == kind,
    )
    found = session.execute(query).scalar_one()
    return None if found is None else found.replace(tzinfo=UTC)


def rotate(folder: Path, keep: int) -> list[str]:
    """Delete the oldest copies beyond `keep`; returns the names removed."""
    copies = sorted(
        (p for p in folder.iterdir() if backup_format.is_backup_file_name(p.name) and p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = []
    for old in copies[keep:]:
        try:
            old.unlink()
            removed.append(old.name)
        except OSError:
            logger.warning("Backup rotation could not delete %s", old.name)
    return removed


@dataclass(frozen=True)
class AutoResult:
    ok: bool
    name: str | None = None
    error: str | None = None
    removed: int = 0


def _fail(code: str, detail: str) -> AutoResult:
    state.last_error = code
    logger.warning("Automatic backup failed (%s): %s", code, detail)
    return AutoResult(ok=False, error=code)


def run_auto(
    engine: Engine,
    settings: Settings,
    now: datetime,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> AutoResult:
    """Make one automatic copy now. Raises BackupError `demo_read_only` / `backup_not_configured`;
    any other failure is returned (and remembered), never raised."""
    if is_demo(settings, engine):
        raise BackupError("demo_read_only", "Automatic copies are off on the demo database.")
    with Session(engine) as session:
        folder_text = str(get_setting(session, "backup_auto_folder"))
        keep = int(get_setting(session, "backup_auto_keep"))
        zone = context(session, now).tz
    if folder_text == "":
        raise BackupError("backup_not_configured", "No backup folder is set.")
    try:
        validate_folder(folder_text)
    except FolderError as exc:
        return _fail(exc.reason, "the folder is not usable")
    folder = Path(folder_text)
    target = folder / backup_format.backup_file_name(now, zone)
    audio_root = AudioStore.for_settings(settings).root
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as stream:
            info = backup.write_backup(engine, now, audio_root, stream, kind="auto")
        backup.replace_with_retries(temporary, target, retries=3, delay=0.2, sleep=sleep)
    except PermissionError as exc:
        return _fail("file_locked", str(exc))
    except OSError as exc:
        return _fail("write_failed", str(exc))
    except BackupError as exc:
        return _fail(exc.code, exc.message)
    finally:
        temporary.unlink(missing_ok=True)
    backup.record_created(engine, info, now)
    state.last_error = None
    removed = rotate(folder, keep)
    return AutoResult(ok=True, name=target.name, removed=len(removed))


def after_session(engine: Engine, settings: Settings, now: datetime) -> None:
    """BackgroundTasks entry after a session ends: nothing happens unless a folder is set."""
    try:
        run_auto(engine, settings, now)
    except BackupError:
        return  # demo or not configured: nothing to do
    except Exception:
        logger.exception("Automatic backup after a session failed")


def at_startup(settings: Settings, now: datetime | None = None) -> None:
    """Startup hook: one copy if a folder is set and the last automatic copy is over 24 h old."""
    db_file = sqlite_file(settings.resolved_database_url)
    if settings.demo or db_file is None or not db_file.exists():
        return
    now = now or datetime.now(UTC)
    engine = create_db_engine(settings.resolved_database_url)
    try:
        if not migrate.schema_status(engine).at_head:
            return
        with Session(engine) as session:
            if str(get_setting(session, "backup_auto_folder")) == "":
                return
            last = last_event_at(session, "auto")
        if last is not None and now - last <= STARTUP_AFTER:
            return
        run_auto(engine, settings, now)
    except (BackupError, SQLAlchemyError):
        return
    except Exception:
        logger.exception("Automatic backup at startup failed")
    finally:
        engine.dispose()
