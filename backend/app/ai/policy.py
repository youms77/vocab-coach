"""Error policy of the gateway: every constant lives here, plus the pure decision functions.

The values are provisional: M2.b may adjust them after reading the real free-tier quotas.
"""

import random
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Protocol

from app.ai.types import ErrorKind, ProviderError, UnavailableReason

MAX_ATTEMPTS_PER_PROVIDER = 3  # transport attempts (rate limit, transient) before falling back
BACKOFF_BASE_S = 1.0
BACKOFF_FACTOR = 2.0
JITTER = 0.25  # +/- 25 % on the computed backoff
MAX_WAIT_S = 20.0  # longest single wait we accept (backoff or `retry_after`)
TOTAL_BUDGET_S = 90.0  # time allowed for one gateway call, all providers included
QUOTA_COOLDOWN = timedelta(hours=1)
REQUEST_TIMEOUT_S = 30.0  # per provider request; tasks may override it
LOG_MESSAGE_MAX = 300  # characters kept of an error message


class RandomLike(Protocol):
    def uniform(self, a: float, b: float, /) -> float: ...


def default_rng() -> RandomLike:
    return random.Random()  # noqa: S311 (backoff jitter, not security)


def backoff(attempt: int, rng: RandomLike) -> float:
    """Wait after the `attempt`-th failed request (1-based): 1 s, 2 s, 4 s... +/- 25 % jitter."""
    base = BACKOFF_BASE_S * BACKOFF_FACTOR ** (attempt - 1)
    return base * (1 + rng.uniform(-JITTER, JITTER))


class Action(StrEnum):
    RETRY = "retry"  # same provider, after a wait
    FALLBACK = "fallback"  # next provider
    REPAIR = "repair"  # same provider, validation message added to the prompt
    STOP = "stop"  # `incomplete`


@dataclass(frozen=True)
class Decision:
    action: Action
    wait_s: float = 0.0
    cooldown: timedelta | None = None  # put the provider in cooldown
    misconfigured: bool = False  # mark the provider as misconfigured until `reload()`


def decide(
    error: ProviderError, *, failed_attempts: int, repaired: bool, rng: RandomLike
) -> Decision:
    """What to do after a failed request. `failed_attempts` counts transport failures on this
    provider, the one that just happened included; `repaired` tells if the repair was used."""
    kind, retry_after = error.kind, error.retry_after
    match kind:
        case ErrorKind.QUOTA_EXHAUSTED:
            return Decision(Action.FALLBACK, cooldown=_cooldown(retry_after))
        case ErrorKind.RATE_LIMITED if retry_after is not None and retry_after > MAX_WAIT_S:
            return Decision(Action.FALLBACK, cooldown=_cooldown(retry_after))
        case ErrorKind.RATE_LIMITED | ErrorKind.TRANSIENT:
            if failed_attempts >= MAX_ATTEMPTS_PER_PROVIDER:
                return Decision(Action.FALLBACK)
            if kind is ErrorKind.RATE_LIMITED and retry_after is not None:
                return Decision(Action.RETRY, wait_s=max(retry_after, 0.0))
            return Decision(Action.RETRY, wait_s=min(backoff(failed_attempts, rng), MAX_WAIT_S))
        case ErrorKind.AUTH:
            return Decision(Action.FALLBACK, misconfigured=True)
        case ErrorKind.INVALID_OUTPUT:
            return Decision(Action.STOP if repaired else Action.REPAIR)
        case _:  # network, bad_request
            return Decision(Action.FALLBACK)


def _cooldown(retry_after: float | None) -> timedelta:
    """`QUOTA_COOLDOWN` without indication, else what the provider asked for (at most that)."""
    if retry_after is None:
        return QUOTA_COOLDOWN
    return min(timedelta(seconds=max(retry_after, 0.0)), QUOTA_COOLDOWN)


_FAILURE_CLASS = {
    ErrorKind.NETWORK: UnavailableReason.NETWORK,
    ErrorKind.QUOTA_EXHAUSTED: UnavailableReason.QUOTA,
    ErrorKind.RATE_LIMITED: UnavailableReason.QUOTA,
    ErrorKind.AUTH: UnavailableReason.AUTH,
}


def unavailable_reason(failures: list[ErrorKind], *, budget_exhausted: bool) -> UnavailableReason:
    """Reason when no provider could answer. `failures` holds one final error kind per provider that
    was tried or skipped (cooldown counts as quota, misconfigured as auth)."""
    if budget_exhausted:
        return UnavailableReason.TIMEOUT
    classes = {_FAILURE_CLASS.get(kind, UnavailableReason.ALL_FAILED) for kind in failures}
    if len(classes) == 1:
        return classes.pop()
    return UnavailableReason.ALL_FAILED
