"""`/api/ai/*` end to end: real adapters over fake servers, the real app, a temporary `.env`.

The recurring check is the secret one: a known key must appear nowhere it should not (responses,
errors, OpenAPI, logs, event log, repr).
"""

import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.demo_marker import DemoMarker, write_demo_marker
from app.db.models import AICallLog, EventLog
from app.services import env_file
from tests.ai.fake_server import Reply, fixture_reply
from tests.api.conftest import ApiEnv

GEMINI_KEY = "AIzaSyTest_0123456789abcdefghij"
GROQ_KEY = "gsk_test_0123456789abcdefghij"
GEMINI_VAR = "VOCAB_GEMINI_API_KEY"


def provider(body: dict, name: str) -> dict:
    return next(p for p in body["providers"] if p["name"] == name)


def put_key(env: ApiEnv, name: str = "gemini", value: str = GEMINI_KEY):
    return env.client.put(f"/api/ai/providers/{name}/credential", json={"value": value})


def events(env: ApiEnv, event_type: str) -> list[EventLog]:
    with Session(env.engine) as session:
        return list(session.scalars(select(EventLog).where(EventLog.event_type == event_type)))


# --- Isolation guard -----------------------------------------------------------------------------


def test_the_env_file_in_use_is_in_the_temporary_folder(env: ApiEnv, tmp_path) -> None:
    assert Settings.model_config["env_file"] == env.env_path
    assert tmp_path in env.env_path.parents


# --- Status --------------------------------------------------------------------------------------


