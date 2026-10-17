"""`python -m app write correct` (M5.a1): the example paragraph, degraded mode, exit codes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_write
from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import ErrorEvent, ProductionAttempt
from tests.conftest import sqlite_url
from tests.correction_support import EXAMPLE_FILE, correction_output, output_for
from tests.library_support import count


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    yield path
    get_settings.cache_clear()


def _gateway(provider: FakeProvider):  # type: ignore[no-untyped-def]
    def build(engine: Engine) -> Gateway:
        return Gateway(
            {provider.name: provider},
            session_factory=lambda: Session(engine, expire_on_commit=False),
            provider_order=lambda: [provider.name],
            sleep=lambda _s: None,
        )

    return build


def _count(path: Path, model: type) -> int:
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            return count(session, model)
    finally:
        engine.dispose()


def _run(db_file: Path, provider: FakeProvider, file: Path, **kwargs: object) -> int:
    return cli_write.run_write_correct(
        sqlite_url(db_file),
        Settings(),
        file,
        gateway_factory=_gateway(provider),
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_example_files_exist_and_match_the_acceptance_text() -> None:
    assert EXAMPLE_FILE.read_text(encoding="utf-8").startswith(
        "Last year I moved to Yaoundé to start my master's degree."
    )
    assert "I lived in campus" in EXAMPLE_FILE.read_text(encoding="utf-8")


def test_the_paragraph_is_corrected_and_the_errors_listed(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [Success(content=correction_output())])
    assert _run(db_file, fake, EXAMPLE_FILE, prompt="My new life.") == 0
    out = capsys.readouterr().out
    assert "Corrected: 2 error(s)." in out
    assert "grammar.preposition.fixed_expression" in out and "in campus -> on campus" in out
    assert "grammar.tense.past_simple_vs_present_perfect" in out
    assert "Corrected text:" in out and "More natural:" in out
    assert (_count(db_file, ProductionAttempt), _count(db_file, ErrorEvent)) == (1, 2)
    assert main(["errors", "list"]) == 0
    assert "Errors 1-2 of 2" in capsys.readouterr().out


def test_naturalness_notes_are_printed_apart_from_the_errors(
    db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "I have the intention to work in a bank."
    file = tmp_path / "text.txt"
    file.write_text(text, encoding="utf-8")
    note = {
        "sentence_index": 1,
        "text": "I have the intention to",
        "suggestion": "I intend to",
        "note": "Correct, but a native speaker says 'I plan to' or 'I intend to'.",
    }
    sentence = {"index": 1, "corrected": text, "status": "unnatural"}
    fake = FakeProvider(
        "fake",
        [Success(content=output_for(text, naturalness_notes=[note], sentences=[sentence]))],
    )
    assert _run(db_file, fake, file) == 0
    out = capsys.readouterr().out
    assert "Corrected: 0 error(s)." in out and "1 naturalness note(s) (not errors):" in out
    assert "I have the intention to  ->  I intend to" in out
    assert _count(db_file, ErrorEvent) == 0


def test_without_a_provider_the_text_is_kept_and_the_exit_code_is_1(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [], configured=False)
    assert _run(db_file, fake, EXAMPLE_FILE) == 1
    err = capsys.readouterr().err
    assert "unavailable (no_provider_configured)" in err and "Production #1 is kept" in err
    assert (_count(db_file, ProductionAttempt), _count(db_file, ErrorEvent)) == (1, 0)


def test_usage_errors(db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeProvider("fake", [Success(content=correction_output())])
    assert _run(db_file, fake, tmp_path / "missing.txt") == 2
    assert "Cannot read" in capsys.readouterr().err
    empty = tmp_path / "empty.txt"
    empty.write_text("  \n", encoding="utf-8")
    assert _run(db_file, fake, empty) == 2
    assert "text is empty" in capsys.readouterr().err
    long = tmp_path / "long.txt"
    long.write_text("Yes. " * 41, encoding="utf-8")
    assert _run(db_file, fake, long) == 2
    assert _count(db_file, ProductionAttempt) == 0
    assert fake.calls == 0


def test_the_command_is_registered(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["write", "correct", "--help"])
    assert caught.value.code == 0
    assert "--file" in capsys.readouterr().out
