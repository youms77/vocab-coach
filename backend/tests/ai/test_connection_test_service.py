"""The connection-test service shared by the CLI and the API (D-065)."""

import threading
from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import AiStatus, ErrorKind, UnavailableReason, UnknownProvider
from app.services.ai_connection_test import (
    MESSAGE_LIMIT,
    TestInProgress,
    run_connection_test,
)
from tests.ai.conftest import log_rows

KEY = "sk-secret-secret-secret-1234"


def _run(gateway: Gateway, engine: Engine, name: str, secrets: tuple[str, ...] = ()) -> object:
    return run_connection_test(gateway, lambda: Session(engine), name, lambda: list(secrets))


def test_success_reports_model_tokens_and_time(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    gateway = make_gateway(provider_factory("groq", Success(model="m-1")))
    report = _run(gateway, engine, "groq")
    assert report.status is AiStatus.OK
    assert (report.provider, report.model) == ("groq", "m-1")
    assert (report.input_tokens, report.output_tokens) == (10, 5)
    assert report.error_code is None and report.http_status is None
    assert report.detail_kind == "none" and report.message is None
    assert len(log_rows(engine)) == 1


def test_auth_failure_reports_the_logged_error_and_masks_the_key(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    failure = Failure(ErrorKind.AUTH, f"bad key {KEY}", status_code=401)
    gateway = make_gateway(provider_factory("groq", failure), secrets=[KEY])
    report = _run(gateway, engine, "groq", (KEY,))
    assert report.status is AiStatus.UNAVAILABLE
    assert report.reason is UnavailableReason.AUTH
    assert (report.error_code, report.http_status) == ("auth", 401)
    assert report.detail_kind == "provider"
    assert report.message is not None and KEY not in report.message
    assert len(report.message) <= MESSAGE_LIMIT


def test_message_is_masked_again_even_if_the_gateway_secrets_differ(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    failure = Failure(ErrorKind.AUTH, f"bad key {KEY}", status_code=401)
    gateway = make_gateway(provider_factory("groq", failure), secrets=[])
    report = _run(gateway, engine, "groq", (KEY,))
    assert report.message is not None and KEY not in report.message


def test_invalid_output_is_incomplete_with_a_schema_detail(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    gateway = make_gateway(provider_factory("groq", Success(content={"wrong": 1})))
    report = _run(gateway, engine, "groq")
    assert report.status is AiStatus.INCOMPLETE
    assert report.error_code == "invalid_output"


def test_not_configured_provider_makes_no_request(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    provider = provider_factory("groq", Success(), configured=False)
    report = _run(make_gateway(provider), engine, "groq")
    assert report.status is AiStatus.UNAVAILABLE
    assert report.reason is UnavailableReason.NO_PROVIDER_CONFIGURED
    assert provider.calls == 0
    assert log_rows(engine) == []


def test_unknown_provider_is_a_usage_error(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    with pytest.raises(UnknownProvider):
        _run(make_gateway(provider_factory("groq", Success())), engine, "nope")


def test_second_test_of_the_same_provider_is_refused_while_one_runs(
    engine: Engine,
    provider_factory: Callable[..., FakeProvider],
    make_gateway: Callable[..., Gateway],
) -> None:
    started, release = threading.Event(), threading.Event()
    groq = provider_factory("groq", Success())
    other = provider_factory("gemini", Success())
    original = groq.generate_json

    def slow(request):  # type: ignore[no-untyped-def]
        started.set()
        assert release.wait(timeout=10)
        return original(request)

    groq.generate_json = slow  # type: ignore[method-assign]
    gateway = make_gateway(groq, other)
    results: list[object] = []
    thread = threading.Thread(target=lambda: results.append(_run(gateway, engine, "groq")))
    thread.start()
    try:
        assert started.wait(timeout=10)
        with pytest.raises(TestInProgress):
            _run(gateway, engine, "groq")
        # Another provider is not blocked.
        assert _run(gateway, engine, "gemini").status is AiStatus.OK
    finally:
        release.set()
        thread.join(timeout=10)
    assert results and results[0].status is AiStatus.OK
    # The lock is free again afterwards.
    assert _run(gateway, engine, "groq").status is AiStatus.OK
