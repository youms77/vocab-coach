"""Bringing the database to `head` when the use mode starts (M10.b, D-313).

- No database file: created by `upgrade` (as in development).
- Personal database behind `head`: a copy of the file is made first, in `data/backups/`, then
  `upgrade` runs. If the copy fails, nothing is upgraded.
- Demo database behind `head`: never upgraded. A message names `demo seed --reset`; the start
  goes on when the file still has a schema revision (it is usable), else it stops.

The copy is a plain SQLite file, not a `vocab-coach-backup-1` archive: that format only exists
for a schema at `head` (`database_out_of_date`, D-303), and an old schema is exactly the case
here. The file is taken with SQLite's own online backup API, so it is consistent even with a
write-ahead log, then checked (`integrity_check`, same revision). Restoring it is a file copy.
Recordings are not touched by a migration and are not copied. Its name does not match the
rotation's pattern (`backup_format.is_backup_file_name`): the automatic copy never deletes it.
"""

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine

from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file

Out = Callable[[str], None]
Upgrade = Callable[[str], object]


class StartupError(Exception):
    """The start must stop (exit code 2); the message says why and what to do."""


@dataclass(frozen=True)
class Preparation:
    action: str  # "ready" | "created" | "upgraded" | "demo_behind"
    from_revision: str | None = None
    backup: Path | None = None


def pre_upgrade_name(revision: str | None, now: datetime) -> str:
    return f"vocab-coach-pre-upgrade-from-{revision or 'none'}-{now:%Y%m%d-%H%M%S}.sqlite3"


def _stored_revision(file: Path) -> str | None:
    connection = sqlite3.connect(file)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()
    return None if row is None else str(row[0])


def copy_before_upgrade(db_file: Path, target: Path, revision: str | None) -> None:
    """Consistent copy of `db_file` to `target`, checked; the temporary file never survives."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        source = sqlite3.connect(db_file)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
            verdict = destination.execute("PRAGMA integrity_check").fetchone()
        finally:
            destination.close()
            source.close()
        if verdict is None or verdict[0] != "ok":
            raise StartupError("the copy of the database did not pass the integrity check")
        if _stored_revision(temporary) != revision:
            raise StartupError(
                "the copy of the database does not have the revision of the original"
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_database(
    settings: Settings, upgrade: Upgrade, now: datetime, out: Out = print
) -> Preparation:
    """Make the selected database ready for the use mode; raise StartupError to stop."""
    url = settings.resolved_database_url
    db_file = sqlite_file(url)
    if db_file is None or not db_file.exists() or db_file.stat().st_size == 0:
        upgrade(url)
        out(f"Database created ({url}).")
        return Preparation("created")

    engine: Engine = create_db_engine(url)
    try:
        status = migrate.schema_status(engine)
    finally:
        engine.dispose()
    if status.at_head:
        return Preparation("ready")

    if settings.demo:
        out(
            f"The demo database is at revision {status.revision or 'none'}, the application "
            f"expects {status.head}. Rebuild it with: "
            "cd backend; uv run python -m app demo seed --reset"
        )
        if status.revision is None:
            raise StartupError("The demo database has no schema revision: rebuild it (see above).")
        return Preparation("demo_behind", status.revision)

    target = settings.resolved_data_dir / "backups" / pre_upgrade_name(status.revision, now)
    try:
        copy_before_upgrade(db_file, target, status.revision)
    except (StartupError, OSError, sqlite3.Error) as exc:
        raise StartupError(
            f"The database was NOT upgraded: its backup could not be made ({exc}). "
            "Free some disk space or fix the folder data/backups, then start again."
        ) from exc
    out(f"Database backup before the upgrade: {target}")
    upgrade(url)
    out(f"Database upgraded from {status.revision or 'none'} to {status.head}.")
    return Preparation("upgraded", status.revision, target)
