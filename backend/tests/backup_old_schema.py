"""Helpers of the backup tests: Settings without the environment, an archive made at `0001`."""

import json
from pathlib import Path

from sqlalchemy import MetaData

from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.services import backup_format as fmt
from tests.backup_support import sha, sqlite_url, write_members


def make_settings(tmp_path: Path, *, demo: bool = False, database: Path | None = None) -> Settings:
    """Settings independent of the process environment and of any `.env`."""
    kwargs: dict[str, object] = {"data_dir": tmp_path / "data", "demo": demo}
    if database is not None and not demo:
        kwargs["database_url"] = sqlite_url(database)
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def archive_at_revision_0001(work: Path) -> tuple[Path, list[str]]:
    """Build, by hand, the archive of a database that was at `0001`: upgrade a file to `0001`
    only, add a few rows, dump it through its own reflected tables. Returns (zip, terms)."""
    database = work / "old.sqlite3"
    url = sqlite_url(database)
    migrate.upgrade(url, "0001")
    engine = create_db_engine(url)
    stamp = "2026-08-01 09:00:00.000000"
    terms = ["shed light on", "at university"]
    try:
        with engine.begin() as connection:
            for index, term in enumerate(terms, start=1):
                connection.exec_driver_sql(
                    "INSERT INTO lexical_item (id, term, normalized_form, item_type, status, "
                    "status_changed_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'word', 'draft', ?, ?, ?)",
                    (index, term, term.lower(), stamp, stamp, stamp),
                )
            connection.exec_driver_sql(
                "INSERT INTO setting (key, value, updated_at) "
                "VALUES ('target_retention', '0.85', ?)",
                (stamp,),
            )
        metadata = MetaData()
        metadata.reflect(engine)
        members: dict[str, bytes] = {}
        counts: dict[str, int] = {}
        with engine.connect() as connection:
            for table in sorted(metadata.tables.values(), key=lambda t: t.name):
                if table.name == "alembic_version":
                    continue
                names = [c.name for c in table.columns]
                kinds = [fmt.column_kind(c.type) for c in table.columns]
                lines = []
                for raw in connection.exec_driver_sql(f'SELECT * FROM "{table.name}"'):  # noqa: S608
                    values = [fmt.encode_stored(k, v) for k, v in zip(kinds, raw, strict=True)]
                    lines.append(json.dumps(dict(zip(names, values, strict=True))))
                counts[table.name] = len(lines)
                text = "".join(line + "\n" for line in lines)
                members[fmt.table_member(table.name)] = text.encode()
    finally:
        engine.dispose()
    manifest = {
        "format": fmt.FORMAT,
        "created_at": "2026-08-01T09:00:00.000000Z",
        "app_version": "0.0.0",
        "alembic_revision": "0001",
        "study_day": "2026-08-01",
        "timezone": "Africa/Douala",
        "demo": False,
        "kind": "manual",
        "tables": counts,
        "files": {n: {"sha256": sha(d), "size": len(d)} for n, d in members.items()},
        "missing_audio": [],
    }
    target = work / "old-backup.zip"
    write_members(target, {**members, "manifest.json": json.dumps(manifest).encode()})
    return target, terms
