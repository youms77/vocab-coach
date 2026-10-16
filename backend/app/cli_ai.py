"""`python -m app ai status | test | usage`: look at the real AI providers from the terminal.

- `status`: which providers are configured, their models, the order. Reads the order read-only and
  never prints a key (not even its last characters) nor a server address.
- `test`: one real call per configured provider through the gateway (`connection_test`, pinned to
  the provider), and optionally one Whisper transcription. These calls use a little of the free
  quota and write rows in `ai_call_log` of the personal database: the output says so.
- `usage`: what `ai_call_log` holds, per study day, provider and model. Read-only.

No session is open while a provider is called (D-038): the database is only checked first, and the
gateway writes its own rows afterwards.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import Provider
from app.ai.redact import clean_message
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AiResult, AiStatus, AudioClip, Capability
from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.models import AICallLog
from app.db.settings_store import get_setting
from app.domain.settings_defaults import KNOWN_AI_PROVIDERS, default_for
from app.services.ai_usage import ai_usage_for_day, study_day_now

EXIT_OK = 0
EXIT_FAILED = 1  # a test failed
EXIT_USAGE = 2  # nothing configured, bad arguments, no database

MESSAGE_LIMIT = 300
MAX_AUDIO_FILE_BYTES = 200 * 1024 * 1024  # never read more than this into memory
AUDIO_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}

Out = Callable[[str], None]


class AiCommandError(Exception):
    """The command cannot run (usage error); the message tells the user what to do. Exit code 2."""


def _open_database(url: str) -> Engine:
    """An engine on a database that exists and is up to date (as `plan today` requires)."""
    db_file = sqlite_file(url)
    if db_file is not None and not db_file.exists():
        raise AiCommandError(f"No database at {db_file}. Run `python -m app db upgrade` first.")
    engine = create_db_engine(url)
    try:
        if not migrate.schema_status(engine).at_head:
            raise AiCommandError("The database is not up to date. Run `python -m app db upgrade`.")
    except Exception:
        engine.dispose()
        raise
    return engine


def _mask(value: str, settings: Settings) -> str:
    return clean_message(value, settings.secret_values(), MESSAGE_LIMIT)


# --- status -----------------------------------------------------------------------------------


def run_ai_status(
    url: str, settings: Settings, providers: Mapping[str, Provider], out: Out = print
) -> int:
    order, note = _read_order(url)
    if note:
        out(note)
    if order:
        out(f"AI providers, in the order they are tried: {' > '.join(order)}")
    else:
        out("AI is turned off: the `ai_provider_order` setting is empty, so no provider is called.")
    out("")
    rows = []
    for name in KNOWN_AI_PROVIDERS:
        provider = providers.get(name)
        if provider is None:
            rows.append((name, "not available yet", "arrives in M2.b2", "-"))
            continue
        configured = "configured" if provider.is_configured() else "not configured"
        models = ", ".join(
            f"{capability.value}: {provider.model_for(capability)}"
            for capability in Capability
            if capability in provider.capabilities
        )
        rank = f"#{order.index(name) + 1}" if name in order else "not in the order"
        rows.append((name, configured, models, rank))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        out("  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))
    if not any(p.is_configured() for p in providers.values()):
        out("")
        out("Nothing is configured: the app runs without AI (degraded mode). See the README,")
        out("section Configuration, to add a free Groq key or a local Ollama server.")
    return EXIT_OK


def _read_order(url: str) -> tuple[list[str], str | None]:
    """The `ai_provider_order` setting, read-only; the default (with a note) without a database."""
    default = list(default_for("ai_provider_order"))
    db_file = sqlite_file(url)
    if db_file is not None and not db_file.exists():
        return default, "(No database yet: showing the default order.)"
    engine = create_db_engine(url)
    try:
        if not migrate.schema_status(engine).at_head:
            return default, "(The database is not up to date: showing the default order.)"
        with Session(engine) as session:
            session.execute(text("PRAGMA query_only = ON"))
            try:
                return list(get_setting(session, "ai_provider_order")), None
            finally:
                session.rollback()
    finally:
        engine.dispose()


# --- test -------------------------------------------------------------------------------------


def run_ai_test(
    url: str,
    settings: Settings,
    providers: Mapping[str, Provider],
    *,
    provider: str | None = None,
    audio: Path | None = None,
    out: Out = print,
    sleep: Callable[[float], None] = time.sleep,  # tests pass a no-op
) -> int:
    engine = _open_database(url)
    try:
        targets = _targets(providers, provider)
        clip = _load_clip(audio, providers, provider) if audio is not None else None
        gateway = Gateway(
            providers,
            session_factory=lambda: Session(engine, expire_on_commit=False),
            provider_order=lambda: list(KNOWN_AI_PROVIDERS),
            secrets=settings.secret_values,
            sleep=sleep,
        )
        out(f"Testing {', '.join(targets)}: one real request each (a retry may add one).")
        out("")
        failed = 0
        for name in targets:
            out(f"  {name}: calling {providers[name].model_for(Capability.TEXT)} ...")
            failed += not _test_text(gateway, engine, settings, name, out)
        if clip is not None:
            out(f"  groq: transcribing {clip.filename} ...")
            failed += not _test_audio(gateway, engine, settings, clip, out)
        out("")
        out(
            f"These calls were recorded in ai_call_log ({_database_name(url)}) and used a little "
            "of the free quota. `python -m app ai usage` shows them."
        )
        return EXIT_FAILED if failed else EXIT_OK
    finally:
        engine.dispose()


def _targets(providers: Mapping[str, Provider], wanted: str | None) -> list[str]:
    if wanted is not None:
        if wanted not in KNOWN_AI_PROVIDERS:
            raise AiCommandError(
                f"Unknown provider {wanted!r}. Known providers: {', '.join(KNOWN_AI_PROVIDERS)}."
            )
        if wanted not in providers:
            raise AiCommandError(f"{wanted} is not available yet in this version (see ai status).")
        if not providers[wanted].is_configured():
            raise AiCommandError(f"{wanted} is not configured (see ai status and the README).")
        return [wanted]
    configured = [
        name for name in KNOWN_AI_PROVIDERS if name in providers and providers[name].is_configured()
    ]
    if not configured:
        raise AiCommandError(
            "Nothing is configured: no API key or server address was found, so there is "
            "nothing to test. See the README, section Configuration."
        )
    return configured


def _load_clip(path: Path, providers: Mapping[str, Provider], wanted: str | None) -> AudioClip:
    if wanted not in (None, "groq"):
        raise AiCommandError("Only Groq transcribes speech: use --provider groq, or no --provider.")
    groq = providers.get("groq")
    if groq is None or not groq.is_configured():
        raise AiCommandError("--audio needs Groq (Whisper): set VOCAB_GROQ_API_KEY first.")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AiCommandError(f"Cannot read the audio file {path}: {exc.strerror}.") from None
    if size > MAX_AUDIO_FILE_BYTES:
        raise AiCommandError(f"The audio file is {size / 1024 / 1024:.0f} MB: too large to test.")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AiCommandError(f"Cannot read the audio file {path}: {exc.strerror}.") from None
    content_type = AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return AudioClip(data=data, filename=path.name, content_type=content_type)


def _test_text(gateway: Gateway, engine: Engine, settings: Settings, name: str, out: Out) -> bool:
    started = time.perf_counter()
    result = gateway.generate_json(
        "connection_test", {"text": "ping"}, ConnectionTestOutput, pin_provider=name
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    out("    " + _describe(result, name, engine, settings, elapsed_ms))
    return result.status is AiStatus.OK


def _test_audio(
    gateway: Gateway, engine: Engine, settings: Settings, clip: AudioClip, out: Out
) -> bool:
    started = time.perf_counter()
    result = gateway.transcribe(clip, language="en", pin_provider="groq")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    out("    " + _describe(result, "groq", engine, settings, elapsed_ms))
    if result.data is not None:
        out(f"    transcript: {_mask(result.data.text, settings) or '(no speech recognised)'}")
    return result.status is AiStatus.OK


def _describe(
    result: AiResult, name: str, engine: Engine, settings: Settings, elapsed_ms: int
) -> str:
    model = result.model or "?"
    if result.status is AiStatus.OK:
        tokens = ""
        if result.input_tokens is not None or result.output_tokens is not None:
            tokens = f", tokens in/out {result.input_tokens}/{result.output_tokens}"
        return f"{name}: ok ({model}, {elapsed_ms} ms{tokens})"
    code, http_status = _last_error(engine, result.call_id)
    if result.status is AiStatus.INCOMPLETE:
        reason = "the answer did not match the expected schema"
        label = "incomplete"
    else:
        reason = result.reason.value if result.reason else "unavailable"
        label = f"unavailable ({reason})"
    parts = [f"{name}: FAILED {label}", f"model {model}", f"{elapsed_ms} ms"]
    if code:
        parts.append(f"last error {code}" + (f" HTTP {http_status}" if http_status else ""))
    line = ", ".join(parts)
    if result.detail:
        line += f"\n      {_mask(result.detail, settings)}"
    elif result.status is AiStatus.INCOMPLETE:
        line += f"\n      {reason}"
    return line


def _last_error(engine: Engine, call_id: int | None) -> tuple[str | None, int | None]:
    """Error code and HTTP status of the last logged request, read in a short session."""
    if call_id is None:
        return None, None
    with Session(engine) as session:
        row = session.get(AICallLog, call_id)
        return (row.error_code, row.http_status) if row is not None else (None, None)


def _database_name(url: str) -> str:
    db_file = sqlite_file(url)
    return str(db_file) if db_file is not None else "the database"


# --- usage ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageOptions:
    days: int = 7
    now: datetime | None = None  # tests only


def run_ai_usage(url: str, options: UsageOptions = UsageOptions(), out: Out = print) -> int:  # noqa: B008
    engine = _open_database(url)
    try:
        with Session(engine) as session:
            session.execute(text("PRAGMA query_only = ON"))
            try:
                today = study_day_now(session, options.now or datetime.now(UTC))
                found = False
                for back in range(options.days):
                    day = today - timedelta(days=back)
                    usage = ai_usage_for_day(session, day)
                    if not usage.rows:
                        continue
                    found = True
                    out(
                        f"Study day {day.isoformat()}: {usage.requests} request(s), "
                        f"{usage.successes} ok, tokens in/out "
                        f"{usage.input_tokens}/{usage.output_tokens}"
                    )
                    for row in usage.rows:
                        errors = ", ".join(f"{code}={n}" for code, n in row.errors.items()) or "-"
                        average = (
                            f"{row.avg_duration_ms:.0f} ms"
                            if row.avg_duration_ms is not None
                            else "-"
                        )
                        out(
                            f"  {row.provider}/{row.model}: {row.requests} requests, "
                            f"{row.successes} ok, errors {errors}, "
                            f"tokens {row.input_tokens}/{row.output_tokens}, mean {average}"
                        )
                if not found:
                    out(f"No AI request recorded in the last {options.days} study day(s).")
                else:
                    out("")
                    out("Requests count every provider request, retries and repairs included.")
            finally:
                session.rollback()
    finally:
        engine.dispose()
    return EXIT_OK
