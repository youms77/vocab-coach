"""Provider health state and the error policy, as pure units."""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.ai import policy
from app.ai.health import ProviderHealth
from app.ai.policy import Action, decide, unavailable_reason
from app.ai.types import ErrorKind, ProviderError, UnavailableReason
from tests.ai.conftest import FixedRng

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def test_cooldown_expires_by_itself() -> None:
    health = ProviderHealth()
    health.record_failure("a", ErrorKind.QUOTA_EXHAUSTED, cooldown_until=NOW + timedelta(hours=1))
    assert health.blocked_by("a", NOW) is ErrorKind.QUOTA_EXHAUSTED
    assert health.blocked_by("a", NOW + timedelta(hours=1)) is None
    assert health.snapshot("a", NOW + timedelta(hours=2)).cooldown_until is None


def test_misconfigured_stays_until_reset_and_success_clears_it() -> None:
    health = ProviderHealth()
    health.record_failure("a", ErrorKind.AUTH, misconfigured=True)
    assert health.blocked_by("a", NOW + timedelta(days=30)) is ErrorKind.AUTH
    health.reset()
    assert health.blocked_by("a", NOW) is None
    health.record_failure("a", ErrorKind.AUTH, misconfigured=True)
    health.record_success("a")
    assert health.snapshot("a", NOW).last_error is None


def test_concurrent_updates_do_not_lose_or_corrupt_state() -> None:
    health = ProviderHealth()
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for n in range(300):
                name = f"p{(i + n) % 4}"
                health.record_failure(name, ErrorKind.TRANSIENT)
                health.snapshot(name, NOW)
                health.blocked_by(name, NOW)
                if n % 50 == 0:
                    health.record_success(name)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert health.snapshot("p0", NOW).last_error in (None, ErrorKind.TRANSIENT)


def _decide(kind: ErrorKind, *, failed: int = 1, repaired: bool = False, **kw: float):  # noqa: ANN202
    return decide(
        ProviderError(kind, "x", **kw), failed_attempts=failed, repaired=repaired, rng=FixedRng()
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ErrorKind.NETWORK, Action.FALLBACK),
        (ErrorKind.BAD_REQUEST, Action.FALLBACK),
        (ErrorKind.AUTH, Action.FALLBACK),
        (ErrorKind.QUOTA_EXHAUSTED, Action.FALLBACK),
        (ErrorKind.RATE_LIMITED, Action.RETRY),
        (ErrorKind.TRANSIENT, Action.RETRY),
        (ErrorKind.INVALID_OUTPUT, Action.REPAIR),
    ],
)
def test_first_failure_decisions(kind: ErrorKind, expected: Action) -> None:
    assert _decide(kind).action is expected


def test_decisions_after_the_limits() -> None:
    assert _decide(ErrorKind.INVALID_OUTPUT, repaired=True).action is Action.STOP
    assert _decide(ErrorKind.RATE_LIMITED, failed=3).action is Action.FALLBACK
    assert _decide(ErrorKind.TRANSIENT, failed=3).action is Action.FALLBACK
    assert _decide(ErrorKind.AUTH).misconfigured


def test_retry_after_is_used_up_to_the_cap() -> None:
    assert _decide(ErrorKind.RATE_LIMITED, retry_after=7.0).wait_s == 7.0
    assert _decide(ErrorKind.RATE_LIMITED, retry_after=policy.MAX_WAIT_S).action is Action.RETRY
    over = _decide(ErrorKind.RATE_LIMITED, retry_after=policy.MAX_WAIT_S + 1)
    assert over.action is Action.FALLBACK and over.cooldown == timedelta(seconds=21)


def test_quota_cooldown_defaults_to_one_hour_and_is_capped_at_one_hour() -> None:
    assert _decide(ErrorKind.QUOTA_EXHAUSTED).cooldown == timedelta(hours=1)
    assert _decide(ErrorKind.QUOTA_EXHAUSTED, retry_after=86400.0).cooldown == timedelta(hours=1)


def test_backoff_doubles() -> None:
    assert [policy.backoff(n, FixedRng()) for n in (1, 2, 3)] == [1.0, 2.0, 4.0]


def test_constants_are_the_documented_ones() -> None:
    assert (policy.MAX_ATTEMPTS_PER_PROVIDER, policy.BACKOFF_BASE_S, policy.BACKOFF_FACTOR) == (
        3,
        1,
        2,
    )
    assert (policy.JITTER, policy.MAX_WAIT_S, policy.TOTAL_BUDGET_S) == (0.25, 20, 90)
    assert timedelta(hours=1) == policy.QUOTA_COOLDOWN


def test_unavailable_reason_prefers_the_budget() -> None:
    assert (
        unavailable_reason([ErrorKind.NETWORK], budget_exhausted=True) is UnavailableReason.TIMEOUT
    )
