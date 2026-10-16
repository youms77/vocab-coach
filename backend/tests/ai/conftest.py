"""Fixtures of the AI tests: no network, a fake clock whose `sleep` never waits, fake providers."""

import socket
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.tasks import TaskSpec
from app.ai.types import AiResult
from app.db.models import AICallLog

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", None, ""}


class NetworkBlocked(BaseException):
    """Not an `Exception`: the gateway's `except Exception` must not be able to hide it."""


def _host_of(address: Any) -> Any:
    return address[0] if isinstance(address, tuple) else None  # None: a Unix socket path


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Any connection to a non-local host fails the test. The CI has no key and no network need.

    Loopback stays open: on Windows `socket.socketpair()` connects through 127.0.0.1.
    """
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> None:
        if _host_of(address) not in LOCAL_HOSTS:
            raise NetworkBlocked(f"network access is forbidden in AI tests: {address!r}")
        return real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if _host_of(address) not in LOCAL_HOSTS:
            raise NetworkBlocked(f"network access is forbidden in AI tests: {address!r}")
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in LOCAL_HOSTS:
            raise NetworkBlocked(f"DNS lookup is forbidden in AI tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield


class FakeClock:
    """Aware UTC clock that only moves when the test (or a fake `sleep`) says so."""

    def __init__(self) -> None:
        self.current = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


class FixedRng:
    """Jitter-free backoff: `uniform(a, b)` returns the middle of the range."""

    def uniform(self, a: float, b: float, /) -> float:
        return (a + b) / 2


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def provider_factory(clock: FakeClock) -> Callable[..., FakeProvider]:
    """Fake providers whose latency moves the fake clock."""

    def make(name: str, *script: Any, **kwargs: Any) -> FakeProvider:
        return FakeProvider(name, script, advance=clock.advance, **kwargs)

    return make


@pytest.fixture
def make_gateway(engine: Engine, clock: FakeClock) -> Callable[..., Gateway]:
    def make(
        *providers: FakeProvider,
        order: Sequence[str] | None = None,
        secrets: Sequence[str] = (),
        session_factory: Callable[[], Session] | None = None,
        tasks: dict[str, TaskSpec] | None = None,
    ) -> Gateway:
        names = [p.name for p in providers] if order is None else order
        return Gateway(
            {p.name: p for p in providers},
            session_factory=session_factory or (lambda: Session(engine)),
            provider_order=lambda: list(names),
            secrets=lambda: list(secrets),
            clock=clock.now,
            sleep=clock.sleep,
            rng=FixedRng(),
            tasks=tasks,
        )

    return make


def ping(gateway: Gateway, **kwargs: Any) -> AiResult[ConnectionTestOutput]:
    """The `connection_test` task, the simplest real call."""
    return gateway.generate_json(
        "connection_test", {"text": "ping"}, ConnectionTestOutput, **kwargs
    )


def log_rows(engine: Engine) -> list[AICallLog]:
    with Session(engine) as session:
        return list(session.scalars(select(AICallLog).order_by(AICallLog.id)))
