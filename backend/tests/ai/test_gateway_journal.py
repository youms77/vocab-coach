"""What the gateway writes to `ai_call_log`, what it never writes, and what a failure does."""

import logging
from collections.abc import Callable
from urllib.parse import quote

import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway, get_gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import ErrorKind, UnavailableReason
from app.config import Settings
from app.db.models import AICallLog
from app.db.settings_store import set_setting
from tests.ai.conftest import FakeClock, log_rows, ping

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]

KEY = "AIzaSyD-test-key/with+chars=1"


def all_log_text(engine: Engine) -> str:
    """Every column of every row, as one string (to prove something is nowhere)."""
    columns = [c.key for c in inspect(AICallLog).mapper.column_attrs]
    return " ".join(str(getattr(row, c)) for row in log_rows(engine) for c in columns)


def test_failed_attempts_keep_their_details(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    a = provider_factory(
        "a",
        Failure(ErrorKind.RATE_LIMITED, "slow down", status_code=429, latency_s=2.0),
        model="model-a",
    )
    ping(make_gateway(a, provider_factory("b", Success())))
    row = log_rows(engine)[0]
    assert (row.model, row.error_code, row.http_status, row.error_message) == (
        "model-a",
        "rate_limited",
        429,
        "slow down",
    )
    assert row.duration_ms == 2000 and row.input_tokens is None
    assert row.started_at.tzinfo is not None
    assert row.started_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_a_key_in_an_error_message_never_reaches_the_database_or_the_result(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="app.ai")
    message = f"GET https://api.example/v1?key={quote(KEY, safe='')}&alt=json failed; key {KEY}"
    a = provider_factory("a", Failure(ErrorKind.NETWORK, message))
    result = ping(make_gateway(a, secrets=[KEY]))

    assert result.detail is not None and "***" in result.detail
    assert KEY not in repr(result) and quote(KEY, safe="") not in repr(result)
    text = all_log_text(engine)
    assert KEY not in text and quote(KEY, safe="") not in text and "***" in text
    assert KEY not in caplog.text and quote(KEY, safe="") not in caplog.text


def test_messages_are_truncated_to_300_characters(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Failure(ErrorKind.BAD_REQUEST, "x" * 1000))
    result = ping(make_gateway(a))
    assert len(result.detail or "") == 300
    assert len(log_rows(engine)[0].error_message or "") == 300


def test_no_prompt_response_or_user_text_is_logged(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success(content={"ok": True, "echo": "RESPONSE-MARKER"}))
    gateway = make_gateway(a)
    gateway.generate_json("connection_test", {"text": "USER-MARKER"}, ConnectionTestOutput)
    text = all_log_text(engine)
    assert "USER-MARKER" not in text and "RESPONSE-MARKER" not in text
    assert "connectivity probe" not in text  # nor the system prompt


def test_a_journal_failure_never_breaks_a_successful_result(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, caplog
) -> None:
    class BrokenSession(Session):
        def commit(self) -> None:
            raise RuntimeError(f"disk is full {KEY}")

    a = provider_factory("a", Success())
    gateway = make_gateway(a, secrets=[KEY], session_factory=lambda: BrokenSession(engine))
    with caplog.at_level(logging.WARNING, logger="app.ai"):
        result = ping(gateway)

    assert result.ok and result.data == ConnectionTestOutput(ok=True, echo="ping")
    assert result.call_id is None
    assert "could not write ai_call_log" in caplog.text and KEY not in caplog.text
    assert log_rows(engine) == []


def test_log_rows_survive_a_rollback_of_the_caller(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, session: Session
) -> None:
    """The journal uses its own short transaction, never the caller's (D-038)."""
    session.execute(select(AICallLog))  # the caller has a transaction open
    ping(make_gateway(provider_factory("a", Failure(ErrorKind.NETWORK))))
    session.rollback()
    assert len(log_rows(engine)) == 1


def test_the_order_is_read_from_the_setting_when_not_injected(
    provider_factory: ProviderFactory, engine, clock: FakeClock
) -> None:
    gemini, groq = provider_factory("gemini", Success()), provider_factory("groq", Success())
    gateway = Gateway(
        {"gemini": gemini, "groq": groq},
        session_factory=lambda: Session(engine),
        clock=clock.now,
        sleep=clock.sleep,
    )
    assert ping(gateway).provider == "gemini"  # default order: gemini, groq, ollama

    with Session(engine) as session:
        set_setting(session, "ai_provider_order", ["groq"])
        session.commit()
    assert ping(gateway).provider == "groq"

    with Session(engine) as session:
        set_setting(session, "ai_provider_order", [])
        session.commit()
    assert ping(gateway).reason is UnavailableReason.NO_PROVIDER_CONFIGURED  # AI switched off


def test_without_any_key_the_application_gateway_is_in_degraded_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path))
    # Empty values, not `delenv`: an environment variable (even empty) wins over the owner's real
    # `.env`, so keys written there for real use can never turn this test into a network call.
    for name in ("VOCAB_GEMINI_API_KEY", "VOCAB_GROQ_API_KEY", "VOCAB_OLLAMA_BASE_URL"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    get_gateway.cache_clear()
    try:
        result = ping(get_gateway())
        assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED
        # Every real provider is known (D-040), none is configured: nothing was called.
        status = get_gateway().status()
        assert {s.name for s in status} == {"groq", "ollama"}
        assert not any(s.configured or s.available for s in status)
    finally:
        get_settings.cache_clear()
        get_gateway.cache_clear()


def test_settings_secret_values_and_repr() -> None:
    settings = Settings(_env_file=None, gemini_api_key=KEY, groq_api_key="", ollama_base_url="")
    assert settings.secret_values() == [KEY]
    assert settings.groq_api_key is None and settings.ollama_base_url is None  # empty = unset
    assert KEY not in repr(settings) and KEY not in str(settings)
