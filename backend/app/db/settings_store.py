"""User settings: the `setting` table holds overrides, the registry holds the defaults."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Setting
from app.domain.events import SettingChanged
from app.domain.settings_defaults import SETTINGS, spec_for


def get_setting(session: Session, key: str) -> Any:
    """Stored value if the user changed it, else the default. SettingError on unknown keys."""
    spec = spec_for(key)
    row = session.get(Setting, key)
    return spec.default_value() if row is None else row.value


def get_all_settings(session: Session) -> dict[str, Any]:
    stored = {row.key: row.value for row in session.scalars(select(Setting)) if row.key in SETTINGS}
    return {key: stored.get(key, spec.default_value()) for key, spec in SETTINGS.items()}


def set_setting(session: Session, key: str, value: Any) -> Any:
    """Validate and store `value`, and log `setting.changed`. The caller commits.

    Setting a value equal to the default removes the override: the table only keeps changes.
    Raises SettingError (a ValueError) for an unknown key or an invalid value.
    """
    spec = spec_for(key)
    value = spec.validate(value)
    old_value = get_setting(session, key)
    if value == old_value:
        return value
    row = session.get(Setting, key)
    if value == spec.default:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    record_event(session, SettingChanged(key=key, old_value=old_value, new_value=value))
    session.flush()
    return value
