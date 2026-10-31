"""Full backup: every table as JSON lines and the recordings, in one zip (module J, M10.a, D-302).

The tables are read in **one read transaction** (`PRAGMA query_only` plus an explicit `BEGIN`, as
the CSV export does, D-271), so the manifest's counts match the files while the app keeps running.
Values are read as SQLite stores them and encoded by `backup_format`, which makes the round trip
exact (clock columns included). The archive holds no environment variable and no key: only tables,
recordings and the manifest.

The `backup.created` event is written in a short transaction **after** the archive is complete, so
the archive does not contain the event that describes it (accepted and documented).
"""

import hashlib
import json
import os
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Literal

from sqlalchemy import Engine, Table
from sqlalchemy.orm import Session

from app import __version__
from app.db import migrate
from app.db.base import Base
from app.db.demo_marker import DEMO_MARKER_KEY
from app.db.event_log import record_event
from app.db.models import ProductionAttempt, ReviewLog
from app.domain.events import BackupCreated
from app.services import backup_format as fmt
from app.services.export import _snapshot
from app.services.stats import context, read_only
from app.speech.audio_store import is_stored_path

Kind = Literal["manual", "auto"]
CHUNK = 1024 * 1024

# Tables left out of the archive: Alembic's own table, replaced by the manifest's revision.
EXCLUDED_TABLES = frozenset({"alembic_version"})
# Where a row refers to a recording.
AUDIO_COLUMNS: tuple[tuple[str, str], ...] = (
    (ProductionAttempt.__tablename__, "audio_path"),
    (ReviewLog.__tablename__, "audio_path"),
)


