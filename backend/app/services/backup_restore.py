"""Restoring a backup into an empty database, with the application stopped (module J, M10.a, D-304).

1. `verify_archive` refuses a hostile or damaged archive before anything is written.
2. The new database is **built in a temporary file** next to the target: `alembic upgrade` to the
   manifest's revision (schema only), every table inserted with its original primary keys (the
   tables are reflected from that schema, so an archive made at an older revision loads into the
   schema it was made with), `alembic upgrade head`, then `sync_taxonomy()`. Foreign keys stay on,
   their check is deferred to the end of the insertion transaction, so a self-referencing table
   needs no special order. Clock columns are copied, never regenerated.
3. The recordings are unpacked into a temporary folder.
4. The swap follows D-188: the old recordings folder is set aside **before** the database is
   replaced (a file held open on Windows refuses the rename, and then nothing has changed), then
   the database, then the new folder. Any failure puts everything back.

The target must be empty (no row outside `alembic_version` and the taxonomy, D-033), otherwise
`replace=True`: the old database becomes `*.bak-YYYYMMDD-HHMMSS`, the old folder `audio.bak-...`.
A demo archive only goes into the demo database, and the reverse is refused as well.
"""

import contextlib
import io
import json
import os
import shutil
import warnings
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Connection, Engine, MetaData, Table, func, select, text
from sqlalchemy.exc import SAWarning, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.engine import create_db_engine
from app.db.migrate import head_revision
from app.db.taxonomy import sync_taxonomy
from app.demo.seed import user_data_tables
from app.services import backup_format as fmt
from app.services.backup import BackupError
from app.services.backup_verify import verify_archive

BATCH = 500
SIDE_SUFFIXES = ("-wal", "-shm")
LOCKED = (
    "A file is in use by another program ({detail}). Stop the app (Ctrl+C in its window), close "
    "anything that plays a recording, and run the command again. Nothing has changed."
)


@dataclass(frozen=True)
class RestoreResult:
    manifest: dict[str, Any]
    rows: int
    audio_files: int
    upgraded_from: str | None  # the archive's revision when it was older than head
    db_backup: Path | None
    audio_backup: Path | None


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _side_files(path: Path) -> list[Path]:
    return [path.with_name(path.name + suffix) for suffix in SIDE_SUFFIXES]


