"""Demo marker: a reserved row of the `setting` table that says "this database is demo data".

The key starts with `_` and is not in the settings registry, so `get_setting` / `set_setting`
refuse it, `get_all_settings` skips it, and it never produces a `setting.changed` event (D-017).
Only `demo seed` writes it (D-033).
"""

from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from app.db.models import Setting

DEMO_MARKER_KEY = "_demo"


class DemoMarker(BaseModel):
    dataset_version: int
    seed: int
    days: int
    anchor: date


def read_demo_marker(session: Session) -> DemoMarker | None:
    row = session.get(Setting, DEMO_MARKER_KEY)
    return None if row is None else DemoMarker.model_validate(row.value)


def write_demo_marker(session: Session, marker: DemoMarker) -> None:
    """Add or replace the marker; the caller commits."""
    value: dict[str, Any] = marker.model_dump(mode="json")
    row = session.get(Setting, DEMO_MARKER_KEY)
    if row is None:
        session.add(Setting(key=DEMO_MARKER_KEY, value=value))
    else:
        row.value = value
    session.flush()


def has_demo_marker(engine: Engine) -> bool:
    """True when the database has the marker. False for an empty or unmigrated database."""
    if not inspect(engine).has_table(Setting.__tablename__):
        return False
    with Session(engine) as session:
        return session.get(Setting, DEMO_MARKER_KEY) is not None