class BackupError(Exception):
    """A backup that cannot be made (`code` is stable, `message` is English)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class BackupInfo:
    kind: Kind
    study_day: str
    tables: dict[str, int]
    audio_files: int
    missing_audio: list[str]
    bytes: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return sum(self.tables.values())


def backup_tables() -> list[Table]:
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


class _Hashed:
    """Writes into a zip member while counting and hashing what goes through."""

    def __init__(self, member: IO[bytes]) -> None:
        self.member = member
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> None:
        self.member.write(data)
        self.digest.update(data)
        self.size += len(data)


def _write_table(
    session: Session, archive: zipfile.ZipFile, table: Table
) -> tuple[int, dict[str, Any], set[str]]:
    """Write `tables/<name>.jsonl`; returns (rows, file entry, audio paths seen)."""
    preparer = session.get_bind().dialect.identifier_preparer
    names = [column.name for column in table.columns]
    kinds = [fmt.column_kind(column.type) for column in table.columns]
    order = ", ".join(preparer.quote(column.name) for column in table.primary_key.columns)
    listed = ", ".join(preparer.quote(n) for n in names)
    # Identifiers come from the models and are quoted by the dialect.
    sql = f"SELECT {listed} FROM {preparer.quote(table.name)} ORDER BY {order}"  # noqa: S608
    audio_index = next((names.index(c) for t, c in AUDIO_COLUMNS if t == table.name), None)
    audio: set[str] = set()
    rows = 0
    with archive.open(fmt.table_member(table.name), "w") as member:
        out = _Hashed(member)
        for raw in session.connection().exec_driver_sql(sql):
            values = [
                fmt.encode_stored(kind, value) for kind, value in zip(kinds, raw, strict=True)
            ]
            if audio_index is not None and values[audio_index]:
                audio.add(values[audio_index])
            line = json.dumps(dict(zip(names, values, strict=True)), ensure_ascii=False)
            out.write(line.encode("utf-8") + b"\n")
            rows += 1
    return rows, {"sha256": out.digest.hexdigest(), "size": out.size}, audio


def _write_audio(
    archive: zipfile.ZipFile, audio_root: Path, stored_path: str
) -> dict[str, Any] | None:
    """Copy one recording; None when the file is not there (or cannot be read)."""
    if not is_stored_path(stored_path):
        return None
    source = audio_root / stored_path
    try:
        handle = source.open("rb")
    except OSError:
        return None
    with handle, archive.open(fmt.audio_member(stored_path), "w") as member:
        out = _Hashed(member)
        while chunk := handle.read(CHUNK):
            out.write(chunk)
    return {"sha256": out.digest.hexdigest(), "size": out.size}


def write_backup(
    engine: Engine, now: datetime, audio_root: Path, stream: IO[bytes], *, kind: Kind = "manual"
) -> BackupInfo:
    """Write the archive into `stream`. Raises BackupError when the schema is not at head."""
    with read_only(engine) as session:
        _snapshot(session)
        ctx = context(session, now)
        # On the session's own connection: a second one would take the place of the first in the
        # pool, and `read_only` would reset `query_only` on the wrong connection.
        revision = (
            session.connection().exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        )
        if revision is None or revision != migrate.head_revision():
            raise BackupError(
                "database_out_of_date", "The database is not up to date: run `db upgrade` first."
            )
        marker = (
            session.connection()
            .exec_driver_sql("SELECT 1 FROM setting WHERE key = ?", (DEMO_MARKER_KEY,))
            .first()
        )
        files: dict[str, Any] = {}
        counts: dict[str, int] = {}
        referenced: set[str] = set()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for table in sorted(backup_tables(), key=lambda t: t.name):
                counts[table.name], entry, audio = _write_table(session, archive, table)
                files[fmt.table_member(table.name)] = entry
                referenced |= audio
            missing: list[str] = []
            audio_files = 0
            for stored_path in sorted(referenced):
                entry = _write_audio(archive, audio_root, stored_path)
                if entry is None:
                    missing.append(stored_path)
                else:
                    files[fmt.audio_member(stored_path)] = entry
                    audio_files += 1
            manifest = {
                "format": fmt.FORMAT,
                "created_at": fmt.encode_stored("datetime", ctx.now),
                "app_version": __version__,
                "alembic_revision": revision,
                "study_day": ctx.today.isoformat(),
                "timezone": ctx.tz.key,
                "demo": marker is not None,
                "kind": kind,
                "tables": counts,
                "files": files,
                "missing_audio": missing,
            }
            archive.writestr(fmt.MANIFEST, json.dumps(manifest, indent=2) + "\n")
    stream.flush()
    size = stream.seek(0, os.SEEK_END)
    return BackupInfo(kind, ctx.today.isoformat(), counts, audio_files, missing, size, manifest)


def file_name_for(engine: Engine, now: datetime) -> str:
    with read_only(engine) as session:
        return fmt.backup_file_name(now, context(session, now).tz)


def record_created(engine: Engine, info: BackupInfo, now: datetime) -> None:
    """The `backup.created` event, in its own short transaction (never in the archive)."""
    with Session(engine) as session:
        record_event(
            session,
            BackupCreated(
                kind=info.kind,
                tables=len(info.tables),
                rows=info.rows,
                audio_files=info.audio_files,
                bytes=info.bytes,
            ),
            occurred_at=now,
        )
        session.commit()


def replace_with_retries(
    source: Path,
    target: Path,
    *,
    retries: int = 3,
    delay: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """`os.replace`; a cloud-sync client (OneDrive) may hold the target for a moment on Windows
    (D-062): `retries` more attempts, `delay` seconds apart, then the last error is raised."""
    for attempt in range(retries + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == retries:
                raise
            sleep(delay)


def backup_to_file(
    engine: Engine,
    now: datetime,
    audio_root: Path,
    target: Path,
    *,
    kind: Kind = "manual",
    retries: int = 0,
) -> BackupInfo:
    """Write the archive to `<target>.tmp-<pid>` in the same folder, then `os.replace` it onto
    `target`; the event follows. The temporary file never survives a failure."""
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as stream:
            info = write_backup(engine, now, audio_root, stream, kind=kind)
        replace_with_retries(temporary, target, retries=retries)
    finally:
        temporary.unlink(missing_ok=True)
    record_created(engine, info, now)
    return info