def test_status_without_any_credential(env: ApiEnv) -> None:
    response = env.client.get("/api/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert body["order"] == ["gemini", "groq", "ollama"]
    assert (body["ai_off"], body["degraded"], body["demo"]) == (False, True, False)
    assert [p["name"] for p in body["providers"]] == ["gemini", "groq", "ollama"]
    for item in body["providers"]:
        assert item["configured"] is False and item["available"] is False
        assert item["credential_source"] == "none"
    gemini, groq, ollama = (provider(body, n) for n in ("gemini", "groq", "ollama"))
    assert gemini["models"] == {"text": "gemini-3.5-flash-lite"}
    assert set(groq["models"]) == {"text", "transcription"}
    assert (gemini["credential_kind"], ollama["credential_kind"]) == ("api_key", "base_url")
    assert groq["capabilities"] == ["text", "transcription"]


def test_put_makes_the_provider_configured_without_a_restart(env: ApiEnv) -> None:
    assert put_key(env).status_code == 200
    body = env.client.get("/api/ai/status").json()
    gemini = provider(body, "gemini")
    assert (gemini["configured"], gemini["available"]) == (True, True)
    assert (gemini["credential_source"], body["degraded"]) == ("env_file", False)
    assert f"{GEMINI_VAR}={GEMINI_KEY}" in env.env_text()


def test_delete_makes_it_not_configured_again(env: ApiEnv) -> None:
    put_key(env)
    response = env.client.delete("/api/ai/providers/gemini/credential")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert provider(env.client.get("/api/ai/status").json(), "gemini")["configured"] is False
    assert GEMINI_KEY not in env.env_text()
    assert f"{GEMINI_VAR}=\n" in env.env_text() + "\n"


def test_put_ollama_address(env: ApiEnv) -> None:
    address = env.servers["ollama"].base_url
    response = put_key(env, "ollama", address + "/")
    assert response.status_code == 200
    state = response.json()
    assert (state["configured"], state["credential_kind"]) == (True, "base_url")
    assert address not in response.text and address not in env.client.get("/api/ai/status").text
    assert f"VOCAB_OLLAMA_BASE_URL={address}\n" in env.env_text()


def test_the_response_of_put_is_the_provider_state(env: ApiEnv) -> None:
    state = put_key(env, "groq", GROQ_KEY).json()
    assert state["name"] == "groq" and state["configured"] is True
    assert state["models"]["text"]


# --- Credential validation and errors ------------------------------------------------------------


def test_invalid_key_is_refused_and_not_echoed(env: ApiEnv) -> None:
    bad = "has a space inside 123456"
    response = put_key(env, value=bad)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_credential"
    assert bad not in response.text
    assert not env.env_path.exists()


def test_malformed_bodies_get_a_422_that_never_quotes_the_input(env: ApiEnv) -> None:
    secret = "tok-should-never-come-back-1234"  # noqa: S105
    for body in ({"value": 12345}, {"value": secret, "extra": secret}, {"other": secret}, [secret]):
        response = env.client.put("/api/ai/providers/gemini/credential", json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"]["code"] == "invalid_request"
        assert secret not in response.text and "input" not in response.json()["detail"]["errors"][0]
    assert not env.env_path.exists()


def test_a_field_error_carries_a_stable_type_next_to_the_english_message(env: ApiEnv) -> None:
    """The interface translates from `type` (M10.c1, D-324); `message` stays the English text."""
    response = env.client.put("/api/ai/providers/gemini/credential", json={"other": "x"})
    errors = response.json()["detail"]["errors"]
    assert response.status_code == 422
    assert {"loc": ["body", "value"], "type": "missing"}.items() <= errors[0].items()
    assert errors[0]["message"] == "Field required"


def test_unknown_provider_is_404(env: ApiEnv) -> None:
    for call in (
        lambda: env.client.put("/api/ai/providers/openai/credential", json={"value": GEMINI_KEY}),
        lambda: env.client.delete("/api/ai/providers/openai/credential"),
        lambda: env.client.post("/api/ai/test", json={"provider": "openai"}),
    ):
        response = call()
        assert (response.status_code, response.json()["detail"]["code"]) == (
            404,
            "unknown_provider",
        )
    assert not env.env_path.exists()


def test_environment_variable_blocks_the_edit(env: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    env.env_path.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setenv(GEMINI_VAR, "from-the-environment-12345")
    response = put_key(env)
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "set_in_environment")
    assert env.client.delete("/api/ai/providers/gemini/credential").status_code == 409
    assert env.env_text() == "A=1\n"
    gemini = provider(env.client.get("/api/ai/status").json(), "gemini")
    assert gemini["credential_source"] == "environment"


def test_locked_env_file_is_a_409(env: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    env.env_path.write_text("A=1\n", encoding="utf-8")

    def locked(*_args: object) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(env_file.os, "replace", locked)
    monkeypatch.setattr(env_file.time, "sleep", lambda _seconds: None)
    response = put_key(env)
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "env_file_locked")
    assert GEMINI_KEY not in response.text
    assert env.env_text() == "A=1\n"


def test_credential_events_carry_no_secret_and_only_real_changes(env: ApiEnv) -> None:
    put_key(env)
    put_key(env)  # identical: nothing written, no event
    env.client.delete("/api/ai/providers/gemini/credential")
    env.client.delete("/api/ai/providers/gemini/credential")  # nothing to remove
    rows = events(env, "ai.credential_changed")
    assert [row.payload for row in rows] == [
        {"provider": "gemini", "action": "set"},
        {"provider": "gemini", "action": "removed"},
    ]
    assert {row.entity_type for row in rows} == {"ai_provider"}


def test_failing_event_write_does_not_fail_the_request(
    env: ApiEnv, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"database is locked, key {GEMINI_KEY}")

    monkeypatch.setattr("app.api.ai.record_event", boom)
    with caplog.at_level(logging.DEBUG):
        response = put_key(env)
    assert response.status_code == 200 and response.json()["configured"] is True
    assert f"{GEMINI_VAR}={GEMINI_KEY}" in env.env_text()
    assert "not recorded" in caplog.text and GEMINI_KEY not in caplog.text


# --- Protection ----------------------------------------------------------------------------------


def test_forged_requests_change_nothing(env: ApiEnv) -> None:
    url = "/api/ai/providers/gemini/credential"
    foreign = env.client.put(
        url, json={"value": GEMINI_KEY}, headers={"Origin": "https://x.example"}
    )
    assert foreign.status_code == 403
    form = env.client.put(
        url,
        content=f"value={GEMINI_KEY}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert form.status_code == 415
    rebinding = env.client.get("/api/ai/status", headers={"Host": "evil.example:8000"})
    assert rebinding.status_code == 403
    assert not env.env_path.exists()


# --- Connection test -----------------------------------------------------------------------------


def test_connection_test_success(env: ApiEnv) -> None:
    put_key(env)
    response = env.client.post("/api/ai/test", json={"provider": "gemini"})
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["provider"], body["error_code"]) == ("ok", "gemini", None)
    assert body["model"] and body["elapsed_ms"] >= 0
    assert body["input_tokens"] is not None and body["output_tokens"] is not None
    assert len(env.servers["gemini"].requests) == 1


def test_connection_test_auth_error(env: ApiEnv) -> None:
    put_key(env, "groq", GROQ_KEY)
    env.servers["groq"].script = [fixture_reply("groq", "error_401", status=401)]
    response = env.client.post("/api/ai/test", json={"provider": "groq"})
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["reason"]) == ("unavailable", "auth")
    assert (body["error_code"], body["http_status"]) == ("auth", 401)
    assert body["detail_kind"] == "provider" and body["message"]
    assert GROQ_KEY not in response.text
    # The bad key is now marked: the status says so.
    assert provider(env.client.get("/api/ai/status").json(), "groq")["misconfigured"] is True


def test_connection_test_quota_error(env: ApiEnv) -> None:
    put_key(env, "groq", GROQ_KEY)
    env.servers["groq"].script = [fixture_reply("groq", "error_429_rpd", status=429)]
    body = env.client.post("/api/ai/test", json={"provider": "groq"}).json()
    assert (body["status"], body["reason"], body["error_code"]) == (
        "unavailable",
        "quota",
        "quota_exhausted",
    )
    state = provider(env.client.get("/api/ai/status").json(), "groq")
    assert state["cooldown_until"] is not None and state["last_error"] == "quota_exhausted"


def test_connection_test_of_an_unconfigured_provider_makes_no_request(env: ApiEnv) -> None:
    response = env.client.post("/api/ai/test", json={"provider": "gemini"})
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["reason"]) == ("unavailable", "no_provider_configured")
    assert env.servers["gemini"].requests == []


