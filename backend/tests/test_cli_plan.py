"""`python -m app plan today`: readable output, JSON, and no change to the database."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.config import get_settings
from app.db.base import Base
from app.db.engine import create_db_engine
from app.domain.enums import CardDirection, ItemStatus
from tests.conftest import sqlite_url
from tests.factories import add_card, add_deck, add_item, add_sheet, link


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def _dump(url: str) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every table."""
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            return {
                table.name: [tuple(row) for row in session.execute(select(table))]
                for table in Base.metadata.sorted_tables
            }
    finally:
        engine.dispose()


def _fill(url: str) -> None:
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            waiting = add_deck(session, "Fictional talk deck")
            for i in range(3):
                term = add_item(session, f"term {i}", status=ItemStatus.QUEUED)
                link(session, waiting, term)
                add_sheet(session, term)
            learning = add_item(session, "draw a conclusion", status=ItemStatus.LEARNING)
            add_card(session, learning, CardDirection.RECEPTIVE)
            session.commit()
    finally:
        engine.dispose()


def test_cli_plan_today_on_empty_database_is_readable(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["db", "upgrade"])
    capsys.readouterr()
    assert main(["plan", "today"]) == 0
    out = capsys.readouterr().out
    assert "Budget: 45 min" in out
    assert "New terms allowed: 0 (limit: nothing to learn" in out
    assert "1. Reviews: none due" in out


def test_cli_plan_today_json_is_valid(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["db", "upgrade"])
    capsys.readouterr()
    assert main(["plan", "today", "--at", "2026-11-01T08:00", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["study_day"] == "2026-11-01"
    assert plan["generated_at"] == "2026-11-01T07:00:00Z"  # 08:00 in Douala
    assert plan["limit"] == "nothing_to_learn"
    assert plan["budget_seconds"] == 2700


def test_cli_plan_today_does_not_change_the_database(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = sqlite_url(db_file)
    main(["db", "upgrade"])
    _fill(url)
    before = _dump(url)
    capsys.readouterr()

    assert main(["plan", "today", "--at", "2026-12-01T08:00"]) == 0
    out = capsys.readouterr().out
    assert "1. Reviews: 1 card(s)" in out
    assert "2. New terms: 3" in out
    assert "Decks to activate: 1" in out

    # Same rows everywhere: the deck stays queued, no event, no study session.
    assert _dump(url) == before


def test_cli_plan_today_without_database_asks_for_upgrade(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plan", "today"]) == 1
    assert "db upgrade" in capsys.readouterr().err
    assert not db_file.exists()


def test_cli_plan_today_rejects_a_bad_date(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["db", "upgrade"])
    assert main(["plan", "today", "--at", "tomorrow"]) == 1
    assert "ISO date-time" in capsys.readouterr().err
