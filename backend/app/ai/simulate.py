"""`python -m app ai simulate`: shows how the gateway behaves, with fake providers and no network.

Development tool. It builds a throwaway database with the migrations, runs three scenarios on a
simulated clock (the waits are printed, never slept) and prints the trace, the `ai_call_log` rows
and the usage summary. It never opens the personal database.
"""

import logging
import random
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Step, Success
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AiResult, ErrorKind
from app.db import migrate
from app.db.engine import create_db_engine
from app.db.models import AICallLog
from app.services.ai_usage import ai_usage_now

START = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


class _SimClock:
    def __init__(self, out: Callable[[str], None]) -> None:
        self.current = START
        self._out = out

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        self._out(f"    (would wait {seconds:.1f} s)")
        self.advance(seconds)


class _TraceHandler(logging.Handler):
    def __init__(self, out: Callable[[str], None]) -> None:
        super().__init__(logging.INFO)
        self._out = out

    def emit(self, record: logging.LogRecord) -> None:
        self._out(f"    trace: {record.getMessage()}")


def _describe(result: AiResult[ConnectionTestOutput]) -> str:
    parts = [f"status={result.status.value}"]
    if result.reason:
        parts.append(f"reason={result.reason.value}")
    if result.provider:
        parts.append(f"provider={result.provider}")
    parts.append(f"requests={result.attempts}")
    return " ".join(parts)


def run_simulation(out: Callable[[str], None] = print) -> int:
    clock = _SimClock(out)
    handler = _TraceHandler(out)
    logger = logging.getLogger("app.ai")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            url = f"sqlite:///{(Path(folder) / 'simulation.sqlite3').as_posix()}"
            out(f"Throwaway database built by the migrations ({url}).")
            migrate.upgrade(url)
            engine = create_db_engine(url)
            try:
                _scenarios(engine, clock, out)
                _report(engine, clock, out)
            finally:
                engine.dispose()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    return 0


def _gateway(engine: Engine, clock: _SimClock, **scripts: list[Step]) -> Gateway:
    providers = {
        name: FakeProvider(name, script, advance=clock.advance) for name, script in scripts.items()
    }
    return Gateway(
        providers,
        session_factory=lambda: Session(engine),
        provider_order=lambda: list(providers),
        clock=clock.now,
        sleep=clock.sleep,
        rng=random.Random(0),  # noqa: S311 (jitter, not security)
    )


def _ping(gateway: Gateway) -> AiResult[ConnectionTestOutput]:
    return gateway.generate_json("connection_test", {"text": "ping"}, ConnectionTestOutput)


def _scenarios(engine: Engine, clock: _SimClock, out: Callable[[str], None]) -> None:
    out("\n== 1. A 429 with Retry-After, then success ==")
    gateway = _gateway(
        engine,
        clock,
        fake_a=[
            Failure(ErrorKind.RATE_LIMITED, "too many requests", retry_after=2, status_code=429),
            Success(),
        ],
    )
    out(f"  -> {_describe(_ping(gateway))}")

    out("\n== 2. Quota exhausted: fallback, then the provider is skipped (cooldown) ==")
    gateway = _gateway(
        engine,
        clock,
        fake_a=[Failure(ErrorKind.QUOTA_EXHAUSTED, "daily quota reached", status_code=429)],
        fake_b=[Success()],
    )
    out(f"  call 1 -> {_describe(_ping(gateway))}")
    out(f"  call 2 -> {_describe(_ping(gateway))}")
    for status in gateway.status():
        out(f"  {status.name}: available={status.available} cooldown_until={status.cooldown_until}")

    out("\n== 3. Everything fails: unavailable ==")
    gateway = _gateway(
        engine,
        clock,
        fake_a=[Failure(ErrorKind.RATE_LIMITED, "slow down", status_code=429)],
        fake_b=[Failure(ErrorKind.NETWORK, "connection refused")],
    )
    out(f"  -> {_describe(_ping(gateway))}")


def _report(engine: Engine, clock: _SimClock, out: Callable[[str], None]) -> None:
    out("\n== ai_call_log ==")
    with Session(engine) as session:
        for row in session.scalars(select(AICallLog).order_by(AICallLog.id)):
            outcome = "ok" if row.success else f"{row.error_code} ({row.http_status})"
            via = f" after {row.fallback_from}" if row.fallback_from else ""
            out(
                f"  #{row.id:<2} {row.started_at:%H:%M:%S} {row.provider:<7} attempt {row.attempt}"
                f"{via}: {outcome}"
            )
        usage = ai_usage_now(session, clock.now())
    out(f"\n== Usage, study day {usage.day} ==")
    for row in usage.rows:
        out(
            f"  {row.provider}/{row.model}: {row.requests} requests, {row.successes} ok, "
            f"errors {row.errors or '-'}, tokens in/out {row.input_tokens}/{row.output_tokens}"
        )
