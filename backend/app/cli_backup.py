"""`python -m app backup create | verify | restore | auto` (module J, M10.a).

`create` and `auto` read the database (the only write is the `backup.created` event); `verify`
reads the archive only; `restore` replaces the database and the recordings and **needs the
application stopped**. `--demo` (before the command) works on the demo database.

Exit codes (D-053): 0 done, 1 the automatic copy failed, 2 usage error (archive refused, target not
empty, file in use, no database or not up to date, nothing configured, demo database).
"""

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.cli_errors import _console_safe
from app.cli_library import EXIT_OK, EXIT_USAGE, _open
from app.config import Settings
from app.db.base import utcnow
from app.db.engine import sqlite_file
from app.services import backup, backup_auto
from app.services.backup import BackupError
from app.services.backup_restore import restore_backup
from app.services.backup_verify import verify_archive
from app.speech.audio_store import AudioStore

EXIT_FAILED = 1
Out = Callable[[str], None]

KEYS_REMINDER = (
    "The AI keys are not part of a backup (they stay in .env). Enter them again in Settings, "
    "or copy your .env file yourself."
)


def _refused(exc: BackupError) -> int:
    print(f"{exc.message} [{exc.code}]", file=sys.stderr)
    return EXIT_USAGE


def _size(count: int) -> str:
    return f"{count / 1024 / 1024:.1f} MB"


def run_backup_create(
    url: str,
    settings: Settings,
    target: Path | None = None,
    *,
    force: bool = False,
    now: datetime | None = None,
    out: Out = print,
) -> int:
    """Write a full backup; by default `<data_dir>/backups/vocab-coach-backup-DATE-TIME.zip`."""
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    now = now or utcnow()
    try:
        if target is None:
            target = settings.resolved_data_dir / "backups" / backup.file_name_for(engine, now)
        if target.exists() and not force:
            print(f"{target} already exists. Use --force to replace it.", file=sys.stderr)
            return EXIT_USAGE
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            info = backup.backup_to_file(
                engine, now, AudioStore.for_settings(settings).root, target
            )
        except BackupError as exc:
            return _refused(exc)
    finally:
        engine.dispose()
    out(
        f"Backup of {info.rows} rows from {len(info.tables)} tables and {info.audio_files} "
        f"recordings ({_size(info.bytes)}) written to {target}"
    )
    if info.missing_audio:
        out(f"{len(info.missing_audio)} recordings are referenced but missing from disk.")
    out("It holds all your personal data and no AI key. Keep it somewhere private.")
    return EXIT_OK


def run_backup_verify(path: Path, *, out: Out = print) -> int:
    """Check an archive without writing anything."""
    _console_safe()
    try:
        manifest = verify_archive(path)
    except BackupError as exc:
        return _refused(exc)
    rows = sum(manifest["tables"].values())
    audio = sum(1 for name in manifest["files"] if name.startswith("audio/"))
    out(
        f"{path.name} is sound: {manifest['format']}, made {manifest['created_at']} "
        f"({manifest['kind']}{', demo data' if manifest['demo'] else ''}), schema "
        f"{manifest['alembic_revision']}, {rows} rows in {len(manifest['tables'])} tables, "
        f"{audio} recordings, {len(manifest['missing_audio'])} missing."
    )
    return EXIT_OK


def run_backup_restore(
    settings: Settings,
    path: Path,
    *,
    replace: bool = False,
    yes: bool = False,
    out: Out = print,
) -> int:
    """Restore into an empty database; the application must be stopped."""
    _console_safe()
    if replace and not yes:
        print("--replace overwrites the current data: add --yes to confirm.", file=sys.stderr)
        return EXIT_USAGE
    db_file = sqlite_file(settings.resolved_database_url)
    if db_file is None:
        print("Restore only works with a SQLite file database.", file=sys.stderr)
        return EXIT_USAGE
    try:
        result = restore_backup(
            path,
            db_file=db_file,
            audio_dir=AudioStore.for_settings(settings).root,
            demo=settings.demo,
            replace=replace,
        )
    except BackupError as exc:
        return _refused(exc)
    out(
        f"Restored {result.rows} rows and {result.audio_files} recordings into {db_file}"
        + (f" (schema upgraded from {result.upgraded_from})." if result.upgraded_from else ".")
    )
    if result.db_backup is not None:
        out(f"The previous database was kept as {result.db_backup}")
    if result.audio_backup is not None:
        out(f"The previous recordings were kept in {result.audio_backup}")
    out(KEYS_REMINDER)
    return EXIT_OK


def run_backup_auto(
    url: str, settings: Settings, *, now: datetime | None = None, out: Out = print
) -> int:
    """Make the automatic copy now (the folder is set in Settings)."""
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        try:
            result = backup_auto.run_auto(engine, settings, now or utcnow())
        except BackupError as exc:
            return _refused(exc)
    finally:
        engine.dispose()
    if not result.ok:
        print(f"The automatic copy failed [{result.error}].", file=sys.stderr)
        return EXIT_FAILED
    out(f"Copy {result.name} written ({result.removed} old copies removed).")
    return EXIT_OK
