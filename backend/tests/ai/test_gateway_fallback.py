"""Fallback, cooldown, misconfigured providers, unavailable reasons, time budget and pinning."""

from collections.abc import Callable
from datetime import timedelta

import pytest

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import AiStatus, ErrorKind, UnavailableReason, UnknownProvider
from tests.ai.conftest import FakeClock, log_rows, ping

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]


def test_quota_falls_back_at_once_and_the_next_call_skips_the_provider(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED, status_code=429), Success())
    b = provider_factory("b", Success())
    gateway = make_gateway(a, b)

    first = ping(gateway)
    assert first.ok and first.provider == "b" and clock.sleeps == []
    rows_after_first = len(log_rows(engine))

    second = ping(gateway)
    assert second.ok and second.provider == "b"
    assert a.calls == 1  # skipped while cooling down
    new_rows = log_rows(engine)[rows_after_first:]
    assert [r.provider for r in new_rows] == ["b"]  # no log line for the skipped provider

    clock.advance(3601)  # QUOTA_COOLDOWN is one hour
    third = ping(gateway)
    assert third.ok and third.provider == "a" and a.calls == 2  # probed again


def test_status_reports_the_cooldown(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED))
    gateway = make_gateway(a, provider_factory("b", Success()), order=["a", "b"])
    ping(gateway)

    status = {s.name: s for s in gateway.status()}
    assert status["a"].cooldown_until == clock.now() + timedelta(hours=1)
    assert (status["a"].available, status["a"].last_error) == (False, ErrorKind.QUOTA_EXHAUSTED)
    assert status["b"].available and status["b"].cooldown_until is None


def test_auth_error_marks_the_provider_until_reload(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Failure(ErrorKind.AUTH, status_code=401), Success())
    b = provider_factory("b", Success())
    gateway = make_gateway(a, b)

    assert ping(gateway).provider == "b"
    assert ping(gateway).provider == "b" and a.calls == 1
    [status_a, _] = gateway.status()
    assert status_a.misconfigured and not status_a.available

    gateway.reload()
    assert ping(gateway).provider == "a"  # reactivated


def test_reload_rebuilds_providers_from_the_factory(
    provider_factory: ProviderFactory, engine, clock: FakeClock
) -> None:
    from sqlalchemy.orm import Session

    old, new = provider_factory("a", Failure(ErrorKind.AUTH)), provider_factory("a", Success())
    current = [old]
    gateway = Gateway(
        lambda: {"a": current[0]},
        session_factory=lambda: Session(engine),
        provider_order=lambda: ["a"],
        clock=clock.now,
        sleep=clock.sleep,
    )
    assert ping(gateway).status is AiStatus.UNAVAILABLE
    current[0] = new  # e.g. the user fixed the key
    gateway.reload()
    assert ping(gateway).ok


@pytest.mark.parametrize("kind", [ErrorKind.NETWORK, ErrorKind.BAD_REQUEST])
def test_no_retry_for_network_and_bad_request(
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
    kind: ErrorKind,
) -> None:
    a = provider_factory("a", Failure(kind))
    b = provider_factory("b", Success())
    result = ping(make_gateway(a, b))
    assert result.ok and a.calls == 1 and clock.sleeps == []


def test_provider_order_comes_from_the_order_setting(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a, b, c = (provider_factory(n, Success()) for n in "abc")
    gateway = make_gateway(a, b, c, order=["c", "a"])  # b is absent: disabled
    assert ping(gateway).provider == "c"
    assert b.calls == 0
    assert {s.name: s.enabled for s in gateway.status()} == {"a": True, "b": False, "c": True}


def test_no_provider_configured_means_zero_calls_and_zero_log_rows(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success(), configured=False)
    for gateway in (
        make_gateway(a),  # present but not configured
        make_gateway(provider_factory("b", Success()), order=[]),  # AI turned off
        make_gateway(provider_factory("c", Success()), order=["zzz"]),  # unknown name
        make_gateway(),  # no provider at all
    ):
        result = ping(gateway)
        assert result.status is AiStatus.UNAVAILABLE
        assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED
        assert result.attempts == 0 and result.data is None
    assert a.calls == 0 and log_rows(engine) == []


@pytest.mark.parametrize(
    ("kinds", "reason"),
    [
        ([ErrorKind.NETWORK, ErrorKind.NETWORK], UnavailableReason.NETWORK),
        ([ErrorKind.QUOTA_EXHAUSTED, ErrorKind.QUOTA_EXHAUSTED], UnavailableReason.QUOTA),
        ([ErrorKind.AUTH, ErrorKind.AUTH], UnavailableReason.AUTH),
        ([ErrorKind.NETWORK, ErrorKind.AUTH], UnavailableReason.ALL_FAILED),
        ([ErrorKind.BAD_REQUEST, ErrorKind.BAD_REQUEST], UnavailableReason.ALL_FAILED),
        ([ErrorKind.TRANSIENT, ErrorKind.TRANSIENT], UnavailableReason.ALL_FAILED),
    ],
)
def test_all_providers_failing_gives_a_reason(
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    kinds: list[ErrorKind],
    reason: UnavailableReason,
) -> None:
    a = provider_factory("a", Failure(kinds[0], message="first failure"))
    b = provider_factory("b", Failure(kinds[1], message="second failure"))
    result = ping(make_gateway(a, b))
    assert result.status is AiStatus.UNAVAILABLE and result.reason is reason
    assert (result.provider, result.detail) == ("b", "second failure")


def test_providers_skipped_for_cooldown_count_in_the_reason(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED))
    gateway = make_gateway(a)
    assert ping(gateway).reason is UnavailableReason.QUOTA
    again = ping(gateway)  # now skipped, no request at all
    assert again.reason is UnavailableReason.QUOTA and again.attempts == 0


