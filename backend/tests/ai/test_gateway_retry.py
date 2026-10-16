"""Success path, retry, backoff and `retry_after` (all offline, with a fake clock)."""

import socket
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AiStatus, ErrorKind
from tests.ai.conftest import FakeClock, NetworkBlocked, log_rows, ping

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]


def test_network_guard_blocks_real_connections() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80), timeout=1)
    with pytest.raises(NetworkBlocked), socket.socket() as sock:
        sock.connect(("93.184.216.34", 80))


def test_first_try_success_writes_one_log_row(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    a = provider_factory("a", Success(input_tokens=12, output_tokens=7, latency_s=0.25))
    result = ping(make_gateway(a))

    assert result.status is AiStatus.OK and result.ok
    assert result.data == ConnectionTestOutput(ok=True, echo="ping")
    assert (result.provider, result.model, result.attempts) == ("a", "fake-model", 1)
    assert (result.input_tokens, result.output_tokens) == (12, 7)
    assert result.prompt_version == "connection_test.v1"
    [row] = log_rows(engine)
    assert (row.provider, row.model, row.task, row.prompt_version) == (
        "a",
        "fake-model",
        "connection_test",
        "connection_test.v1",
    )
    assert (row.success, row.attempt, row.fallback_from) == (True, 1, None)
    assert (row.input_tokens, row.output_tokens, row.duration_ms) == (12, 7, 250)
    assert row.error_code is None and row.error_message is None
    assert row.started_at == clock.now() - timedelta(seconds=0.25)
    assert result.call_id == row.id


def test_rate_limit_then_success_respects_retry_after(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    a = provider_factory(
        "a", Failure(ErrorKind.RATE_LIMITED, retry_after=3.0, status_code=429), Success()
    )
    result = ping(make_gateway(a))

    assert result.ok and result.attempts == 2
    assert clock.sleeps == [3.0]
    first, second = log_rows(engine)
    assert (first.success, first.error_code, first.http_status, first.attempt) == (
        False,
        "rate_limited",
        429,
        1,
    )
    assert (second.success, second.attempt) == (True, 2)


def test_rate_limit_without_retry_after_backs_off_exponentially(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory(
        "a", Failure(ErrorKind.RATE_LIMITED), Failure(ErrorKind.RATE_LIMITED), Success()
    )
    assert ping(make_gateway(a)).ok
    assert clock.sleeps == [1.0, 2.0]  # base 1 s, factor 2, no jitter with the fixed rng


def test_backoff_jitter_stays_within_25_percent(
    provider_factory: ProviderFactory, engine, clock: FakeClock
) -> None:
    import random

    from sqlalchemy.orm import Session

    a = provider_factory("a", *[Failure(ErrorKind.TRANSIENT)] * 2, Success())
    gateway = Gateway(
        {"a": a},
        session_factory=lambda: Session(engine),
        provider_order=lambda: ["a"],
        clock=clock.now,
        sleep=clock.sleep,
        rng=random.Random(7),  # noqa: S311
    )
    assert ping(gateway).ok
    assert 0.75 <= clock.sleeps[0] <= 1.25
    assert 1.5 <= clock.sleeps[1] <= 2.5


def test_transient_errors_are_retried(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.TRANSIENT, status_code=503), Success())
    result = ping(make_gateway(a))
    assert result.ok and a.calls == 2 and clock.sleeps == [1.0]


def test_long_retry_after_is_not_waited_for(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.RATE_LIMITED, retry_after=45.0))
    b = provider_factory("b", Success())
    gateway = make_gateway(a, b)

    result = ping(gateway)

    assert result.ok and result.provider == "b"
    assert clock.sleeps == []  # 45 s > MAX_WAIT_S: straight to the next provider
    [status_a, _] = gateway.status()
    assert status_a.cooldown_until == clock.now() + timedelta(seconds=45)  # what it asked for


def test_repeated_rate_limit_falls_back_after_three_attempts(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.RATE_LIMITED, status_code=429))
    b = provider_factory("b", Success())

    result = ping(make_gateway(a, b))

    assert result.ok and result.provider == "b" and result.attempts == 4
    assert a.calls == 3 and clock.sleeps == [1.0, 2.0]
    rows = log_rows(engine)
    assert [(r.provider, r.attempt, r.fallback_from) for r in rows] == [
        ("a", 1, None),
        ("a", 2, None),
        ("a", 3, None),
        ("b", 1, "a"),
    ]


def test_request_timeout_is_the_task_timeout(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success())
    ping(make_gateway(a))
    assert a.requests[0].timeout_s == 15.0  # connection_test overrides the 30 s default
