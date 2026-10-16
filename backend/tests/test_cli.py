from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import db_reset, main
from app.config import get_settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.db.models import Deck, ErrorCategory
from tests.conftest import sqlite_url


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def _count(url: str, model: type) -> int:
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            return session.scalar(select(func.count()).select_from(model)) or 0
    finally:
        engine.dispose()


def _add_deck(url: str) -> None:
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            session.add(Deck(name="Fictional deck"))
            session.commit()
    finally:
        engine.dispose()


def test_db_upgrade_twice_creates_then_changes_nothing(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["db", "upgrade"]) == 0
    first = capsys.readouterr().out
    assert main(["db", "upgrade"]) == 0
    second = capsys.readouterr().out

    url = sqlite_url(db_file)
    assert _count(url, ErrorCategory) > 0
    assert "0 added, 0 updated" not in first
    assert "0 added, 0 updated" in second
    engine = create_db_engine(url)
    try:
        assert migrate.schema_status(engine).at_head
    finally:
        engine.dispose()


def test_db_reset_without_yes_refuses_and_keeps_data(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["db", "upgrade"])
    _add_deck(sqlite_url(db_file))

    assert main(["db", "reset"]) == 2
    assert "--yes" in capsys.readouterr().err
    assert _count(sqlite_url(db_file), Deck) == 1
    assert list(db_file.parent.glob("*.bak-*")) == []


def test_db_reset_with_yes_backs_up_then_recreates(db_file: Path) -> None:
    url = sqlite_url(db_file)
    main(["db", "upgrade"])
    _add_deck(url)

    backup = db_reset(url, now=datetime(2026, 10, 16, 9, 5, 7))  # noqa: DTZ001

    assert backup == db_file.with_name("vocab-coach.sqlite3.bak-20261016-090507")
    assert backup.exists()
    assert _count(sqlite_url(backup), Deck) == 1
    assert _count(url, Deck) == 0
    assert _count(url, ErrorCategory) > 0


def test_db_reset_cli_with_yes(db_file: Path) -> None:
    main(["db", "upgrade"])
    assert main(["db", "reset", "--yes"]) == 0
    assert len(list(db_file.parent.glob("vocab-coach.sqlite3.bak-*"))) == 1
