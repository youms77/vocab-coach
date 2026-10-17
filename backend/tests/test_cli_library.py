"""`python -m app library import`: preview without writing, `--commit`, exit codes, `--demo`."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.config import get_settings
from app.db.engine import create_db_engine
from app.db.models import Deck, EventLog, LexicalItem
from app.domain.enums import ItemStatus
from tests.conftest import sqlite_url
from tests.library_support import count

EXAMPLES = Path(__file__).resolve().parents[2] / "content" / "examples"
WITH_HEADER = EXAMPLES / "import-with-header.md"
WITHOUT_HEADER = EXAMPLES / "import-without-header.md"


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def counts(path: Path) -> tuple[int, int, int]:
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            return count(session, Deck), count(session, LexicalItem), count(session, EventLog)
    finally:
        engine.dispose()


def test_preview_writes_nothing(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["db", "upgrade"]) == 0
    before = db_file.read_bytes()
    assert main(["library", "import", str(WITH_HEADER)]) == 0
    out = capsys.readouterr().out
    assert "nothing written" in out and "deck: Presenting survey results" in out
    assert "? L16" in out and "ambiguous looks_like_definition" in out
    assert "warning duplicate_in_file" in out and "info heading_ignored: line 8" in out
    assert "--commit" in out
    assert counts(db_file) == (0, 0, 0)
    assert db_file.read_bytes() == before


def test_commit_then_attach(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["db", "upgrade"])
    assert main(["library", "import", str(WITH_HEADER), "--commit"]) == 0
    out = capsys.readouterr().out
    assert "Imported into new deck #1: 9 new (waiting for triage)" in out
    assert "3 skipped (2 ambiguous left out)" in out
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            statuses = set(session.scalars(select(LexicalItem.status)))
            assert statuses == {ItemStatus.TRIAGE}
            deck = session.get(Deck, 1)
            assert deck is not None and deck.name == "Presenting survey results"
    finally:
        engine.dispose()

    # Second time into the same deck: every term is already there.
    assert main(["library", "import", str(WITH_HEADER), "--deck-id", "1"]) == 0
    assert "- L10" in capsys.readouterr().out
    # Into a new deck without a header: named after the file, queued directly.
    assert main(["library", "import", str(WITHOUT_HEADER), "--commit", "--no-triage"]) == 0
    assert "6 new (queued)" in capsys.readouterr().out
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            assert session.get(Deck, 2).name == "import-without-header"  # type: ignore[union-attr]
    finally:
        engine.dispose()


def test_exit_codes(db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["library", "import", str(WITH_HEADER)]) == 2  # no database yet
    assert "db upgrade" in capsys.readouterr().err
    main(["db", "upgrade"])
    assert main(["library", "import", str(tmp_path / "missing.md")]) == 2
    assert main(["library", "import", str(WITH_HEADER), "--deck-id", "42"]) == 2
    assert "no deck 42" in capsys.readouterr().err

    big = tmp_path / "big.md"
    big.write_text("- x\n" * 70_000, encoding="utf-8")
    assert main(["library", "import", str(big)]) == 1
    assert "too_large" in capsys.readouterr().err
    latin = tmp_path / "latin.md"
    latin.write_bytes("- café\n".encode("cp1252"))
    assert main(["library", "import", str(latin)]) == 1
    assert "not_utf8" in capsys.readouterr().err
    many = tmp_path / "many.md"
    many.write_text("\n".join(f"- t{i}" for i in range(1001)), encoding="utf-8")
    assert main(["library", "import", str(many)]) == 1
    only_ambiguous = tmp_path / "ambiguous.md"
    only_ambiguous.write_text("- bias = biais\n", encoding="utf-8")
    assert main(["library", "import", str(only_ambiguous), "--commit"]) == 1
    assert "Nothing to import" in capsys.readouterr().err
    assert counts(db_file) == (0, 0, 0)


def test_demo_flag_uses_the_demo_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("VOCAB_DATABASE_URL", raising=False)
    monkeypatch.setenv("VOCAB_DEMO", "0")  # set, so teardown removes what `--demo` writes
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert main(["--demo", "db", "upgrade"]) == 0
        assert main(["--demo", "library", "import", str(WITH_HEADER), "--commit"]) == 0
        demo = get_settings().demo_database_file
        assert counts(demo)[1] == 9
        assert not (tmp_path / "vocab-coach.sqlite3").exists()
    finally:
        get_settings.cache_clear()
