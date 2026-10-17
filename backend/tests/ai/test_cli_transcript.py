"""`python -m app transcript analyse` (M5.a2): preview, the example transcript, exit codes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_transcript
from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import ErrorEvent, ProductionAttempt
from app.domain.transcript_import import parse_transcript
from tests.conftest import sqlite_url
from tests.library_support import count
from tests.transcript_support import (
    CLEAN_FILE,
    EXAMPLE,
    EXAMPLE_FILE,
    UNLABELLED_FILE,
    example_output,
    output_for,
)


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
    return cli_transcript.run_transcript_analyse(
        sqlite_url(db_file),
        Settings(),
        file,
        gateway_factory=_gateway(provider),
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_example_files_match_the_acceptance_text() -> None:
    parsed = parse_transcript(EXAMPLE)
    mine = parsed.user_text
    assert parsed.suggested_user_label == "You"
    for wrong in ("in campus", "I study here since two years", "Yesterday I have finished"):
        assert wrong in mine
    chatgpt = " ".join(t.text for t in parsed.turns if not t.is_user)
    assert '"in campus"' in chatgpt and '"on campus"' in chatgpt  # ChatGPT quotes and corrects
    assert "[00:" in EXAMPLE and "Uh," in EXAMPLE
    clean = parse_transcript(CLEAN_FILE.read_text(encoding="utf-8"))
    assert clean.suggested_user_label == "You" and "." not in clean.user_text
    assert "um" in clean.user_text and "—" in clean.user_text
    unlabelled = parse_transcript(UNLABELLED_FILE.read_text(encoding="utf-8"))
    assert not unlabelled.labelled and len(unlabelled.turns) == 6


def test_preview_writes_nothing_and_needs_no_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nothing.sqlite3"
    code = cli_transcript.run_transcript_analyse(
        sqlite_url(missing), Settings(), EXAMPLE_FILE, preview=True
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Suggested user label: You" in out
    assert "You (user): 4 turn(s)" in out and "ChatGPT (other): 4 turn(s)" in out
    assert "Your turns (*): 4" in out
    assert not missing.exists()


def test_preview_of_an_unlabelled_file_with_a_mode(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_transcript.run_transcript_analyse(
        "sqlite:///unused.sqlite3",
        Settings(),
        UNLABELLED_FILE,
        mode="alternating-user-second",
        preview=True,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "No speaker labels." in out and "no_speaker_labels" in out
    assert "Your turns (*): 3" in out


def test_the_example_is_recorded_analysed_and_the_errors_printed(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [Success(content=example_output())])
    assert _run(db_file, fake, EXAMPLE_FILE) == 0
    out = capsys.readouterr().out
    assert "Analysed: 3 error(s) in your turns." in out
    assert "grammar.preposition.fixed_expression" in out and "in campus -> on campus" in out
    assert "grammar.preposition.by_for_since" in out
    assert "grammar.tense.past_simple_vs_present_perfect" in out
    assert "transcript" in out
    # The context is sent: the CLI passes the transcript along.
    assert '"before_unit": 2' in fake.requests[0].user
    assert _count(db_file, ErrorEvent) == 3


def test_an_unavailable_ai_keeps_the_transcript_and_exits_1(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [Success(content=output_for([]))], configured=False)
    assert _run(db_file, fake, EXAMPLE_FILE) == 1
    err = capsys.readouterr().err
    assert "could not analyse" in err and "POST /api/productions/1/correct" in err
    assert _count(db_file, ProductionAttempt) == 1 and _count(db_file, ErrorEvent) == 0


def test_usage_errors_exit_2(
    db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [Success(content=example_output())])
    assert _run(db_file, fake, tmp_path / "missing.txt") == 2
    assert _run(db_file, fake, EXAMPLE_FILE, speaker="Jordan") == 2
    assert "unknown_label" in capsys.readouterr().err
    assert _run(db_file, fake, UNLABELLED_FILE) == 2  # no label to suggest, no mode
    assert "--speaker LABEL or --mode" in capsys.readouterr().err
    assert fake.calls == 0 and _count(db_file, ProductionAttempt) == 0


def test_demo_is_refused_for_the_ai_call(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(demo=True)
    fake = FakeProvider("fake", [Success(content=example_output())])
    code = cli_transcript.run_transcript_analyse(
        "sqlite:///unused.sqlite3", settings, EXAMPLE_FILE, gateway_factory=_gateway(fake)
    )
    assert code == 2 and "refused on the demo database" in capsys.readouterr().err
    assert fake.calls == 0


def test_the_command_line_is_wired(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["transcript", "analyse", "--file", str(EXAMPLE_FILE), "--preview"]) == 0
    assert "Suggested user label: You" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["transcript", "analyse", "--file", "x", "--speaker", "You", "--mode", "all-mine"])