def test_time_budget_stops_the_retries(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    # Each attempt takes 40 s: the second one ends at 81 s, the third would end at 123 s.
    a = provider_factory("a", Failure(ErrorKind.TRANSIENT, latency_s=40.0))
    b = provider_factory("b", Success())
    result = ping(make_gateway(a, b))
    assert result.reason is UnavailableReason.TIMEOUT
    assert b.calls == 0  # nothing left of the 90 s budget


def test_a_wait_that_does_not_fit_is_skipped_and_the_next_provider_runs(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.RATE_LIMITED, retry_after=15.0, latency_s=80.0))
    b = provider_factory("b", Success())
    result = ping(make_gateway(a, b))
    assert result.ok and result.provider == "b"
    assert clock.sleeps == []  # 80 s + 15 s > 90 s: not waited
    assert b.requests[0].timeout_s == 10.0  # capped by the budget left


def test_a_wait_that_does_not_fit_with_no_other_provider_is_a_timeout(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    a = provider_factory("a", Failure(ErrorKind.RATE_LIMITED, retry_after=15.0, latency_s=80.0))
    result = ping(make_gateway(a))
    assert result.reason is UnavailableReason.TIMEOUT and clock.sleeps == []


# --- pin_provider -------------------------------------------------------------------------------


def test_pin_uses_only_that_provider_and_does_not_fall_back(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success())
    b = provider_factory("b", Failure(ErrorKind.BAD_REQUEST))
    result = ping(make_gateway(a, b), pin_provider="b")
    assert result.status is AiStatus.UNAVAILABLE and a.calls == 0
    [row] = log_rows(engine)  # logged like any other call
    assert (row.provider, row.success, row.fallback_from) == ("b", False, None)


def test_pin_ignores_cooldown_and_auth_marks_and_the_order(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED), Success())
    b = provider_factory("b", Failure(ErrorKind.AUTH), Success())
    gateway = make_gateway(a, b, order=["a"])  # b is not even enabled
    ping(gateway)  # puts a in cooldown
    assert ping(gateway, pin_provider="a").ok  # cooldown ignored
    assert ping(gateway, pin_provider="b").status is AiStatus.UNAVAILABLE  # marks b misconfigured
    assert ping(gateway, pin_provider="b").ok  # mark ignored; success clears it
    status = {s.name: s for s in gateway.status()}
    assert not status["b"].misconfigured and status["a"].cooldown_until is None


def test_pin_errors(provider_factory: ProviderFactory, make_gateway: GatewayFactory) -> None:
    gateway = make_gateway(provider_factory("a", Success(), configured=False))
    with pytest.raises(UnknownProvider):
        ping(gateway, pin_provider="nope")
    result = ping(gateway, pin_provider="a")
    assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED


def test_unexpected_provider_exception_is_contained_and_masked(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    class Broken(FakeProvider):
        def generate_json(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom with SECRETKEY-123456")

    a = Broken("a")
    b = provider_factory("b", Success())
    result = ping(make_gateway(a, b, secrets=["SECRETKEY-123456"]))
    assert result.ok and result.provider == "b"
    first = log_rows(engine)[0]
    assert first.error_code == "unexpected:RuntimeError"
    assert first.error_message == "boom with ***"
