"""CSV export of the event tables, for analysis in pandas (module I, M9.a).

A zip archive holds one CSV per table, `manifest.json` and `data_dictionary.md`. Every table is read
in **one read transaction**, so the counts of the manifest match the files even while the app runs.

Format (D-271): UTF-8 without BOM, comma, the `csv` module (RFC 4180 quoting, line breaks inside a
field kept); header = column names; instants in ISO 8601 UTC with `Z` and microseconds; dates
YYYY-MM-DD; JSON columns as compact JSON text; booleans `true` / `false`; null = empty field; one
`study_day` column (last) for the table's main timestamp. No audio (M10), no `setting` table, no
environment variable.
"""

import csv
import io
import json
import os
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import IO, Any

from sqlalchemy import Engine, Table, select
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.base import Base
from app.services.export_dictionary import STUDY_DAY, TABLES
from app.services.stats import Context, context, read_only

FORMAT = "vocab-coach-csv-1"

# Event tables first, then the tables useful for joins. `setting` is never exported.
EXPORT_TABLES: tuple[str, ...] = (
    "event_log",
    "review_log",
    "error_event",
    "production_attempt",
    "production_target",
    "pronunciation_result",
    "study_session",
    "ai_call_log",
    "lexical_item",
    "card",
    "deck",
    "deck_item",
    "error_category",
    "consolidation_task",
    "consolidation_task_item",
    "curriculum_track",
    "curriculum_unit",
)

# The timestamp that gets a `study_day` column.
MAIN_TIMESTAMP: dict[str, str] = {
    "event_log": "occurred_at",
    "review_log": "reviewed_at",
    "error_event": "occurred_at",
    "production_attempt": "created_at",
    "pronunciation_result": "created_at",
    "study_session": "started_at",
    "ai_call_log": "started_at",
    "lexical_item": "created_at",
    "card": "created_at",
    "deck": "created_at",
    "deck_item": "added_at",
    "consolidation_task": "created_at",
    "curriculum_track": "created_at",
    "curriculum_unit": "created_at",
}


class UnknownTable(LookupError):
    pass


def table_of(name: str) -> Table:
    if name not in EXPORT_TABLES:
        raise UnknownTable(name)
    return Base.metadata.tables[name]


def columns(name: str) -> list[str]:
    """Header of a table's CSV."""
    names = [column.name for column in table_of(name).columns]
    return names + (["study_day"] if name in MAIN_TIMESTAMP else [])


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _rows(session: Session, name: str, ctx: Context) -> Iterator[list[str]]:
    table = table_of(name)
    main = MAIN_TIMESTAMP.get(name)
    order = list(table.primary_key.columns)
    for row in session.execute(select(table).order_by(*order)).mappings():
        values = [format_value(row[column.name]) for column in table.columns]
        if main is not None:
            instant = row[main]
            values.append(ctx.day_of(instant).isoformat() if instant is not None else "")
        yield values


def write_csv(session: Session, name: str, ctx: Context, stream: IO[str]) -> int:
    """Write one table; returns the number of data rows."""
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(columns(name))
    count = 0
    for values in _rows(session, name, ctx):
        writer.writerow(values)
        count += 1
    return count


def _snapshot(session: Session) -> None:
    """Start an explicit read transaction: every table is read from the same state."""
    dbapi = session.connection().connection.dbapi_connection
    if dbapi is not None and not dbapi.in_transaction:
        session.connection().exec_driver_sql("BEGIN")


def table_csv(engine: Engine, name: str, now: datetime) -> str:
    table_of(name)
    with read_only(engine) as session:
        _snapshot(session)
        stream = io.StringIO(newline="")
        write_csv(session, name, context(session, now), stream)
        return stream.getvalue()


def archive_name(day: date) -> str:
    return f"vocab-coach-export-{day:%Y%m%d}.zip"


@dataclass(frozen=True)
class ExportResult:
    path: Path
    study_day: date
    rows: dict[str, int]
    demo: bool


def data_dictionary(ctx: Context) -> str:
    lines = [
        "# vocab-coach CSV export: data dictionary",
        "",
        "One CSV per table, UTF-8 without BOM, comma-separated, RFC 4180 quoting (a field may hold "
        "line breaks). Instants are UTC in ISO 8601 with `Z`; `study_day` is the local study day "
        f"(timezone `{ctx.tz.key}`, day starts at {ctx.day_start_hour}:00). JSON columns hold "
        "compact JSON text, booleans are `true` / `false`, an empty field is null.",
        "",
        "```python",
        "import json",
        "import zipfile",
        "",
        "import pandas as pd",
        "",
        'archive = zipfile.ZipFile("vocab-coach-export-YYYYMMDD.zip")',
        "reviews = pd.read_csv(",
        '    archive.open("review_log.csv"),',
        '    parse_dates=["reviewed_at", "due_before", "due_after"],',
        ")",
        'reviews["study_day"] = pd.to_datetime(reviews["study_day"])',
        'events = pd.read_csv(archive.open("event_log.csv"), parse_dates=["occurred_at"])',
        'events["payload"] = events["payload"].map(json.loads)',
        "```",
        "",
    ]
    for name in EXPORT_TABLES:
        description, docs = TABLES[name]
        lines += [
            f"## {name}",
            "",
            description,
            "",
            "| Column | Type | Description |",
            "|---|---|---|",
        ]
        for column in table_of(name).columns:
            kind = type(column.type).__name__
            lines.append(f"| `{column.name}` | {kind} | {docs[column.name]} |")
        if name in MAIN_TIMESTAMP:
            lines.append(f"| `study_day` | date | {STUDY_DAY} (`{MAIN_TIMESTAMP[name]}`) |")
        lines.append("")
    return "\n".join(lines)


def write_archive(session: Session, ctx: Context, stream: IO[bytes]) -> dict[str, int]:
    """Write the zip into `stream` (the session must be read-only); returns rows per table."""
    _snapshot(session)
    rows: dict[str, int] = {}
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXPORT_TABLES:
            with archive.open(f"{name}.csv", "w") as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                rows[name] = write_csv(session, name, ctx, text)
                text.flush()
                text.detach()
        revision = migrate.schema_status(session.get_bind()).revision  # type: ignore[arg-type]
        manifest = {
            "format": FORMAT,
            "exported_at": format_value(ctx.now),
            "study_day": ctx.today.isoformat(),
            "timezone": ctx.tz.key,
            "day_start_hour": ctx.day_start_hour,
            "alembic_revision": revision,
            "demo": ctx.demo,
            "tables": rows,
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("data_dictionary.md", data_dictionary(ctx))
    return rows


def export_archive(
    engine: Engine, now: datetime, target: Path, *, force: bool = False
) -> ExportResult:
    """Write the archive to `target` atomically (a temporary file in the same folder, then
    `os.replace`). Refuses an existing file unless `force`."""
    if target.exists() and not force:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        with read_only(engine) as session:
            ctx = context(session, now)
            with temporary.open("wb") as stream:
                rows = write_archive(session, ctx, stream)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return ExportResult(target, ctx.today, rows, ctx.demo)
