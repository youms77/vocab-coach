"""`python -m app consolidation write | speak` (M7.a2): the summary, the exit codes."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli_consolidation, cli_consolidation_attempts
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import ConsolidationTask, LexicalItem
from app.db.taxonomy import sync_taxonomy
from tests.conftest import sqlite_url
from tests.consolidation_deck_support import ready_deck
from tests.consolidation_support import TERMS, TEXT, corrected_output, task_output
from tests.speaking_support import clean_output
from tests.speech_support import heard, wav_bytes

STT = (Capability.TEXT, Capability.TRANSCRIPTION)


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    yield path
    get_settings.cache_clear()


@pytest.fixture
def task_id(db_file: Path) -> int:
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            sync_taxonomy(session)
            deck, _ = ready_deck(session, 10, terms=TERMS, stability=lambda n: 10.0 + n)
            session.commit()
            deck_id = deck.id
    finally:
        engine.dispose()
    provider = FakeProvider(
        "fake", [Success(content=task_output([f"t{i + 1}" for i in range(10)]))]
    )
    assert (
        cli_consolidation.run_consolidation_new(
            sqlite_url(db_file), Settings(), deck_id, count=10, gateway_factory=gateway(provider)
        )
        == 0
    )
    return 1


def gateway(provider: FakeProvider) -> Callable[[Engine], Gateway]:
    def build(engine: Engine) -> Gateway:
        return Gateway(
            {provider.name: provider},
            session_factory=lambda: Session(engine, expire_on_commit=False),
            provider_order=lambda: [provider.name],
            sleep=lambda _s: None,
        )

    return build


def statuses(db_file: Path) -> dict[str, str]:
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            return {i.term: str(i.status) for i in session.scalars(select(LexicalItem))}
    finally:
        engine.dispose()


def task_status(db_file: Path) -> str:
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            return str(session.scalars(select(ConsolidationTask)).one().status)
    finally:
        engine.dispose()


def test_write_corrects_and_activates(
    db_file: Path, task_id: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = tmp_path / "talk.txt"
    text.write_text(TEXT, encoding="utf-8")
    provider = FakeProvider("fake", [Success(content=corrected_output())])
    code = cli_consolidation_attempts.run_consolidation_write(
        sqlite_url(db_file), Settings(), task_id, text, gateway_factory=gateway(provider)
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Corrected: 1 error(s)." in out
    assert "now active (8): shed light on, causal effect" in out
    assert "review card reinforced (1): selection bias" in out
    assert "not used (1): standard error" in out
    assert task_status(db_file) == "accepted"
    assert statuses(db_file)["shed light on"] == "active"


def test_write_failures_and_usage(
    db_file: Path, task_id: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = tmp_path / "talk.txt"
    text.write_text(TEXT, encoding="utf-8")
    down = FakeProvider("fake", [Failure(ErrorKind.NETWORK)])
    code = cli_consolidation_attempts.run_consolidation_write(
        sqlite_url(db_file), Settings(), task_id, text, gateway_factory=gateway(down)
    )
    assert code == 1
    assert "no term changed" in capsys.readouterr().err
    assert set(statuses(db_file).values()) == {"consolidated"}
    missing = cli_consolidation_attempts.run_consolidation_write(
        sqlite_url(db_file), Settings(), task_id, tmp_path / "none.txt"
    )
    assert missing == 2
    assert main(["consolidation", "write", "99", "--file", str(text)]) == 2
    assert "There is no consolidation task 99" in capsys.readouterr().err
    assert (
        main(["consolidation", "write", str(task_id), "--file", str(text.with_suffix(".bin"))]) == 2
    )


def test_write_on_a_closed_task(
    db_file: Path, task_id: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = create_db_engine(sqlite_url(db_file))
    with Session(engine) as session:
        from app.db.base import utcnow
        from app.domain.consolidation import TaskStatus
        from app.services import consolidation

        consolidation.change_status(session, task_id, TaskStatus.DISMISSED, at=utcnow())
        session.commit()
    engine.dispose()
    text = tmp_path / "talk.txt"
    text.write_text(TEXT, encoding="utf-8")
    assert main(["consolidation", "write", str(task_id), "--file", str(text)]) == 2
    assert "This task is closed" in capsys.readouterr().err


def test_speak(
    db_file: Path, task_id: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clip = tmp_path / "talk.wav"
    clip.write_bytes(wav_bytes(1.0))
    spoken = TEXT.split(". ")[0] + "."
    provider = FakeProvider(
        "fake",
        [
            heard(spoken, duration_s=60.0),
            Success(
                content=clean_output(
                    spoken,
                    targets=[{"ref": 0, "used": True, "used_correctly": True, "comment": ""}],
                )
            ),
        ],
        capabilities=STT,
    )
    settings = Settings(data_dir=tmp_path / "data")
    code = cli_consolidation_attempts.run_consolidation_speak(
        sqlite_url(db_file),
        settings,
        task_id,
        clip,
        duration=60.0,
        gateway_factory=gateway(provider),
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Heard: In this reading" in out
    assert "now active (1): shed light on" in out
    assert statuses(db_file)["shed light on"] == "active"


def test_speak_refusals(
    db_file: Path, task_id: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clip = tmp_path / "short.wav"
    clip.write_bytes(wav_bytes(1.0))
    assert (
        main(["consolidation", "speak", str(task_id), "--file", str(clip), "--duration", "5"]) == 2
    )
    assert "20" in capsys.readouterr().err
    assert main(["consolidation", "speak", "99", "--file", str(clip), "--duration", "60"]) == 2
