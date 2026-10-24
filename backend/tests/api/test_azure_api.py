"""Azure Speech in the AI and settings endpoints (M6.c1, D-214): credential with a region, status,
the `pronunciation_assessment` setting, the demo guard, the connection test and usage."""

import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.demo_marker import DemoMarker, write_demo_marker
from app.db.models import AICallLog, EventLog
from tests.ai.fake_server import Reply, fixture_reply
from tests.api.conftest import ApiEnv

AZURE_KEY = "az0123456789abcdef0123456789abcd"
KEY_VAR = "VOCAB_AZURE_SPEECH_KEY"
REGION_VAR = "VOCAB_AZURE_SPEECH_REGION"


def put_azure(env: ApiEnv, value: str = AZURE_KEY, **extra: object):
    return env.client.put("/api/ai/providers/azure/credential", json={"value": value, **extra})


def azure_state(env: ApiEnv) -> dict:
    [state] = env.client.get("/api/ai/status").json()["speech_providers"]
    return state


# --- Status ----------------------------------------------------------------------------------


def test_status_lists_azure_apart_and_leaves_the_providers_unchanged(env: ApiEnv) -> None:
    body = env.client.get("/api/ai/status").json()
    assert [p["name"] for p in body["providers"]] == ["gemini", "groq", "ollama"]
    assert body["order"] == ["gemini", "groq", "ollama"]
    azure = azure_state(env)
    assert azure["name"] == "azure" and azure["capabilities"] == ["pronunciation_assessment"]
    assert azure["configured"] is False and azure["region"] is None
    assert azure["credential_source"] == "none"
    assert azure["models"] == {"pronunciation_assessment": "pa-rest-v1"}
    assert all(p["region"] is None for p in body["providers"])


def test_azure_alone_does_not_end_the_degraded_mode(env: ApiEnv) -> None:
    assert put_azure(env, region="westeurope").status_code == 200
    body = env.client.get("/api/ai/status").json()
    assert body["degraded"] is True  # no text provider: usage sheets stay unavailable
    assert azure_state(env)["available"] is True


# --- Credential ------------------------------------------------------------------------------


def test_put_writes_key_and_region_and_the_status_shows_the_region_not_the_key(
    env: ApiEnv,
) -> None:
    response = put_azure(env, region="WestEurope")
    assert response.status_code == 200
    state = response.json()
    assert (state["name"], state["configured"], state["region"]) == ("azure", True, "westeurope")
    assert state["credential_source"] == "env_file" and state["credential_kind"] == "api_key"
    text = env.env_text()
    assert f"{KEY_VAR}={AZURE_KEY}" in text and f"{REGION_VAR}=westeurope" in text
    assert AZURE_KEY not in response.text and AZURE_KEY not in env.client.get("/api/ai/status").text
    assert azure_state(env)["region"] == "westeurope"


def test_a_key_without_region_is_refused_when_none_is_stored(env: ApiEnv) -> None:
    response = put_azure(env)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "region_required")
    assert not env.env_path.exists()


def test_a_key_alone_is_accepted_when_a_region_is_stored(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    assert put_azure(env, AZURE_KEY + "2").status_code == 200
    assert f"{REGION_VAR}=westeurope" in env.env_text()
    assert f"{KEY_VAR}={AZURE_KEY}2" in env.env_text()


@pytest.mark.parametrize("region", ["", "a", "west europe", "x" * 41, "eu/1"])
def test_an_invalid_region_is_a_422(env: ApiEnv, region: str) -> None:
    response = put_azure(env, region=region)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "invalid_region")
    assert AZURE_KEY not in response.text and not env.env_path.exists()


def test_a_region_is_refused_for_other_providers(env: ApiEnv) -> None:
    response = env.client.put(
        "/api/ai/providers/gemini/credential",
        json={"value": "AIzaSyTest_0123456789abcdefghij", "region": "westeurope"},
    )
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "invalid_request")
    assert not env.env_path.exists()


