import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import EventLog, Setting
from app.db.settings_store import get_all_settings, get_setting, set_setting
from app.domain.settings_defaults import SETTINGS, SettingError, spec_for


def test_defaults_are_returned_without_rows(session: Session) -> None:
    assert session.scalar(select(func.count()).select_from(Setting)) == 0
    assert get_setting(session, "daily_time_budget_minutes") == 45
    assert get_setting(session, "target_retention") == 0.90
    assert get_setting(session, "timezone") == "Africa/Douala"
    assert get_all_settings(session) == {key: spec.default for key, spec in SETTINGS.items()}


def test_changed_value_is_stored_and_logged(session: Session) -> None:
    set_setting(session, "new_items_per_day", 20)
    session.commit()

    assert get_setting(session, "new_items_per_day") == 20
    event = session.scalars(select(EventLog)).one()
    assert event.event_type == "setting.changed"
    assert event.payload == {"key": "new_items_per_day", "old_value": 12, "new_value": 20}


def test_back_to_default_removes_the_row(session: Session) -> None:
    set_setting(session, "new_items_per_day", 20)
    set_setting(session, "new_items_per_day", 12)
    session.commit()
    assert session.get(Setting, "new_items_per_day") is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("daily_time_budget_minutes", 5),
        ("daily_time_budget_minutes", 241),
        ("new_items_per_day", -1),
        ("target_retention", 0.99),
        ("target_retention", 0.5),
        ("day_start_hour", 24),
        ("new_items_per_day", "12"),
        ("new_items_per_day", True),
        ("timezone", "Mars/Olympus_Mons"),
        ("ui_language", "de"),
    ],
)
def test_invalid_values_are_refused(session: Session, key: str, value: object) -> None:
    with pytest.raises(SettingError):
        set_setting(session, key, value)
    assert session.get(Setting, key) is None


def test_unknown_key_is_refused(session: Session) -> None:
    with pytest.raises(SettingError, match="unknown setting"):
        get_setting(session, "gemini_api_key")


def test_integer_is_accepted_for_float_setting() -> None:
    assert spec_for("tts_rate").validate(1) == 1.0
