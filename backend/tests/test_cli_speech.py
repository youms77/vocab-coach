"""`python -m app speech shadow | transcribe | compare` with the fake provider (cli_speech.py)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli_speech
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.cli import main
from app.config import Settings, get_settings
from app.db.models import ProductionAttempt
from app.speech.audio_store import AudioStore
from tests.speech_support import HEARD, TARGET, heard, wav_bytes

STT = (Capability.TRANSCRIPTION,)


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "my recording.wav"
    path.write_bytes(wav_bytes(1.0))
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
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


def recordings(settings: Settings, folder: str = "audio") -> list[Path]:
    root = settings.resolved_data_dir / folder
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def productions(engine: Engine) -> list[ProductionAttempt]:
    with Session(engine) as session:
        return list(session.scalars(select(ProductionAttempt).order_by(ProductionAttempt.id)))


# --- compare -------------------------------------------------------------------------------------


def test_compare_needs_no_ai(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_speech.run_speech_compare(
        "We account for regional fixed effects.", "we account for regional fix effect"
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Recognised 4 of 6 words (67%)." in out
    assert "[fixed -> fix] [effects -> effect]" in out
    assert "word 5: 'fixed', heard 'fix'" in out
    assert "not a pronunciation judge" in out


def test_compare_shows_close_and_extra_words(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_speech.run_speech_compare("The colour is grey.", "the the color is gray") == 0
    out = capsys.readouterr().out
    assert "Close spellings, counted as recognised: colour ~ color, grey ~ gray" in out
    assert "Extra words heard: the" in out and "(100%)" in out


@pytest.mark.parametrize(("target", "heard_text"), [("", "x"), ("?!", "x"), ("a" * 401, "a")])
def test_compare_refuses_an_invalid_target(target: str, heard_text: str) -> None:
    assert cli_speech.run_speech_compare(target, heard_text) == 2


def test_compare_refuses_a_heard_text_too_long() -> None:
    assert cli_speech.run_speech_compare("Hello there.", "word " * 401) == 2


def test_compare_through_main(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["speech", "compare", "It's well-known.", "it is well known"]) == 0
    assert "Recognised 2 of 2 words (100%)." in capsys.readouterr().out


# --- shadow --------------------------------------------------------------------------------------


def test_shadow_with_a_duration(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard())
    code = cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, duration=1.0, gateway_factory=build
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    [stored] = recordings(settings)
    assert stored.read_bytes() == clip.read_bytes()
    assert f"Recording: {stored}" in captured.out
    assert "word 5: 'fixed', heard 'fix'" in captured.out
    assert HEARD in captured.out and "not a pronunciation judge" in captured.out
    assert provider.transcriptions[0].audio.filename == stored.name  # not "my recording.wav"
    [attempt] = productions(engine)
    assert (attempt.prompt_text, attempt.audio_seconds) == (TARGET, 3.4)


def test_shadow_without_a_duration_uses_the_provider_measure(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard(duration_s=1.2))
    code = cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, gateway_factory=build
    )
    assert code == 0, capsys.readouterr().err
    assert provider.calls == 1  # transcribed once, stored without a second call
    [attempt] = productions(engine)
    assert attempt.audio_seconds == 1.2


@pytest.mark.parametrize(
    "script",
    [
        (heard(duration_s=None),),  # an answer without duration
        (Failure(ErrorKind.NETWORK),),
    ],
)
def test_shadow_without_any_duration_stores_nothing(
    db_url: str,
    engine: Engine,
    settings: Settings,
    clip: Path,
    capsys: pytest.CaptureFixture[str],
    script: tuple[Success | Failure, ...],
) -> None:
    build, _ = factory_for(*script)
    code = cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, gateway_factory=build
    )
    assert code == 2
    assert "--duration" in capsys.readouterr().err
    assert recordings(settings) == [] and productions(engine) == []


def test_shadow_without_a_key_keeps_the_recording_then_transcribe_works(
    db_url: str, engine: Engine, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(configured=False)
    code = cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, duration=1.0, gateway_factory=build
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "Transcription unavailable (no_provider_configured)" in captured.err
    [attempt] = productions(engine)
    assert f"speech transcribe {attempt.id}" in captured.err
    assert len(recordings(settings)) == 1

    build, _ = factory_for(heard())
    assert (
        cli_speech.run_speech_transcribe(db_url, settings, attempt.id, gateway_factory=build) == 0
    )
    assert "word 5: 'fixed', heard 'fix'" in capsys.readouterr().out
    again = cli_speech.run_speech_transcribe(db_url, settings, attempt.id, gateway_factory=build)
    assert again == 2
    assert "already transcribed" in capsys.readouterr().err


def test_shadow_reports_silence(
    db_url: str, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(heard("", segments=()))
    code = cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, duration=1.0, gateway_factory=build
    )
    assert code == 0
    assert "Nothing was heard (silence)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "changes", "message"),
    [
        ("notes.txt", {}, "not an accepted recording"),
        ("clip.flac", {}, "not an accepted recording"),
        ("missing.wav", {}, "Cannot read"),
        ("clip.wav", {"target": "   "}, "has no word"),
        ("clip.wav", {"duration": 45.0}, "from 0.5 to 30 seconds"),
        ("clip.wav", {"item_id": 99}, "no term 99"),
    ],
)
def test_shadow_refusals(
    db_url: str,
    engine: Engine,
    settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    changes: dict[str, object],
    message: str,
) -> None:
    path = tmp_path / name
    if name != "missing.wav":
        path.write_bytes(wav_bytes(1.0))
    build, provider = factory_for(heard())
    arguments: dict[str, object] = {"target": TARGET, "duration": 1.0} | changes
    code = cli_speech.run_speech_shadow(
        db_url,
        settings,
        path,
        gateway_factory=build,
        **arguments,  # type: ignore[arg-type]
    )
    assert code == 2
    assert message in capsys.readouterr().err
    assert recordings(settings) == [] and productions(engine) == []
    if "item_id" not in changes:
        assert provider.calls == 0  # refused before any AI call


def test_shadow_without_a_database(
    tmp_path: Path, settings: Settings, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{(tmp_path / 'none.sqlite3').as_posix()}"
    assert cli_speech.run_speech_shadow(url, settings, clip, target=TARGET, duration=1.0) == 2
    assert "db upgrade" in capsys.readouterr().err


def test_transcribe_refusals(
    db_url: str, engine: Engine, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(heard())
    assert cli_speech.run_speech_transcribe(db_url, settings, 42, gateway_factory=build) == 2
    assert "no production 42" in capsys.readouterr().err


# --- demo ----------------------------------------------------------------------------------------


def test_the_demo_records_in_its_own_folder(
    db_url: str, tmp_path: Path, clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = Settings(data_dir=tmp_path / "data", demo=True)
    build, _ = factory_for(heard())
    code = cli_speech.run_speech_shadow(
        db_url, demo, clip, target=TARGET, duration=1.0, gateway_factory=build
    )
    assert code == 0
    assert len(recordings(demo, "audio-demo")) == 1 and recordings(demo, "audio") == []


def test_main_passes_the_demo_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clip: Path
) -> None:
    monkeypatch.delenv("VOCAB_DATABASE_URL", raising=False)
    monkeypatch.setenv("VOCAB_DEMO", "0")  # set, so teardown removes what `--demo` writes
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    seen: dict[str, object] = {}

    def spy(url: str, settings: Settings, file: Path, **kwargs: object) -> int:
        seen.update(url=url, root=AudioStore.for_settings(settings).root, file=file, **kwargs)
        return 0

    monkeypatch.setattr(cli_speech, "run_speech_shadow", spy)
    try:
        args = ["--demo", "speech", "shadow", "--file", str(clip), "--target", "Hi there."]
        assert main([*args, "--item", "3", "--duration", "2.5"]) == 0
    finally:
        get_settings.cache_clear()
    assert seen["root"] == (tmp_path / "data").resolve() / "audio-demo"
    assert str(seen["url"]).endswith("vocab-coach-demo.sqlite3")
    assert (seen["file"], seen["target"], seen["item_id"], seen["duration"]) == (
        clip,
        "Hi there.",
        3,
        2.5,
    )


def test_main_needs_a_target(clip: Path) -> None:
    with pytest.raises(SystemExit):
        main(["speech", "shadow", "--file", str(clip)])
