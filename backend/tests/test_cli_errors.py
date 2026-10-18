"""`python -m app errors list | show | add | categories` (no AI needed)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.cli import main
from app.config import get_settings
from app.db.engine import create_db_engine
from app.db.models import ErrorCategory
from app.domain.enums import ErrorCategoryStatus
from app.services import error_log
from tests.conftest import sqlite_url


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    yield path
    get_settings.cache_clear()


ADD = [
    "errors",
    "add",
    "--wrong",
    "in campus",
    "--correction",
    "on campus",
    "--category",
    "grammar.preposition.fixed_expression",
    "--original",
    "I live in campus.",
    "--alt",
    "at the university",
    "--explanation",
    "We say 'on campus'.",
]


def test_add_list_and_show(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(ADD) == 0
    assert "Error #1 recorded" in capsys.readouterr().out
    assert main(["errors", "list"]) == 0
    out = capsys.readouterr().out
    assert "Errors 1-1 of 1" in out
    assert "manual   grammar.preposition.fixed_expression" in out
    assert "in campus -> on campus" in out and "in: I live in campus." in out
    assert "1  grammar.preposition  (Prepositions)" in out
    assert main(["errors", "list", "--category", "lexis"]) == 0
    assert "No error matches." in capsys.readouterr().out
    assert main(["errors", "show", "1"]) == 0
    out = capsys.readouterr().out
    assert "also:        at the university" in out and "rule:        We say" in out
    assert main(["errors", "show", "9"]) == 2
    assert "There is no error 9." in capsys.readouterr().err


def test_add_refusals(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main([*ADD[:7], "grammar.nothing"]) == 1
    assert "not an active error category" in capsys.readouterr().err
    assert main([*ADD[:8], "--original", "I live on campus."]) == 1
    assert main([*ADD, "--item-id", "42"]) == 2
    assert main(["errors", "list", "--page-size", "101"]) == 2


def test_categories_and_proposed(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            outcome = error_log.propose_category(
                session,
                error_log.Proposal(
                    "grammar.preposition", "campus", "Campus", "Campus", "on campus, at university"
                ),
                at=datetime(2026, 10, 17, tzinfo=UTC),
            )
            session.commit()
            category = session.get_one(ErrorCategory, outcome.category.id)
            assert category.status == ErrorCategoryStatus.PROPOSED
    finally:
        engine.dispose()
    capsys.readouterr()
    assert main(["errors", "categories"]) == 0
    out = capsys.readouterr().out
    assert "grammar.preposition.fixed_expression" in out
    assert "grammar.preposition.campus" in out and "(ai)  [proposed" in out
    assert main(["errors", "categories", "--proposed"]) == 0
    out = capsys.readouterr().out
    assert "grammar.preposition.campus  Campus / Campus" in out
    assert "fixed_expression" not in out


def test_card_suggestions_and_dismiss(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["errors", "suggestions"]) == 0
    assert "No recurring error without a card." in capsys.readouterr().out
    assert main(ADD) == 0
    assert main(ADD) == 0
    capsys.readouterr()

    assert main(["errors", "suggestions"]) == 0
    out = capsys.readouterr().out
    assert "2x  in campus -> on campus  [errors card 2]" in out
    assert "key: in campus => on campus" in out

    assert main(["errors", "card", "2", "--term", "x y z u v w t"]) == 1
    assert "(invalid_term)" in capsys.readouterr().err
    assert main(["errors", "card", "2"]) == 0
    out = capsys.readouterr().out
    assert "'on campus' made from error #2." in out
    assert "exercise: I live ___ campus." in out
    assert main(["errors", "card", "2"]) == 1  # one card per error
    assert "already is a card of this error" in capsys.readouterr().err
    assert main(["errors", "card", "9"]) == 2

    assert main(["errors", "suggestions"]) == 0
    assert "No recurring error without a card." in capsys.readouterr().out
    assert main(["errors", "dismiss", "in campus => on campus"]) == 2  # a card hides it: not found
    assert main(["errors", "show", "2"]) == 0
