"""`curriculum generate | unit | step | terms | edit` and `speech shadow | speak --unit` on a
temporary database with the fake provider (M8.a2): output and exit codes."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli_curriculum, cli_speech
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import CurriculumUnit, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from tests.conftest import sqlite_url
from tests.curriculum_unit_support import LINES, unit_output
from tests.speaking_support import clean_output
from tests.speech_support import heard, wav_bytes

STT = (Capability.TEXT, Capability.TRANSCRIPTION)
TALK = "I would like this job because I work well in a team."


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    engine = create_db_engine(sqlite_url(path))
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    engine.dispose()
    yield path
    get_settings.cache_clear()


def gateway(*script: Success | Failure) -> Callable[[Engine], Gateway]:
    provider = FakeProvider("fake", script, capabilities=STT)

    def build(engine: Engine) -> Gateway:
        return Gateway(
            {"fake": provider},
            session_factory=lambda: Session(engine),
            provider_order=lambda: ["fake"],
            sleep=lambda _: None,
        )

    return build


def generate(db_file: Path, *script: Success | Failure) -> int:
    return cli_curriculum.run_curriculum_generate(
        sqlite_url(db_file), Settings(), "speaking_scenarios", 1, gateway_factory=gateway(*script)
    )


def start(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["curriculum", "start", "speaking_scenarios"]) == 0
    capsys.readouterr()


def test_generate_prints_the_unit_and_a_failure_keeps_nothing(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generate(db_file, Success(content=unit_output())) == 2  # the track is not started
    assert "Start the track 'speaking_scenarios' first" in capsys.readouterr().err
    start(capsys)
    assert generate(db_file, Failure(ErrorKind.AUTH)) == 1
    err = capsys.readouterr().err
    assert "Nothing was written" in err and "again later" in err
    assert generate(db_file, Success(content=unit_output())) == 0
    out = capsys.readouterr().out
    assert "job_interview_1" in out and "Thank you for having me" in out
    assert "[ ] formulas" in out and "Next: formulas" in out
    assert generate(db_file, Success(content=unit_output())) == 2
    assert "already has its content" in capsys.readouterr().err


def test_unit_step_terms_and_edit(
    db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start(capsys)
    assert generate(db_file, Success(content=unit_output())) == 0
    capsys.readouterr()

    assert main(["curriculum", "unit", "1"]) == 0
    assert "Revision 1" in capsys.readouterr().out
    assert main(["curriculum", "unit", "1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["formulas"][0]["register"] == "neutral"
    assert main(["curriculum", "unit", "9"]) == 2 and "no unit 9" in capsys.readouterr().err

    assert main(["curriculum", "step", "1", "formulas"]) == 0
    assert "marked done" in capsys.readouterr().out
    assert main(["curriculum", "step", "1", "formulas"]) == 0
    assert "already done" in capsys.readouterr().out

    assert main(["curriculum", "terms", "1", "--indices", "0", "1"]) == 0
    assert "2 formula(s) added" in capsys.readouterr().out
    assert main(["curriculum", "terms", "1"]) == 0
    out = capsys.readouterr().out
    assert "7 formula(s) added" in out and "2 skipped" in out

    parts = tmp_path / "parts.json"
    parts.write_text(json.dumps({"shadowing": [0, 2, 4, 6, 9]}), encoding="utf-8")
    assert main(["curriculum", "edit", "1", "--file", str(parts)]) == 0
    assert "revision 2" in capsys.readouterr().out
    parts.write_text(json.dumps({"shadowing": [0, 1]}), encoding="utf-8")
    assert main(["curriculum", "edit", "1", "--file", str(parts)]) == 2
    assert "shadowing" in capsys.readouterr().err
    parts.write_text("[]", encoding="utf-8")
    assert main(["curriculum", "edit", "1", "--file", str(parts)]) == 2
    assert main(["curriculum", "edit", "1", "--file", str(tmp_path / "none.json")]) == 2


def test_shadowing_and_the_final_talk_of_a_unit(
    db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start(capsys)
    assert generate(db_file, Success(content=unit_output())) == 0
    capsys.readouterr()
    clip = tmp_path / "clip.wav"
    clip.write_bytes(wav_bytes(1.0))
    settings = Settings(data_dir=tmp_path / "data")
    url = sqlite_url(db_file)
    assert (
        cli_speech.run_speech_shadow(
            url,
            settings,
            clip,
            target=LINES[0][1],
            duration=3.0,
            unit_id=1,
            gateway_factory=gateway(heard(LINES[0][1], duration_s=3.0)),
        )
        == 0
    )
    missing = cli_speech.run_speech_shadow(
        url,
        settings,
        clip,
        target=LINES[0][1],
        duration=3.0,
        unit_id=77,
        gateway_factory=gateway(heard(LINES[0][1], duration_s=3.0)),
    )
    assert missing == 2 and "no unit 77" in capsys.readouterr().err
    assert (
        cli_speech.run_speech_speak(
            url,
            settings,
            clip,
            duration=30.0,
            unit_id=1,
            gateway_factory=gateway(
                heard(TALK, duration_s=30.0), Success(content=clean_output(TALK))
            ),
        )
        == 0
    )
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            takes = session.scalars(select(ProductionAttempt).order_by(ProductionAttempt.id)).all()
            assert [t.curriculum_unit_id for t in takes] == [1, 1]
            assert (takes[1].prompt_text or "").startswith("You are in an interview")
            assert session.get_one(CurriculumUnit, 1).progress.value == "in_progress"
    finally:
        engine.dispose()
    capsys.readouterr()
    assert main(["curriculum", "unit", "1"]) == 0
    out = capsys.readouterr().out
    assert "line 0: 1 take(s)" in out and "[x] final_task" in out
