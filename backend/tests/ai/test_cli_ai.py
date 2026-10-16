"""`ai status`, `ai test` and `ai usage`, against fake servers and a temporary database."""

import socket
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import cli_ai
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.cli import main
from app.cli_ai import AiCommandError, UsageOptions, run_ai_status, run_ai_test, run_ai_usage
from app.config import Settings, get_settings
from app.db.models import AICallLog
from app.db.settings_store import set_setting
from tests.ai.fake_server import FakeServer, Reply, fixture_reply

ServerFactory = Callable[..., FakeServer]
KEY = "gsk_test_0123456789abcdefghij"


class Capture:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str = "") -> None:
        self.lines.append(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _settings(**kwargs: str | None) -> Settings:
    return Settings(_env_file=None, groq_api_key=KEY, **kwargs)  # type: ignore[arg-type]


def _providers(groq: FakeServer | None = None, ollama: FakeServer | str | None = None) -> dict:
    ollama_url = ollama.base_url if isinstance(ollama, FakeServer) else ollama
    return {
        "groq": GroqProvider(KEY if groq else None, base_url=groq.base_url if groq else "http://x"),
        "ollama": OllamaProvider(ollama_url),
    }


def _rows(engine: Engine) -> list[AICallLog]:
    with Session(engine) as session:
        return list(session.scalars(select(AICallLog).order_by(AICallLog.id)))


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --- status -----------------------------------------------------------------------------------


def test_status_without_any_configuration(db_url: str) -> None:
    out = Capture()
    assert run_ai_status(db_url, _settings(), _providers(), out) == cli_ai.EXIT_OK
    assert out.text.count("not configured") == 2
    assert "Nothing is configured" in out.text and "degraded mode" in out.text
    assert "gemini > groq > ollama" in out.text  # the default order
    assert "gemini  not available yet" in out.text


def test_status_shows_models_and_order_but_never_a_key_or_an_address(
    db_url: str, make_server: ServerFactory
) -> None:
    ollama = make_server()
    out = Capture()
    run_ai_status(db_url, _settings(), _providers(make_server(), ollama), out)

    assert "text: openai/gpt-oss-20b, transcription: whisper-large-v3" in out.text
    assert "text: gemma3:4b" in out.text
    assert "  groq    configured" in out.text and "  ollama  configured" in out.text
    assert "#2" in out.text and "#3" in out.text
    for secret in (KEY, KEY[-4:], "127.0.0.1", str(ollama.base_url.rsplit(":", 1)[1])):
        assert secret not in out.text
    assert "cooldown" not in out.text.lower()  # health is per process: never shown as information


def test_status_with_ai_turned_off(db_url: str, engine: Engine) -> None:
    with Session(engine) as session:
        set_setting(session, "ai_provider_order", [])
        session.commit()
    out = Capture()
    run_ai_status(db_url, _settings(), _providers(), out)
    assert "AI is turned off" in out.text and "not in the order" in out.text


def test_status_with_a_custom_order(db_url: str, engine: Engine) -> None:
    with Session(engine) as session:
        set_setting(session, "ai_provider_order", ["ollama", "groq"])
        session.commit()
    out = Capture()
    run_ai_status(db_url, _settings(), _providers(), out)
    assert "ollama > groq" in out.text and "#1" in out.text


def test_status_without_a_database_uses_the_default_order(tmp_path: Path) -> None:
    out = Capture()
    run_ai_status(
        f"sqlite:///{(tmp_path / 'missing.sqlite3').as_posix()}", _settings(), _providers(), out
    )
    assert "No database yet" in out.text and "gemini > groq > ollama" in out.text
    assert not (tmp_path / "missing.sqlite3").exists()  # looking must not create it


def test_status_leaves_the_database_untouched(db_url: str, tmp_path: Path) -> None:
    path = Path(db_url.removeprefix("sqlite:///"))
    before = path.read_bytes()
    run_ai_status(db_url, _settings(), _providers(), Capture())
    assert path.read_bytes() == before


# --- test -------------------------------------------------------------------------------------


def test_every_configured_provider_is_tested_and_logged(
    db_url: str, engine: Engine, make_server: ServerFactory
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    out = Capture()

    code = run_ai_test(db_url, _settings(), _providers(groq, ollama), out=out)

    assert code == cli_ai.EXIT_OK
    assert "groq: ok (openai/gpt-oss-20b," in out.text and "tokens in/out 96/14" in out.text
    assert "ollama: ok (gemma3:4b," in out.text and "tokens in/out 57/12" in out.text
    assert " ms" in out.text
    assert "recorded in ai_call_log" in out.text and "free quota" in out.text
    rows = _rows(engine)
    assert [(r.provider, r.task, r.success) for r in rows] == [
        ("groq", "connection_test", True),
        ("ollama", "connection_test", True),
    ]
    assert KEY not in out.text


def test_a_failing_provider_gives_exit_1_and_the_others_still_run(
    db_url: str, make_server: ServerFactory
) -> None:
    groq = make_server(fixture_reply("groq", "error_401", status=401))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    out = Capture()

    code = run_ai_test(db_url, _settings(), _providers(groq, ollama), out=out)

    assert code == cli_ai.EXIT_FAILED
    assert "groq: FAILED unavailable (auth)" in out.text
    assert "last error auth HTTP 401" in out.text
    assert "Invalid API Key" in out.text  # the service's own explanation
    assert "ollama: ok" in out.text
    assert KEY not in out.text


def test_a_hostile_error_message_cannot_leak_the_key_through_the_cli(
    db_url: str, make_server: ServerFactory
) -> None:
    groq = make_server(
        Reply(status=401, body={"error": {"message": f"rejected {KEY} (Bearer {KEY})"}})
    )
    out = Capture()
    run_ai_test(db_url, _settings(), _providers(groq), out=out)
    assert KEY not in out.text and "***" in out.text


def test_a_rate_limited_provider_is_reported_after_its_retries(
    db_url: str, make_server: ServerFactory
) -> None:
    groq = make_server(
        fixture_reply("groq", "error_429_rpd", status=429, headers={"retry-after": "5"})
    )
    out = Capture()
    code = run_ai_test(db_url, _settings(), _providers(groq), provider="groq", out=out)
    assert code == cli_ai.EXIT_FAILED
    assert "unavailable (quota)" in out.text and "last error quota_exhausted HTTP 429" in out.text
    assert len(groq.requests) == 1  # a daily quota is not retried


def test_provider_option_tests_only_that_provider(db_url: str, make_server: ServerFactory) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    code = run_ai_test(
        db_url, _settings(), _providers(groq, ollama), provider="ollama", out=Capture()
    )
    assert code == cli_ai.EXIT_OK and groq.requests == [] and len(ollama.requests) == 1


def test_ollama_not_running_is_reported_as_a_network_problem(db_url: str) -> None:
    out = Capture()
    providers = _providers(None, f"http://127.0.0.1:{_closed_port()}")
    code = run_ai_test(db_url, _settings(), providers, out=out)
    assert code == cli_ai.EXIT_FAILED
    assert "ollama: FAILED unavailable (network)" in out.text and "refused" in out.text


def test_an_answer_that_does_not_match_the_schema_is_incomplete(
    db_url: str, make_server: ServerFactory
) -> None:
    body = {"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
    groq = make_server(Reply(body=body))
    out = Capture()
    code = run_ai_test(db_url, _settings(), _providers(groq), out=out)
    assert code == cli_ai.EXIT_FAILED and "FAILED incomplete" in out.text


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"provider": "gemini"}, "not available yet"),
        ({"provider": "ollama"}, "ollama is not configured"),
        ({"provider": "nope"}, "Unknown provider"),
    ],
)
def test_usage_errors_exit_before_any_call(
    db_url: str, make_server: ServerFactory, kwargs: dict, fragment: str
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    with pytest.raises(AiCommandError, match=fragment):
        run_ai_test(db_url, _settings(), _providers(groq), out=Capture(), **kwargs)
    assert groq.requests == []


def test_nothing_configured_is_a_usage_error(db_url: str) -> None:
    with pytest.raises(AiCommandError, match="Nothing is configured"):
        run_ai_test(db_url, _settings(), _providers(), out=Capture())


def test_a_missing_database_is_refused_and_not_created(tmp_path: Path) -> None:
    target = tmp_path / "missing.sqlite3"
    with pytest.raises(AiCommandError, match="db upgrade"):
        run_ai_test(f"sqlite:///{target.as_posix()}", _settings(), _providers(), out=Capture())
    assert not target.exists()


def test_a_database_that_is_not_up_to_date_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "old.sqlite3"
    sqlite3.connect(target).close()  # an empty file: no schema at all
    with pytest.raises(AiCommandError, match="not up to date"):
        run_ai_test(f"sqlite:///{target.as_posix()}", _settings(), _providers(), out=Capture())


def test_no_connection_stays_open_during_a_call(
    db_url: str, engine: Engine, make_server: ServerFactory
) -> None:
    """While the provider is being called the database must be free for other writers (D-038)."""

    def handler(_received) -> Reply:  # runs in the server thread, during the client's call
        with sqlite3.connect(db_url.removeprefix("sqlite:///"), timeout=0.5) as other:
            other.execute("BEGIN IMMEDIATE")  # would fail with 'database is locked' if held
            other.rollback()
        return fixture_reply("groq", "chat_ok")

    groq = make_server(handler=handler)
    assert run_ai_test(db_url, _settings(), _providers(groq), out=Capture()) == cli_ai.EXIT_OK


# --- test --audio -----------------------------------------------------------------------------


def _wav(tmp_path: Path, size: int = 64) -> Path:
    path = tmp_path / "essai.wav"
    path.write_bytes(b"RIFF" + b"\x00" * size)
    return path


def test_audio_is_transcribed_and_the_text_is_shown(
    db_url: str, engine: Engine, make_server: ServerFactory, tmp_path: Path
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"), fixture_reply("groq", "transcription_ok"))
    out = Capture()

    code = run_ai_test(db_url, _settings(), _providers(groq), audio=_wav(tmp_path), out=out)

    assert code == cli_ai.EXIT_OK
    assert "transcript: Hello, this is a short test of my English." in out.text
    assert [r.task for r in _rows(engine)] == ["connection_test", "transcription"]
    assert groq.requests[1].path == "/audio/transcriptions"
    assert b'filename="essai.wav"' in groq.requests[1].body
    assert b"Content-Type: audio/wav" in groq.requests[1].body


def test_silence_is_reported_as_no_speech(
    db_url: str, make_server: ServerFactory, tmp_path: Path
) -> None:
    groq = make_server(
        fixture_reply("groq", "chat_ok"), fixture_reply("groq", "transcription_silence")
    )
    out = Capture()
    run_ai_test(db_url, _settings(), _providers(groq), audio=_wav(tmp_path), out=out)
    assert "transcript: (no speech recognised)" in out.text


def test_a_clip_over_the_limit_fails_cleanly_without_an_upload(
    db_url: str, make_server: ServerFactory, tmp_path: Path
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    out = Capture()
    big = _wav(tmp_path, size=25 * 1024 * 1024)
    code = run_ai_test(db_url, _settings(), _providers(groq), audio=big, out=out)
    assert code == cli_ai.EXIT_FAILED
    assert "bad_request" in out.text and "at most 25 MB" in out.text
    assert len(groq.requests) == 1  # only the text test reached the server


@pytest.mark.parametrize(
    ("provider", "fragment"),
    [("ollama", "Only Groq transcribes"), (None, "--audio needs Groq")],
)
def test_audio_needs_groq(
    db_url: str, make_server: ServerFactory, tmp_path: Path, provider: str | None, fragment: str
) -> None:
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    with pytest.raises(AiCommandError, match=fragment):
        run_ai_test(
            db_url, _settings(), _providers(None, ollama),
            provider=provider, audio=_wav(tmp_path), out=Capture(),
        )  # fmt: skip
    assert ollama.requests == []


def test_an_unreadable_audio_file_is_a_usage_error(db_url: str, make_server: ServerFactory) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    with pytest.raises(AiCommandError, match="Cannot read the audio file"):
        run_ai_test(db_url, _settings(), _providers(groq), audio=Path("nowhere.wav"), out=Capture())
    assert groq.requests == []


def test_a_non_ascii_transcript_does_not_break_the_console(
    db_url: str, make_server: ServerFactory, tmp_path: Path
) -> None:
    body = {"text": "café ☕ 日本語"}
    groq = make_server(fixture_reply("groq", "chat_ok"), Reply(body=body))
    out = Capture()
    run_ai_test(db_url, _settings(), _providers(groq), audio=_wav(tmp_path), out=out)
    assert "café ☕ 日本語" in out.text


# --- usage ------------------------------------------------------------------------------------


def test_usage_lists_the_calls_per_day_provider_and_model(
    db_url: str, engine: Engine, make_server: ServerFactory
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    ollama = make_server(fixture_reply("ollama", "error_generic", status=500))
    run_ai_test(db_url, _settings(), _providers(groq, ollama), out=Capture(), sleep=lambda _s: None)

    out = Capture()
    code = run_ai_usage(db_url, out=out)

    assert code == cli_ai.EXIT_OK
    assert (
        f"Study day {datetime.now(UTC).date().isoformat()}" in out.text or "Study day" in out.text
    )
    assert "groq/openai/gpt-oss-20b: 1 requests, 1 ok, errors -, tokens 96/14" in out.text
    assert "ollama/gemma3:4b: 3 requests, 0 ok, errors transient=3" in out.text  # 500 is retried
    assert "retries and repairs included" in out.text


def test_usage_is_empty_without_calls_and_respects_days(db_url: str, engine: Engine) -> None:
    out = Capture()
    run_ai_usage(db_url, UsageOptions(days=3), out)
    assert "No AI request recorded in the last 3 study day(s)." in out.text


def test_usage_only_looks_back_the_requested_days(
    db_url: str, engine: Engine, make_server: ServerFactory
) -> None:
    run_ai_test(
        db_url,
        _settings(),
        _providers(make_server(fixture_reply("groq", "chat_ok"))),
        out=Capture(),
    )
    later = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    out = Capture()
    run_ai_usage(db_url, UsageOptions(days=7, now=later), out)
    assert "No AI request recorded" in out.text  # a year later, nothing in the last 7 days


def test_usage_is_read_only(db_url: str, engine: Engine) -> None:
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(AICallLog))
    run_ai_usage(db_url, out=Capture())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AICallLog)) == before


# --- Through `python -m app` ------------------------------------------------------------------


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, db_url: str) -> str:
    """The CLI on the temporary database, with no AI configured and the owner's .env ignored
    (an environment variable, even an empty one, wins over `.env`)."""
    monkeypatch.setenv("VOCAB_DATABASE_URL", db_url)
    for name in ("VOCAB_GEMINI_API_KEY", "VOCAB_GROQ_API_KEY", "VOCAB_OLLAMA_BASE_URL"):
        monkeypatch.setenv(name, "")
    for name in ("VOCAB_GROQ_TEXT_MODEL", "VOCAB_GROQ_TRANSCRIPTION_MODEL", "VOCAB_OLLAMA_MODEL"):
        monkeypatch.setenv(name, "")
    monkeypatch.delenv("VOCAB_DEMO", raising=False)
    get_settings.cache_clear()
    yield db_url
    get_settings.cache_clear()


