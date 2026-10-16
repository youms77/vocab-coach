"""The `ai_provider_order` setting and list-valued settings in general."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventLog, Setting
from app.db.settings_store import get_all_settings, get_setting, set_setting
from app.domain.settings_defaults import SETTINGS, SettingError, default_for


def test_default_order_is_gemini_groq_ollama(session: Session) -> None:
    assert get_setting(session, "ai_provider_order") == ["gemini", "groq", "ollama"]
    assert get_all_settings(session)["ai_provider_order"] == ["gemini", "groq", "ollama"]


def test_the_default_cannot_be_changed_through_a_returned_value(session: Session) -> None:
    get_setting(session, "ai_provider_order").append("evil")
    default_for("ai_provider_order").append("evil")
    get_all_settings(session)["ai_provider_order"].append("evil")
    assert get_setting(session, "ai_provider_order") == ["gemini", "groq", "ollama"]
    assert SETTINGS["ai_provider_order"].default == ["gemini", "groq", "ollama"]


def test_a_new_order_is_stored_and_logged(session: Session) -> None:
    set_setting(session, "ai_provider_order", ["groq", "gemini"])
    session.commit()

    assert get_setting(session, "ai_provider_order") == ["groq", "gemini"]
    event = session.scalars(select(EventLog)).one()
    assert event.event_type == "setting.changed"
    assert event.payload == {
        "key": "ai_provider_order",
        "old_value": ["gemini", "groq", "ollama"],
        "new_value": ["groq", "gemini"],
    }


def test_an_empty_list_turns_ai_off_and_is_stored(session: Session) -> None:
    set_setting(session, "ai_provider_order", [])
    session.commit()
    assert get_setting(session, "ai_provider_order") == []
    assert session.get(Setting, "ai_provider_order") is not None


def test_writing_back_the_default_removes_the_override(session: Session) -> None:
    set_setting(session, "ai_provider_order", ["groq"])
    set_setting(session, "ai_provider_order", ["gemini", "groq", "ollama"])
    session.commit()
    assert session.get(Setting, "ai_provider_order") is None


@pytest.mark.parametrize(
    "value",
    [
        ["gemini", "openai"],  # unknown name
        ["gemini", "gemini"],  # duplicate
        "gemini",  # not a list
        ("gemini",),  # a tuple is not a JSON list
        [1],  # not names
        None,
    ],
)
def test_invalid_orders_are_refused(session: Session, value: object) -> None:
    with pytest.raises(SettingError):
        set_setting(session, "ai_provider_order", value)
    assert session.get(Setting, "ai_provider_order") is None
    assert session.scalars(select(EventLog)).first() is None