def _remove_file(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _remove_tree(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _remove_database(path: Path) -> None:
    for candidate in (path, *_side_files(path)):
        _remove_file(candidate)


def _has_files(folder: Path) -> bool:
    return folder.is_dir() and any(p.is_file() for p in folder.rglob("*"))


def _target_has_data(db_file: Path) -> bool:
    if not db_file.exists():
        return False
    engine = create_db_engine(_sqlite_url(db_file))
    try:
        return bool(user_data_tables(engine))
    except SQLAlchemyError as exc:
        raise BackupError(
            "target_unreadable", f"The target database {db_file} cannot be read ({exc})."
        ) from None
    finally:
        engine.dispose()


def _lines(archive: zipfile.ZipFile, table: str) -> Iterator[dict[str, Any]]:
    with archive.open(fmt.table_member(table)) as member:
        for line in io.TextIOWrapper(member, encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise BackupError("invalid_row", f"A row of {table} is not an object.")
                yield row


def _insert_table(connection: Connection, table: Table, rows: Iterator[dict[str, Any]]) -> int:
    """Insert `rows` with their original keys; returns how many. Core `insert` with explicit
    values: no Python default (`created_at`) and no `onupdate` ever runs."""
    kinds = {column.name: fmt.column_kind(column.type) for column in table.columns}
    batch: list[dict[str, Any]] = []
    count = 0
    for row in rows:
        if set(row) != set(kinds):
            raise BackupError(
                "column_mismatch", f"The columns of {table.name} do not match the schema."
            )
        batch.append({name: fmt.decode_to_bind(kinds[name], value) for name, value in row.items()})
        count += 1
        if len(batch) >= BATCH:
            connection.execute(table.insert(), batch)
            batch = []
    if batch:
        connection.execute(table.insert(), batch)
    return count


def _reflect(engine: Engine) -> MetaData:
    metadata = MetaData()
    metadata.reflect(engine)
    metadata.remove(metadata.tables["alembic_version"])
    for table in metadata.tables.values():
        for column in table.columns:
            if fmt.column_kind(column.type) == "json":
                column.type = JSON(none_as_null=True)  # null in the archive is a SQL NULL
    return metadata


def _ordered(metadata: MetaData) -> list[Table]:
    """Parents before children where the foreign keys allow it. The cycles of the schema (card,
    review_log...) have no valid order: the deferred check of `_fill` covers them."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SAWarning)
        return list(metadata.sorted_tables)


def _fill(engine: Engine, archive: zipfile.ZipFile, manifest: dict[str, Any]) -> None:
    counts: dict[str, int] = manifest["tables"]
    metadata = _reflect(engine)
    unknown = set(counts) - set(metadata.tables)
    if unknown:
        raise BackupError(
            "unknown_table",
            f"The archive has tables this schema lacks: {', '.join(sorted(unknown))}.",
        )
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN")
        connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
        try:
            for table in _ordered(metadata):
                if table.name in counts:
                    _insert_table(connection, table, _lines(archive, table.name))
            for table in _ordered(metadata):
                found = connection.execute(select(func.count()).select_from(table)).scalar_one()
                if found != counts.get(table.name, 0):
                    raise BackupError(
                        "count_mismatch",
                        f"{table.name}: {found} rows restored, the manifest says "
                        f"{counts.get(table.name, 0)}.",
                    )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _final_checks(engine: Engine) -> None:
    with engine.connect() as connection:
        integrity = connection.execute(text("PRAGMA integrity_check")).scalars().all()
        if integrity != ["ok"]:
            raise BackupError("integrity_check_failed", f"integrity_check: {integrity[:3]}")
        broken = connection.execute(text("PRAGMA foreign_key_check")).all()
        if broken:
            raise BackupError(
                "foreign_key_check_failed", f"{len(broken)} rows refer to a missing row."
            )
        connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))


def build_database(archive: zipfile.ZipFile, manifest: dict[str, Any], temporary: Path) -> None:
    """Schema at the manifest's revision, the rows, then head and the taxonomy; checked."""
    url = _sqlite_url(temporary)
    migrate.upgrade(url, manifest["alembic_revision"])
    engine = create_db_engine(url)
    try:
        _fill(engine, archive, manifest)
    finally:
        engine.dispose()
    migrate.upgrade(url, "head")
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            sync_taxonomy(session)
            session.commit()
        _final_checks(engine)
    finally:
        engine.dispose()
    for side in _side_files(temporary):
        _remove_file(side)


def extract_audio(archive: zipfile.ZipFile, manifest: dict[str, Any], folder: Path) -> int:
    count = 0
    for name in manifest["files"]:
        if not name.startswith("audio/"):
            continue
        destination = folder / name.removeprefix("audio/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        count += 1
    return count


def _checkpoint(db_file: Path) -> None:
    """Fold the write-ahead log into the file, so the old database is whole on its own."""
    engine = create_db_engine(_sqlite_url(db_file))
    try:
        with engine.connect() as connection:
            connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except SQLAlchemyError:
        pass
    finally:
        engine.dispose()


def swap_in(
    *,
    db_temporary: Path,
    db_file: Path,
    audio_temporary: Path,
    audio_dir: Path,
    keep_old: bool,
    stamp: str,
) -> tuple[Path | None, Path | None]:
    """Put the new database and recordings in place, or leave everything as it was.

    Returns the paths of the old database and recordings when they were kept. The old recordings
    are set aside first (D-188); every step that succeeded is undone if a later one fails."""
    undo: list[Callable[[], None]] = []
    db_backup = db_file.with_name(f"{db_file.name}.bak-{stamp}")
    audio_backup = audio_dir.with_name(f"{audio_dir.name}.bak-{stamp}")
    kept_audio: Path | None = None
    try:
        if audio_dir.exists():
            if _has_files(audio_dir):
                os.replace(audio_dir, audio_backup)
                undo.append(lambda: os.replace(audio_backup, audio_dir))
                kept_audio = audio_backup
            else:
                shutil.rmtree(audio_dir)
        had_database = db_file.exists()
        if had_database:
            _checkpoint(db_file)
            os.replace(db_file, db_backup)
            undo.append(lambda: os.replace(db_backup, db_file))
            for side in _side_files(db_file):
                if side.exists():
                    target = db_backup.with_name(db_backup.name + side.name[len(db_file.name) :])
                    os.replace(side, target)
                    undo.append(lambda s=side, t=target: os.replace(t, s))  # type: ignore[misc]
        os.replace(db_temporary, db_file)
        undo.append(lambda: os.replace(db_file, db_temporary))
        if audio_temporary.exists():
            os.replace(audio_temporary, audio_dir)
    except BaseException as exc:
        for step in reversed(undo):
            with contextlib.suppress(OSError):
                step()
        if isinstance(exc, PermissionError):
            raise BackupError("file_locked", LOCKED.format(detail=exc)) from exc
        raise
    if had_database and not keep_old:
        _remove_database(db_backup)
        return None, kept_audio
    return (db_backup if had_database else None), kept_audio


def restore_backup(
    archive_path: Path,
    *,
    db_file: Path,
    audio_dir: Path,
    demo: bool,
    replace: bool = False,
    now: datetime | None = None,
) -> RestoreResult:
    """Restore the archive into `db_file` and `audio_dir`; BackupError means nothing changed."""
    manifest = verify_archive(archive_path)
    if manifest["demo"] != demo:
        raise BackupError(
            "demo_mismatch",
            "This is a demo backup and the target is your personal database."
            if manifest["demo"]
            else "This is a backup of your personal data and the target is the demo database.",
        )
    has_data = _target_has_data(db_file)
    if (has_data or _has_files(audio_dir)) and not replace:
        raise BackupError(
            "target_not_empty",
            "The target already holds data. Nothing was changed. To replace it (the old data is "
            "kept as *.bak-...), add --replace --yes.",
        )
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_temporary = db_file.with_name(f"{db_file.name}.tmp-{os.getpid()}")
    audio_temporary = audio_dir.with_name(f"{audio_dir.name}.tmp-{os.getpid()}")
    _remove_database(db_temporary)
    _remove_tree(audio_temporary)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005 (local time)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            build_database(archive, manifest, db_temporary)
            audio_files = extract_audio(archive, manifest, audio_temporary)
        db_backup, audio_backup = swap_in(
            db_temporary=db_temporary,
            db_file=db_file,
            audio_temporary=audio_temporary,
            audio_dir=audio_dir,
            keep_old=has_data or _has_files(audio_dir),
            stamp=stamp,
        )
    finally:
        _remove_database(db_temporary)
        _remove_tree(audio_temporary)
    head = head_revision()
    return RestoreResult(
        manifest=manifest,
        rows=sum(manifest["tables"].values()),
        audio_files=audio_files,
        upgraded_from=manifest["alembic_revision"]
        if manifest["alembic_revision"] != head
        else None,
        db_backup=db_backup,
        audio_backup=audio_backup,
    )