def test_main_status_and_usage_exit_0(cli_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ai", "status"]) == 0
    assert "Nothing is configured" in capsys.readouterr().out
    assert main(["ai", "usage", "--days", "2"]) == 0
    assert "No AI request recorded in the last 2" in capsys.readouterr().out


def test_main_test_without_configuration_exits_2(
    cli_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ai", "test"]) == 2
    captured = capsys.readouterr()
    assert "Nothing is configured" in captured.err and captured.out == ""


def test_main_refuses_demo_for_test_and_usage(
    cli_env: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `--demo` and an explicit database URL are exclusive by design: use a data folder instead.
    monkeypatch.delenv("VOCAB_DATABASE_URL")
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VOCAB_DEMO", "0")  # `--demo` sets it to 1: this makes the test undo it
    for command in ("test", "usage"):
        assert main(["--demo", "ai", command]) == 2
        assert "personal database" in capsys.readouterr().err
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "argv",
    [
        ["ai", "test", "--provider", "nope"],
        ["ai", "usage", "--days", "0"],
        ["ai", "usage", "--days", "x"],
    ],
)
def test_main_rejects_bad_arguments_with_exit_2(
    cli_env: str, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2


def test_main_status_with_a_key_never_prints_it(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VOCAB_GROQ_API_KEY", KEY)
    monkeypatch.setenv("VOCAB_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    get_settings.cache_clear()
    assert main(["ai", "status"]) == 0
    output = capsys.readouterr()
    assert "  groq    configured" in output.out and "  ollama  configured" in output.out
    assert KEY not in output.out + output.err and "11434" not in output.out


def test_main_simulate_still_works(cli_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ai", "simulate"]) == 0
    assert "== 1. A 429 with Retry-After" in capsys.readouterr().out
