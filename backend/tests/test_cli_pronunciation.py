"""`speech assess` and `speech shadow --assess` with a fake provider (cli_speech.py)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import cli_speech
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.pronunciation import (
    PhonemeScore,
    PronunciationAssessmentOutput,
    WordScore,
)
from app.ai.types import Capability, ErrorKind
from app.cli import main
from app.config import Settings
from app.db.models import ErrorEvent, PronunciationResult
from app.db.settings_store import set_setting
from tests.audio_support import WEBM, wav
from tests.speech_support import TARGET, heard

CAPS = (Capability.TRANSCRIPTION, Capability.PRONUNCIATION_ASSESSMENT)
OUTPUT = PronunciationAssessmentOutput(
    status="ok",
    accuracy=78,
    fluency=84,
    completeness=90,
    pronunciation=74.5,
    words=[
        WordScore(word="We", accuracy=95, error_type="None"),
        WordScore(
            word="fixed",
            accuracy=40,
            error_type="Mispronunciation",
            phonemes=[
                PhonemeScore(phoneme="k", accuracy=12),
                PhonemeScore(phoneme="s", accuracy=70),
            ],
        ),
        WordScore(word="effects", accuracy=0, error_type="Omission"),
    ],
)


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "take.wav"
    path.write_bytes(wav(1.0))
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def on(engine: Engine) -> None:
    with Session(engine) as session:
        set_setting(session, "pronunciation_assessment", "azure")
        session.commit()


def factory_for(*script: Success | Failure) -> tuple[Callable[[Engine], Gateway], FakeProvider]:
    provider = FakeProvider("fake", script, capabilities=CAPS)

    def build(engine: Engine) -> Gateway:
        return Gateway(
            {"fake": provider},
            session_factory=lambda: Session(engine),
            provider_order=lambda: ["fake"],
            sleep=lambda _: None,
        )

    return build, provider


def assessed(output: PronunciationAssessmentOutput = OUTPUT) -> Success:
    return Success(content="", assessment=output)


def shadow(db_url, settings, clip, build, **kwargs) -> int:
    return cli_speech.run_speech_shadow(
        db_url, settings, clip, target=TARGET, duration=1.0, gateway_factory=build, **kwargs
    )


def test_shadow_with_assess_prints_the_scores(
    db_url, engine, settings, clip, on, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard(), assessed())
    assert shadow(db_url, settings, clip, build, assess=True) == 0
    out = capsys.readouterr().out
    assert "overall 74.5, accuracy 78, fluency 84, completeness 90" in out
    assert "fixed: 40  [Mispronunciation]" in out and "effects: 0  [Omission]" in out
    assert "We: 95\n" in out  # a correct word carries no tag
    assert "Weakest sounds: k (fixed, 12), s (fixed, 70)" in out
    assert "Mispronounced 1, omitted 1, inserted 0." in out
    assert "automatic estimate, not a teacher's judgment" in out
    assert provider.assessments[0].reference_text == TARGET and provider.calls == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PronunciationResult)) == 1
        assert session.scalar(select(func.count()).select_from(ErrorEvent)) == 0


def test_assess_a_stored_shadowing_later(
    db_url, settings, clip, on, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(heard(), assessed())
    assert shadow(db_url, settings, clip, build) == 0
    capsys.readouterr()
    assert cli_speech.run_speech_assess(db_url, settings, 1, gateway_factory=build) == 0
    assert "Pronunciation (0-100): overall 74.5" in capsys.readouterr().out
    # A second time: refused (exit 2), nothing sent.
    code = cli_speech.run_speech_assess(db_url, settings, 1, gateway_factory=build)
    assert code == 2 and "already assessed" in capsys.readouterr().err


def test_a_silent_take_exits_0_with_a_message(
    db_url, settings, clip, on, capsys: pytest.CaptureFixture[str]
) -> None:
    silence = PronunciationAssessmentOutput(status="silence")
    build, _ = factory_for(heard(), assessed(silence))
    assert shadow(db_url, settings, clip, build, assess=True) == 0
    assert "nothing was heard (silence), no score" in capsys.readouterr().out


def test_an_unavailable_service_exits_1_and_can_be_retried(
    db_url, settings, clip, on, capsys: pytest.CaptureFixture[str]
) -> None:
    build, _ = factory_for(heard(), Failure(ErrorKind.AUTH, status_code=401))
    assert shadow(db_url, settings, clip, build, assess=True) == 1
    err = capsys.readouterr().err
    assert "unavailable (auth)" in err and "speech assess 1" in err
    retry, _ = factory_for(assessed())
    assert cli_speech.run_speech_assess(db_url, settings, 1, gateway_factory=retry) == 0


def test_the_setting_off_is_a_usage_error_before_anything_is_stored(
    db_url, engine, settings, clip, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(heard(), assessed())
    assert shadow(db_url, settings, clip, build, assess=True) == 2
    assert "Pronunciation assessment is off" in capsys.readouterr().err
    assert provider.calls == 0
    assert not (settings.resolved_data_dir / "audio").exists()
    # Without --assess the shadowing works as before; `assess` then refuses.
    assert shadow(db_url, settings, clip, build) == 0
    capsys.readouterr()
    assert cli_speech.run_speech_assess(db_url, settings, 1, gateway_factory=build) == 2
    assert "off" in capsys.readouterr().err
    assert provider.assessments == []


def test_usage_errors_exit_2(db_url, settings, clip, on, tmp_path, capsys) -> None:
    build, provider = factory_for(heard())
    assert cli_speech.run_speech_assess(db_url, settings, 99, gateway_factory=build) == 2
    assert "no production 99" in capsys.readouterr().err
    webm = tmp_path / "take.webm"
    webm.write_bytes(WEBM)
    assert shadow(db_url, settings, webm, build) == 0  # stored, transcribed
    capsys.readouterr()
    assert cli_speech.run_speech_assess(db_url, settings, 1, gateway_factory=build) == 2
    assert "WAV" in capsys.readouterr().err
    assert provider.assessments == []


def test_a_failed_transcription_still_keeps_the_assessment_for_later(
    db_url, settings, clip, on, capsys: pytest.CaptureFixture[str]
) -> None:
    build, provider = factory_for(Failure(ErrorKind.NETWORK))
    assert shadow(db_url, settings, clip, build, assess=True) == 1
    err = capsys.readouterr().err
    assert "Not assessed: the transcription failed" in err and provider.assessments == []


def test_render_assessment_handles_missing_numbers() -> None:
    text = cli_speech.render_assessment(
        {
            "status": "ok",
            "provider": "azure",
            "model": "pa-rest-v1",
            "overall": {"accuracy": None},
            "words": [{"word": "x", "accuracy": None, "error_type": "Insertion"}],
        }
    )
    assert "overall -, accuracy -" in text and "x: -  [Insertion]" in text


def test_through_main_the_argument_is_checked(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["speech", "assess", "zero"])
    assert caught.value.code == 2
