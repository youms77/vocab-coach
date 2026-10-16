"""`/api/settings` end to end."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventLog, Setting
from app.domain.settings_defaults import SETTINGS
from tests.api.conftest import ApiEnv


def code(response) -> str:  # noqa: ANN001
    return response.json()["detail"]["code"]


def test_list_has_every_setting_with_its_description(env: ApiEnv) -> None:
    response = env.client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(SETTINGS)
    budget = body["daily_time_budget_minutes"]
    assert budget == {
        "value": 45,
        "default": 45,
        "is_default": True,
        "type": "int",
        "minimum": 10,
        "maximum": 240,
        "choices": None,
        "item_choices": None,
    }
    assert body["ui_language"]["choices"] == ["en", "fr"]
    order = body["ai_provider_order"]
    assert (order["type"], order["item_choices"]) == ("list", ["gemini", "groq", "ollama"])
    assert "_demo" not in body


def test_patch_changes_several_settings_and_returns_the_full_list(env: ApiEnv) -> None:
    response = env.client.patch(
        "/api/settings", json={"new_items_per_day": 20, "ui_language": "fr", "tts_rate": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(SETTINGS)
    assert (body["new_items_per_day"]["value"], body["new_items_per_day"]["is_default"]) == (
        20,
        False,
    )
    assert body["ui_language"]["value"] == "fr"
    assert env.client.get("/api/settings").json() == body
    with Session(env.engine) as session:
        changed = list(
            session.scalars(select(EventLog).where(EventLog.event_type == "setting.changed"))
        )
    assert {row.payload["key"] for row in changed} == {"new_items_per_day", "ui_language"}


def test_setting_back_to_the_default_is_default_again(env: ApiEnv) -> None:
    env.client.patch("/api/settings", json={"new_items_per_day": 20})
    body = env.client.patch("/api/settings", json={"new_items_per_day": 12}).json()
    assert body["new_items_per_day"]["is_default"] is True
    with Session(env.engine) as session:
        assert session.get(Setting, "new_items_per_day") is None


def test_one_invalid_value_cancels_the_whole_patch(env: ApiEnv) -> None:
    response = env.client.patch(
        "/api/settings", json={"new_items_per_day": 20, "daily_time_budget_minutes": 5}
    )
    assert (response.status_code, code(response)) == (422, "invalid_setting")
    assert response.json()["detail"]["key"] == "daily_time_budget_minutes"
    body = env.client.get("/api/settings").json()
    assert body["new_items_per_day"]["value"] == 12
    with Session(env.engine) as session:
        assert (
            session.scalars(
                select(EventLog).where(EventLog.event_type == "setting.changed")
            ).first()
            is None
        )


def test_out_of_bounds_wrong_type_and_unknown_choices_are_422(env: ApiEnv) -> None:
    for payload in (
        {"daily_time_budget_minutes": 1000},
        {"target_retention": 0.5},
        {"new_items_per_day": "twelve"},
        {"new_items_per_day": True},
        {"ui_language": "de"},
        {"timezone": "Mars/Olympus"},
        {"ai_provider_order": ["gemini", "gemini"]},
        {"ai_provider_order": ["gemini", "openai"]},
        {"ai_provider_order": "gemini"},
    ):
        response = env.client.patch("/api/settings", json=payload)
        assert (response.status_code, code(response)) == (422, "invalid_setting"), payload
        assert response.json()["detail"]["key"] == next(iter(payload))


def test_unknown_and_reserved_keys_are_refused(env: ApiEnv) -> None:
    for key in ("nope", "_demo", "VOCAB_GEMINI_API_KEY", "gemini_api_key"):
        response = env.client.patch("/api/settings", json={key: "x"})
        assert (response.status_code, code(response)) == (422, "invalid_setting"), key


def test_body_must_be_a_json_object(env: ApiEnv) -> None:
    for body in (["a"], "text", 3):
        response = env.client.patch("/api/settings", json=body)
        assert (response.status_code, code(response)) == (422, "invalid_request")


def test_empty_provider_order_turns_ai_off(env: ApiEnv) -> None:
    body = env.client.patch("/api/settings", json={"ai_provider_order": []}).json()
    assert body["ai_provider_order"]["value"] == []
    assert env.client.get("/api/ai/status").json()["ai_off"] is True


def test_empty_patch_is_a_no_op(env: ApiEnv) -> None:
    response = env.client.patch("/api/settings", json={})
    assert response.status_code == 200 and set(response.json()) == set(SETTINGS)


def test_settings_are_protected_like_the_rest_of_the_api(env: ApiEnv) -> None:
    assert (
        env.client.patch(
            "/api/settings", json={"new_items_per_day": 20}, headers={"Origin": "https://x.example"}
        ).status_code
        == 403
    )
    assert (
        env.client.patch(
            "/api/settings",
            content=b'{"new_items_per_day": 20}',
            headers={"Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    assert env.client.get("/api/settings").json()["new_items_per_day"]["value"] == 12
