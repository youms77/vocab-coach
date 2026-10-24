"""One real request to one AI provider, shared by `python -m app ai test` and `POST /api/ai/test`.

The call goes through the gateway (`connection_test` task, pinned to the provider), so it is
journalled in `ai_call_log` like any other and honours the retry rules. No database session is open
during the call (D-038): the gateway writes its own rows, and the last error is read afterwards in a
short session.

A lock per provider refuses a second test of the same provider while one is running (a double click
would spend the free quota twice): `TestInProgress`.
"""

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.redact import clean_message
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AiResult, AiStatus, AudioClip, UnavailableReason
from app.db.models import AICallLog
from app.domain.pronunciation import silent_wav
from app.domain.settings_defaults import KNOWN_SPEECH_PROVIDERS

MESSAGE_LIMIT = 300

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class TestInProgress(Exception):
    """A test of this provider is already running."""

    __test__ = False  # not a pytest class, whatever the name says


@dataclass(frozen=True)
class ConnectionTestReport:
    provider: str
    status: AiStatus
    reason: UnavailableReason | None
    model: str | None
    elapsed_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None  # code of the last logged request, e.g. "auth", "quota_exhausted"
    http_status: int | None
    message: str | None  # the provider's own wording, masked and cut to 300 characters
    # "schema": the model answered but not in the expected shape; "provider": `message` comes from
    # the provider or the gateway; "none": nothing more to say.
    detail_kind: Literal["none", "provider", "schema"]


def last_error(
    session_factory: Callable[[], Session], call_id: int | None
) -> tuple[str | None, int | None]:
    """Error code and HTTP status of a logged request, read in a short session."""
    if call_id is None:
        return None, None
    with session_factory() as session:
        row = session.get(AICallLog, call_id)
        return (row.error_code, row.http_status) if row is not None else (None, None)


def mask(text: str, secrets: Sequence[str]) -> str:
    return clean_message(text, secrets, MESSAGE_LIMIT)


def report_from_result(
    result: AiResult,
    provider: str,
    elapsed_ms: int,
    session_factory: Callable[[], Session],
    secrets: Sequence[str],
) -> ConnectionTestReport:
    """Summarize a gateway result (text or transcription) for display."""
    if result.status is AiStatus.OK:
        code, http_status = None, None
    else:
        code, http_status = last_error(session_factory, result.call_id)
    message = mask(result.detail, secrets) if result.detail else None
    if message:
        kind: Literal["none", "provider", "schema"] = "provider"
    elif result.status is AiStatus.INCOMPLETE:
        kind = "schema"
    else:
        kind = "none"
    return ConnectionTestReport(
        provider=provider,
        status=result.status,
        reason=result.reason,
        model=result.model,
        elapsed_ms=elapsed_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        error_code=code,
        http_status=http_status,
        message=message,
        detail_kind=kind,
    )


def _lock_for(provider: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(provider, threading.Lock())


def run_connection_test(
    gateway: Gateway,
    session_factory: Callable[[], Session],
    provider: str,
    secrets: Callable[[], Sequence[str]],
) -> ConnectionTestReport:
    """Ask `provider` for a trivial answer (a speech provider: assess one second of silence).
    Raises TestInProgress, or UnknownProvider (from the gateway) for a name it does not know. A
    provider that is not configured is not called: the gateway answers
    `unavailable(no_provider_configured)` without any request."""
    lock = _lock_for(provider)
    if not lock.acquire(blocking=False):
        raise TestInProgress(provider)
    try:
        started = time.perf_counter()
        result: AiResult
        if provider in KNOWN_SPEECH_PROVIDERS:
            # One second of silence against "Hello.": a 200 answer, even a "silence" one, proves
            # the key, the region and the endpoint (M6.c1, D-214).
            clip = AudioClip(data=silent_wav(1.0), filename="test.wav", content_type="audio/wav")
            result = gateway.assess_pronunciation(
                clip, reference_text="Hello.", pin_provider=provider
            )
        else:
            result = gateway.generate_json(
                "connection_test", {"text": "ping"}, ConnectionTestOutput, pin_provider=provider
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return report_from_result(result, provider, elapsed_ms, session_factory, secrets())
    finally:
        lock.release()