def test_second_test_in_parallel_is_a_409_and_the_database_is_free_meanwhile(
    env: ApiEnv, make_server
) -> None:
    path = env.engine.url.database
    inside = threading.Event()
    database_was_free: list[bool] = []

    def handler(_received) -> Reply:  # runs in the server thread, during the first call
        inside.set()
        try:
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")  # fails with 'database is locked' if held
                other.rollback()
            database_was_free.append(True)
        except sqlite3.OperationalError:
            database_was_free.append(False)
        time.sleep(0.6)
        return fixture_reply("gemini", "generate_ok")

    env.servers["gemini"] = server = make_server(handler=handler)
    put_key(env)  # after the swap: the providers are rebuilt against the new server
    first: list = []
    thread = threading.Thread(
        target=lambda: first.append(env.client.post("/api/ai/test", json={"provider": "gemini"}))
    )
    thread.start()
    try:
        assert inside.wait(timeout=10)
        second = env.client.post("/api/ai/test", json={"provider": "gemini"})
        assert (second.status_code, second.json()["detail"]["code"]) == (409, "test_in_progress")
    finally:
        thread.join(timeout=20)
    assert first[0].status_code == 200 and first[0].json()["status"] == "ok"
    assert database_was_free == [True]
    assert len(server.requests) == 1  # the refused test made no request


def test_connection_test_is_journalled_and_shows_in_usage(env: ApiEnv) -> None:
    put_key(env, "groq", GROQ_KEY)
    env.client.post("/api/ai/test", json={"provider": "groq"})
    with Session(env.engine) as session:
        rows = list(session.scalars(select(AICallLog)))
    assert [(r.provider, r.task, r.success) for r in rows] == [("groq", "connection_test", True)]


# --- Usage ---------------------------------------------------------------------------------------


def test_usage_lists_every_day_today_first(env: ApiEnv) -> None:
    put_key(env, "groq", GROQ_KEY)
    env.client.post("/api/ai/test", json={"provider": "groq"})
    response = env.client.get("/api/ai/usage", params={"days": 3})
    assert response.status_code == 200
    days = response.json()["days"]
    assert len(days) == 3
    assert days[0]["day"] > days[1]["day"] > days[2]["day"]
    assert days[0]["requests"] == 1 and days[0]["successes"] == 1
    assert days[0]["input_tokens"] == 96 and days[0]["output_tokens"] == 14
    row = days[0]["rows"][0]
    assert (row["provider"], row["requests"], row["errors"]) == ("groq", 1, {})
    assert days[1] == {
        "day": days[1]["day"],
        "requests": 0,
        "successes": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "rows": [],
    }


def test_usage_default_window_and_bounds(env: ApiEnv) -> None:
    assert len(env.client.get("/api/ai/usage").json()["days"]) == 7
    assert len(env.client.get("/api/ai/usage", params={"days": 90}).json()["days"]) == 90
    for days in (0, 91, -1, "x"):
        response = env.client.get("/api/ai/usage", params={"days": days})
        assert (response.status_code, response.json()["detail"]["code"]) == (422, "invalid_request")


