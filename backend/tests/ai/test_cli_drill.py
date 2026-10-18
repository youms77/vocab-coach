"""`python -m app drill new | list` (M5.a2): no solutions printed, exit codes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_drill
from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import ProductionAttempt
from tests.conftest import sqlite_url
from tests.drill_support import FIXED, drill_output
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


def _drills(path: Path) -> int:
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            return count(session, ProductionAttempt)
    finally:
        engine.dispose()


def _new(db_file: Path, provider: FakeProvider, code: str = FIXED, count_: int = 5) -> int:
    return cli_drill.run_drill_new(
        sqlite_url(db_file), Settings(), code, count=count_, gateway_factory=_gateway(provider)
    )


def test_drill_new_prints_the_rule_and_items_without_solutions(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("fake", [Success(content=drill_output(5))])
    assert _new(db_file, fake) == 0
    out = capsys.readouterr().out
    assert f"Drill #1 on {FIXED} (5 items)." in out
    assert "Rule: Some phrases always take the same preposition." in out
    assert "  0. In week 0, my friend lived ___ campus with two classmates." in out
    assert "[0]" in out  # the options of the choice items
    assert "On dit" not in out and "We say" not in out  # no explanation before the attempt
    assert "items/<index>/answer" in out


def test_drill_list(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_drill.run_drill_list(sqlite_url(db_file)) == 0
    assert "No drill yet" in capsys.readouterr().out
    _new(db_file, FakeProvider("fake", [Success(content=drill_output(5))]))
    capsys.readouterr()
    assert cli_drill.run_drill_list(sqlite_url(db_file)) == 0
    out = capsys.readouterr().out
    assert "1 drill(s)" in out and FIXED in out and "0/5 correct, 0 answered (in progress)" in out


def test_refusals_and_failures(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeProvider("fake", [Success(content=drill_output(5))])
    assert _new(db_file, fake, code="grammar") == 2
    assert "more precise category" in capsys.readouterr().err
    assert _new(db_file, fake, code="nothing.here") == 2
    assert fake.calls == 0
    down = FakeProvider("fake", [Success(content=drill_output(5))], configured=False)
    assert _new(db_file, down) == 1
    assert "could not write the drill" in capsys.readouterr().err
    assert _drills(db_file) == 0


def test_demo_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeProvider("fake", [Success(content=drill_output(5))])
    code = cli_drill.run_drill_new(
        "sqlite:///unused.sqlite3", Settings(demo=True), FIXED, gateway_factory=_gateway(fake)
    )
    assert code == 2 and "refused on the demo database" in capsys.readouterr().err


def test_the_command_line_is_wired(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["drill", "list"]) == 0
    assert "No drill yet" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["drill", "new", FIXED, "--count", "20"])
