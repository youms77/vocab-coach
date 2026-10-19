"""`python -m app speech speak | correct` with the fake provider (cli_speech.py, M6.a2a)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli_speech
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.cli import _build_parser as build_parser
from app.config import Settings
from app.db.models import ErrorEvent, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from tests.speaking_support import PROMPT, SPEECH, speaking_output
from tests.speech_support import heard, wav_bytes

STT = (Capability.TEXT, Capability.TRANSCRIPTION)


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "my speech.wav"
    path.write_bytes(wav_bytes(1.0))
    return path


@pytest.fixture
def settings(tmp_path: Path, engine: Engine) -> Settings:
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    return Settings(data_dir=tmp_path / "data")


def factory_for(
    *script: Success | Failure, configured: bool = True
) -> tuple[Callable[[Engine], Gateway], FakeProvider]:
    provider = FakeProvider("fake", script, capabilities=STT, configured=configured)

    def build(engine: Engine) -> Gateway:
        return Gateway(
            {"fake": provider},
            session_factory=lambda: Session(engine),
            provider_order=lambda: ["fake"],
            sleep=lambda _: None,
        )

    return build, provider


def recordings(settings: Settings) -> list[Path]:
    root = settings.resolved_data_dir / "audio"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def stored(engine: Engine) -> list[ProductionAttempt]:
    with Session(engine) as session:
        return list(session.scalars(select(ProductionAttempt).order_by(ProductionAttempt.id)))


def test_speak_with_a_duration_records_transcribes_and_corrects(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard(SPEECH), Success(content=speaking_output()))
    code = cli_speech.run_speech_speak(
        db_url, settings, clip, prompt=PROMPT, duration=40.0, gateway_factory=build
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    out = captured.out
    assert f"Heard: {SPEECH}" in out
    assert "Corrected: 3 error(s)." in out
    assert "grammar.preposition.fixed_expression" in out and "in campus -> on campus" in out
    assert "study here since two years -> have been studying here for two years" in out
    assert "More natural:" in out and "Structure:" in out
    assert "Connectors you used: so, and" in out
    assert "what speech recognition heard" in out
    [attempt] = stored(engine)
    assert (attempt.kind, attempt.prompt_text) == ("speaking", PROMPT)
    assert len(recordings(settings)) == 1 and provider.calls == 2
    with Session(engine) as session:
        assert {e.source for e in session.scalars(select(ErrorEvent))} == {"speaking"}


def test_speak_without_a_duration_measures_first_and_calls_whisper_once(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(
        heard(SPEECH, duration_s=41.0), Success(content=speaking_output())
    )
    code = cli_speech.run_speech_speak(db_url, settings, clip, gateway_factory=build)
    assert code == 0, capsys.readouterr().err
    assert len(provider.transcriptions) == 1
    [attempt] = stored(engine)
    assert attempt.audio_seconds == 41.0


def test_speak_without_a_duration_and_without_a_key_stores_nothing(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(configured=False)
    code = cli_speech.run_speech_speak(db_url, settings, clip, gateway_factory=build)
    assert code == 2 and "--duration" in capsys.readouterr().err
    assert stored(engine) == [] and recordings(settings) == []


def test_speak_without_a_key_keeps_the_recording_then_transcribe_and_correct(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    offline, _ = factory_for(configured=False)
    code = cli_speech.run_speech_speak(
        db_url, settings, clip, duration=40.0, gateway_factory=offline
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "unavailable (no_provider_configured)" in err
    assert "speech transcribe 1" in err and "speech correct 1" in err
    assert len(recordings(settings)) == 1
    # Not transcribed yet: correct refuses before any call.
    assert cli_speech.run_speech_correct(db_url, settings, 1, gateway_factory=offline) == 2
    assert "transcribe it first" in capsys.readouterr().err
    online, _ = factory_for(heard(SPEECH), Success(content=speaking_output()))
    assert cli_speech.run_speech_transcribe(db_url, settings, 1, gateway_factory=online) == 0
    capsys.readouterr()
    assert cli_speech.run_speech_correct(db_url, settings, 1, gateway_factory=online) == 0
    assert "Corrected: 3 error(s)." in capsys.readouterr().out
    # Corrected once only.
    assert cli_speech.run_speech_correct(db_url, settings, 1, gateway_factory=online) == 2


def test_speak_no_correct_then_correct(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard(SPEECH), Success(content=speaking_output()))
    code = cli_speech.run_speech_speak(
        db_url, settings, clip, duration=40.0, correct=False, gateway_factory=build
    )
    assert code == 0 and "speech correct 1" in capsys.readouterr().out
    assert provider.requests == []
    assert cli_speech.run_speech_correct(db_url, settings, 1, gateway_factory=build) == 0


def test_a_failed_correction_keeps_the_production(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(heard(SPEECH), Failure(ErrorKind.NETWORK))
    code = cli_speech.run_speech_speak(db_url, settings, clip, duration=40.0, gateway_factory=build)
    err = capsys.readouterr().err
    assert code == 1 and "speech correct 1" in err
    [attempt] = stored(engine)
    assert attempt.ai_feedback is None and attempt.text == SPEECH


def test_speak_reports_silence(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard("", segments=()))
    code = cli_speech.run_speech_speak(db_url, settings, clip, duration=40.0, gateway_factory=build)
    assert code == 0 and "Nothing was heard" in capsys.readouterr().out
    assert provider.requests == []


def test_speak_refusals(
    db_url: str,
    engine: Engine,
    settings: Settings,
    clip: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build, provider = factory_for(heard(SPEECH))
    text = tmp_path / "speech.txt"
    text.write_text("not audio", encoding="utf-8")
    assert cli_speech.run_speech_speak(db_url, settings, text, gateway_factory=build) == 2
    assert (
        cli_speech.run_speech_speak(db_url, settings, clip, duration=4.0, gateway_factory=build)
        == 2
    )
    assert (
        cli_speech.run_speech_speak(db_url, settings, clip, duration=200.0, gateway_factory=build)
        == 2
    )
    assert (
        cli_speech.run_speech_speak(
            db_url, settings, clip, prompt="p" * 501, duration=40.0, gateway_factory=build
        )
        == 2
    )
    assert cli_speech.run_speech_correct(db_url, settings, 99, gateway_factory=build) == 2
    assert provider.calls == 0 and stored(engine) == []
    capsys.readouterr()


def test_the_parser_knows_the_commands() -> None:
    args = build_parser().parse_args(
        ["speech", "speak", "--file", "a.m4a", "--prompt", "Topic.", "--no-correct"]
    )
    assert (args.speech_command, args.prompt, args.no_correct, args.duration) == (
        "speak",
        "Topic.",
        True,
        None,
    )
    assert build_parser().parse_args(["speech", "correct", "3"]).production_id == 3