def test_delete_clears_both_variables(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    response = env.client.delete("/api/ai/providers/azure/credential")
    assert response.status_code == 200
    state = response.json()
    assert (state["configured"], state["region"]) == (False, None)
    text = env.env_text()
    assert AZURE_KEY not in text and "westeurope" not in text


@pytest.mark.parametrize("variable", [KEY_VAR, REGION_VAR])
def test_either_variable_in_the_environment_is_a_409(
    env: ApiEnv, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "")
    for response in (
        put_azure(env, region="westeurope"),
        env.client.delete("/api/ai/providers/azure/credential"),
    ):
        assert (response.status_code, response.json()["detail"]["code"]) == (
            409,
            "set_in_environment",
        )
    assert not env.env_path.exists()
    assert azure_state(env)["credential_source"] == "environment"


def test_credential_events_name_the_provider_and_hold_no_secret(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    put_azure(env, region="westeurope")  # no change, no event
    env.client.delete("/api/ai/providers/azure/credential")
    with Session(env.engine) as session:
        rows = list(
            session.scalars(select(EventLog).where(EventLog.event_type == "ai.credential_changed"))
        )
    assert [r.payload for r in rows] == [
        {"provider": "azure", "action": "set"},
        {"provider": "azure", "action": "removed"},
    ]


# --- The setting -----------------------------------------------------------------------------


def test_the_setting_is_off_by_default_and_takes_off_or_azure(env: ApiEnv) -> None:
    info = env.client.get("/api/settings").json()["pronunciation_assessment"]
    assert (info["value"], info["default"], info["choices"]) == ("off", "off", ["off", "azure"])
    assert (
        env.client.patch("/api/settings", json={"pronunciation_assessment": "azure"}).status_code
        == 200
    )
    assert env.client.get("/api/settings").json()["pronunciation_assessment"]["value"] == "azure"
    for bad in ("on", "gemini", "", 1, None):
        response = env.client.patch("/api/settings", json={"pronunciation_assessment": bad})
        assert (response.status_code, response.json()["detail"]["code"]) == (
            422,
            "invalid_setting",
        )
    assert env.client.get("/api/settings").json()["pronunciation_assessment"]["value"] == "azure"


def test_the_demo_database_refuses_the_setting_but_not_the_others(env: ApiEnv) -> None:
    with Session(env.engine) as session:
        write_demo_marker(
            session,
            DemoMarker(
                dataset_version=1, seed=1, days=10, anchor=datetime(2026, 9, 1, tzinfo=UTC).date()
            ),
        )
        session.commit()
    for response in (
        env.client.patch("/api/settings", json={"pronunciation_assessment": "azure"}),
        put_azure(env, region="westeurope"),
        env.client.delete("/api/ai/providers/azure/credential"),
        env.client.post("/api/ai/test", json={"provider": "azure"}),
    ):
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "demo_read_only")
    assert not env.env_path.exists()
    assert env.client.patch("/api/settings", json={"new_items_per_day": 15}).status_code == 200
    assert env.servers["azure"].requests == []


# --- The connection test ---------------------------------------------------------------------


def test_the_connection_test_sends_one_second_of_silence(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    env.servers["azure"].script = [fixture_reply("azure", "nomatch")]
    response = env.client.post("/api/ai/test", json={"provider": "azure"})
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["provider"], body["model"]) == ("ok", "azure", "pa-rest-v1")
    assert body["error_code"] is None and body["input_tokens"] is None
    [received] = env.servers["azure"].requests
    assert received.headers["content-type"].startswith("audio/wav")
    assert len(received.body) == 44 + 32000  # a header and one second of 16 kHz 16-bit mono
    assert AZURE_KEY not in response.text


def test_the_connection_test_of_an_unconfigured_azure_makes_no_request(env: ApiEnv) -> None:
    body = env.client.post("/api/ai/test", json={"provider": "azure"}).json()
    assert (body["status"], body["reason"]) == ("unavailable", "no_provider_configured")
    assert env.servers["azure"].requests == []


def test_a_rejected_key_is_reported_as_auth(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    env.servers["azure"].script = [fixture_reply("azure", "error_401", status=401)]
    body = env.client.post("/api/ai/test", json={"provider": "azure"}).json()
    assert (body["status"], body["reason"], body["error_code"]) == ("unavailable", "auth", "auth")
    assert body["http_status"] == 401 and AZURE_KEY not in str(body)
    assert azure_state(env)["misconfigured"] is True


def test_the_test_is_journalled_and_azure_shows_in_the_usage(env: ApiEnv) -> None:
    put_azure(env, region="westeurope")
    env.client.post("/api/ai/test", json={"provider": "azure"})
    with Session(env.engine) as session:
        [row] = session.scalars(select(AICallLog))
    assert (row.provider, row.task, row.model, row.success) == (
        "azure",
        "pronunciation_assessment",
        "pa-rest-v1",
        True,
    )
    today = env.client.get("/api/ai/usage").json()["days"][0]
    assert [(r["provider"], r["requests"], r["successes"]) for r in today["rows"]] == [
        ("azure", 1, 1)
    ]


def test_a_hostile_azure_never_leaks_the_key(env: ApiEnv, caplog: pytest.LogCaptureFixture) -> None:
    put_azure(env, region="westeurope")
    env.servers["azure"].script = [
        Reply(status=403, body={"error": {"message": f"key {AZURE_KEY} is not allowed"}})
    ]
    caplog.set_level(logging.DEBUG)
    response = env.client.post("/api/ai/test", json={"provider": "azure"})
    assert AZURE_KEY not in response.text and AZURE_KEY not in caplog.text
    with Session(env.engine) as session:
        for row in session.scalars(select(AICallLog)):
            assert AZURE_KEY not in (row.error_message or "")
        for event in session.scalars(select(EventLog)):
            assert AZURE_KEY not in str(event.payload)
    assert AZURE_KEY not in env.client.get("/openapi.json").text