def test_usage_leaves_the_pooled_connection_writable(env: ApiEnv) -> None:
    env.client.get("/api/ai/usage")
    assert env.client.patch("/api/settings", json={"new_items_per_day": 20}).status_code == 200
    assert put_key(env).status_code == 200
    assert len(events(env, "ai.credential_changed")) == 1


def test_usage_without_a_database_is_a_503_and_creates_nothing(
    env: ApiEnv, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.engine import create_db_engine, get_engine

    missing = tmp_path / "missing" / "none.sqlite3"
    engine = create_db_engine(f"sqlite:///{missing.as_posix()}")
    env.client.app.dependency_overrides[get_engine] = lambda: engine
    try:
        response = env.client.get("/api/ai/usage")
    finally:
        engine.dispose()
    assert (response.status_code, response.json()["detail"]["code"]) == (
        503,
        "database_unavailable",
    )
    assert not missing.exists()


# --- Provider order ------------------------------------------------------------------------------


def test_patching_the_order_is_taken_into_account_at_once(env: ApiEnv) -> None:
    put_key(env)
    put_key(env, "groq", GROQ_KEY)
    assert (
        env.client.patch("/api/settings", json={"ai_provider_order": ["groq"]}).status_code == 200
    )
    body = env.client.get("/api/ai/status").json()
    assert body["order"] == ["groq"]
    assert provider(body, "gemini")["enabled"] is False and provider(body, "groq")["enabled"]
    env.client.patch("/api/settings", json={"ai_provider_order": []})
    body = env.client.get("/api/ai/status").json()
    assert (body["ai_off"], body["degraded"], body["order"]) == (True, True, [])


# --- Demo mode -----------------------------------------------------------------------------------


def test_demo_database_refuses_the_writes_and_allows_the_reads(env: ApiEnv) -> None:
    with Session(env.engine) as session:
        write_demo_marker(
            session,
            DemoMarker(
                dataset_version=1, seed=1, days=10, anchor=datetime(2026, 9, 1, tzinfo=UTC).date()
            ),
        )
        session.commit()
    status = env.client.get("/api/ai/status")
    assert status.status_code == 200 and status.json()["demo"] is True
    for response in (
        put_key(env),
        env.client.delete("/api/ai/providers/gemini/credential"),
        env.client.post("/api/ai/test", json={"provider": "gemini"}),
        env.client.patch("/api/settings", json={"ai_provider_order": ["groq"]}),
    ):
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "demo_read_only")
    assert not env.env_path.exists()
    assert env.client.get("/api/ai/usage").status_code == 200
    assert env.client.get("/api/settings").status_code == 200
    # The other settings stay editable on the demo database.
    assert env.client.patch("/api/settings", json={"new_items_per_day": 15}).status_code == 200


# --- Secrets everywhere --------------------------------------------------------------------------


def test_a_known_key_appears_nowhere_it_should_not(
    env: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    texts: list[str] = []
    with caplog.at_level(logging.DEBUG):
        texts.append(put_key(env).text)
        put_key(env, "groq", GROQ_KEY)
        env.servers["gemini"].script = [fixture_reply("gemini", "error_401", status=401)]
        for call in (
            lambda: env.client.get("/api/ai/status"),
            lambda: env.client.post("/api/ai/test", json={"provider": "gemini"}),
            lambda: env.client.post("/api/ai/test", json={"provider": "groq"}),
            lambda: env.client.get("/api/ai/usage"),
            lambda: env.client.get("/api/settings"),
            lambda: env.client.put("/api/ai/providers/gemini/credential", json={"value": ["x"]}),
            lambda: env.client.put("/api/ai/providers/gemini/credential", json={"value": "a b c"}),
            lambda: env.client.get("/openapi.json"),
            lambda: env.client.get("/docs"),
        ):
            texts.append(call().text)
    for key in (GEMINI_KEY, GROQ_KEY):
        assert all(key not in text for text in texts)
        assert key not in caplog.text
        with Session(env.engine) as session:
            for row in session.scalars(select(EventLog)):
                assert key not in str(row.payload)
            for call_row in session.scalars(select(AICallLog)):
                assert key not in (call_row.error_message or "")
        assert key not in repr(env.gateway) + repr(dict(env.gateway.providers)) + repr(
            env.gateway.status()
        )
