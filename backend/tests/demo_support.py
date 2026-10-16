"""Helpers shared by the demo tests."""

import hashlib
import json
from datetime import date

from sqlalchemy import Engine, select

from app.db.base import Base

DEMO_ANCHOR = date(2026, 9, 1)
DEMO_SEED = 42

# Columns filled by the real clock (row insert or update time): they differ between two runs and
# are left out of the fingerprint. Every business date (occurred_at, reviewed_at, due...) is in.
CLOCK_COLUMNS = frozenset({"created_at", "updated_at", "recorded_at"})


def fingerprint(engine: Engine) -> str:
    """SHA-256 of every table, rows sorted by primary key, real-clock columns excluded."""
    digest = hashlib.sha256()
    with engine.connect() as connection:
        for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
            columns = [c for c in table.columns if c.name not in CLOCK_COLUMNS]
            query = select(*columns).order_by(*table.primary_key.columns)
            digest.update(table.name.encode())
            for row in connection.execute(query):
                digest.update(json.dumps(list(row), default=str, sort_keys=True).encode())
    return digest.hexdigest()
