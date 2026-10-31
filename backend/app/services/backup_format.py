"""The `vocab-coach-backup-1` archive format: names, limits and how values are encoded (D-302).

An archive is a zip with `manifest.json`, `tables/<table>.jsonl` (one JSON object per row, columns
in the model's order, rows sorted by primary key) and `audio/YYYY/MM/<hex32>.<ext>` (the recordings
that a row refers to). Values are encoded so that they read back exactly:

- instants `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC), dates `YYYY-MM-DD`;
- JSON columns as native JSON (never a string);
- enumerations by their value, booleans as JSON booleans, null as `null`.

Pure: no database, no file. Reading and writing live in `backup.py` and `backup_restore.py`.
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime
from sqlalchemy.types import TypeDecorator, TypeEngine

FORMAT = "vocab-coach-backup-1"

# A zip declares its sizes in its own headers, which a hostile archive can falsify: the limit is
# enforced on the bytes actually read. 2 GiB is far above a real backup (the database of a daily
# learner is a few tens of MB, and a recording is at most 10 MB, D-169) and far below what would
# fill the disk of a laptop.
MAX_UNCOMPRESSED_BYTES = 2 * 1024**3
# The manifest lists every file and every missing recording: a few MB at most.
MAX_MANIFEST_BYTES = 16 * 1024**2

MANIFEST = "manifest.json"
TABLE_MEMBER = re.compile(r"tables/([a-z][a-z0-9_]*)\.jsonl")
BACKUP_FILE_NAME = re.compile(r"vocab-coach-backup-\d{8}-\d{6}\.zip")

# A JSON column can hold a SQL NULL (attribute never set) or the JSON value `null` (attribute set to
# None): the ORM writes both. The first is `null` in the archive, the second this marker, so that
# the restored file is identical to the original, not only equal once read through the ORM.
JSON_NULL = {"$json": "null"}

INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def table_member(table: str) -> str:
    return f"tables/{table}.jsonl"


def audio_member(stored_path: str) -> str:
    return f"audio/{stored_path}"


def backup_file_name(now: datetime, tz: Any) -> str:
    """`vocab-coach-backup-YYYYMMDD-HHMMSS.zip`, in the local time of the `timezone` setting."""
    return f"vocab-coach-backup-{now.astimezone(tz):%Y%m%d-%H%M%S}.zip"


def is_backup_file_name(name: str) -> bool:
    """Exactly the application's naming pattern (rotation touches nothing else)."""
    return BACKUP_FILE_NAME.fullmatch(name) is not None


def column_kind(column_type: TypeEngine[Any]) -> str:
    """How a column's value is encoded: `datetime`, `date`, `json`, `bool` or `raw`."""
    if isinstance(column_type, TypeDecorator):
        column_type = column_type.impl
    if isinstance(column_type, DateTime):
        return "datetime"
    if isinstance(column_type, Date):
        return "date"
    if isinstance(column_type, JSON):
        return "json"
    if isinstance(column_type, Boolean):
        return "bool"
    return "raw"


def encode_stored(kind: str, raw: Any) -> Any:
    """A value as SQLite stores it (read with plain SQL) -> the JSON value of the archive."""
    if raw is None:
        return None
    if kind == "datetime":
        parsed = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed.strftime(INSTANT_FORMAT)
    if kind == "json":
        if raw == "null":
            return JSON_NULL
        return json.loads(raw) if isinstance(raw, str | bytes) else raw
    if kind == "bool":
        return bool(raw)
    return raw


def decode_to_bind(kind: str, value: Any) -> Any:
    """A JSON value of the archive -> the Python value to bind (naive UTC for an instant)."""
    if value is None:
        return None
    if kind == "datetime":
        return datetime.strptime(value, INSTANT_FORMAT)
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "json" and value == JSON_NULL:
        return JSON.NULL
    return value
