"""In-memory health of the providers: cooldown after a quota error, "misconfigured" after an auth
error, last error. Shared by the threads of the API, hence the lock. Lost on restart on purpose: a
quota or a key may well have been fixed in the meantime."""

import threading
from dataclasses import dataclass, replace
from datetime import datetime

from app.ai.types import ErrorKind


@dataclass(frozen=True)
class HealthSnapshot:
    cooldown_until: datetime | None = None
    misconfigured: bool = False
    last_error: ErrorKind | None = None


class ProviderHealth:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, HealthSnapshot] = {}

    def snapshot(self, name: str, now: datetime) -> HealthSnapshot:
        """State of a provider; an expired cooldown is reported as none."""
        with self._lock:
            state = self._state.get(name, HealthSnapshot())
        if state.cooldown_until is not None and state.cooldown_until <= now:
            return replace(state, cooldown_until=None)
        return state

    def blocked_by(self, name: str, now: datetime) -> ErrorKind | None:
        """Why the provider should be skipped: quota (cooldown) or auth (misconfigured)."""
        state = self.snapshot(name, now)
        if state.misconfigured:
            return ErrorKind.AUTH
        if state.cooldown_until is not None:
            return ErrorKind.QUOTA_EXHAUSTED
        return None

    def record_failure(
        self,
        name: str,
        kind: ErrorKind,
        *,
        cooldown_until: datetime | None = None,
        misconfigured: bool = False,
    ) -> None:
        with self._lock:
            state = self._state.get(name, HealthSnapshot())
            self._state[name] = HealthSnapshot(
                cooldown_until=cooldown_until or state.cooldown_until,
                misconfigured=misconfigured or state.misconfigured,
                last_error=kind,
            )

    def record_success(self, name: str) -> None:
        with self._lock:
            self._state[name] = HealthSnapshot()

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
