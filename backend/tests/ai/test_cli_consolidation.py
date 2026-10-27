"""`python -m app consolidation status | new | show | export` (M7.a1): output and exit codes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_consolidation
from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.domain.consolidation import TaskType, term_ref
from tests.conftest import sqlite_url
from tests.consolidation_deck_support import ready_deck
from tests.consolidation_support import task_output


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    yield path
    get_settings.cache_clear()


def add_deck(db_file: Path, count: int, name: str = "Causal inference reading") -> int:
    engine = create_db_engine(sqlite_url(db_file))
    try:
        with Session(engine) as session:
            deck, _ = ready_deck(session, count, name=name)
            session.commit()
            return deck.id
    finally:
        engine.dispose()


def gateway(provider: FakeProvider):  # type: ignore[no-untyped-def]
    def build(engine: Engine) -> Gateway:
        return Gateway(
            {provider.name: provider},
            session_factory=lambda: Session(engine, expire_on_commit=False),
            provider_order=lambda: [provider.name],
            sleep=lambda _s: None,
        )

    return build


def new(db_file: Path, provider: FakeProvider, deck_id: int, **kwargs) -> int:  # type: ignore[no-untyped-def]
    return cli_consolidation.run_consolidation_new(
        sqlite_url(db_file), Settings(), deck_id, gateway_factory=gateway(provider), **kwargs
    )


def test_status(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_consolidation.run_consolidation_status(sqlite_url(db_file)) == 0
    assert "No deck yet" in capsys.readouterr().out
    ready = add_deck(db_file, 10)
    add_deck(db_file, 4, name="Small")
    assert main(["consolidation", "status"]) == 0
    out = capsys.readouterr().out
    assert f"{ready:>4}  yes" in out and "10/10" in out
    assert "no" in out and "fewer than 8 consolidated terms" in out


def test_new_show_and_export(
    db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deck_id = add_deck(db_file, 10)
    provider = FakeProvider(
        "fake", [Success(content=task_output([term_ref(i) for i in range(10)]))]
    )
    assert new(db_file, provider, deck_id, count=10) == 0
    out = capsys.readouterr().out
    assert "Task #1: Presenting a reading on causal inference" in out
    assert "Terms (10):" in out and "term number 1 [consolidated]" in out
    assert "Written by: ai" in out
    assert main(["consolidation", "show", "1"]) == 0
    assert "Structure:" in capsys.readouterr().out
    target = tmp_path / "task.md"
    assert main(["consolidation", "export", "1", "--lang", "fr", "--out", str(target)]) == 0
    assert "Écoute tout mon exposé" in target.read_text(encoding="utf-8")
    assert main(["consolidation", "export", "1"]) == 0
    assert "3 follow-up questions" in capsys.readouterr().out


def test_without_ai_a_template_is_used(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    deck_id = add_deck(db_file, 10)
    down = FakeProvider("fake", [Success()], configured=False)
    assert new(db_file, down, deck_id, task_type=TaskType.SPEECH) == 0
    out = capsys.readouterr().out
    assert "made from a template instead" in out and "no_provider_configured" in out
    assert "Written by: template" in out and "Type: speech" in out


def test_refusals(db_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    small = add_deck(db_file, 5, name="Small")
    provider = FakeProvider("fake", [Success()], configured=False)
    assert new(db_file, provider, small) == 2
    assert "fewer than 8 consolidated terms" in capsys.readouterr().err
    assert new(db_file, provider, 999) == 2
    assert "There is no deck 999" in capsys.readouterr().err
    ready = add_deck(db_file, 10)
    assert new(db_file, provider, ready) == 0
    capsys.readouterr()
    assert new(db_file, provider, ready) == 2
    assert "(task 1)" in capsys.readouterr().err
    assert main(["consolidation", "show", "99"]) == 2
    assert main(["consolidation", "export", "99"]) == 2
    capsys.readouterr()
    bad = tmp_path / "missing" / "x.md"
    assert main(["consolidation", "export", "1", "--out", str(bad)]) == 2
    assert "Cannot write" in capsys.readouterr().err


def test_the_command_line_is_wired() -> None:
    with pytest.raises(SystemExit):
        main(["consolidation", "new", "1", "--count", "7"])
    with pytest.raises(SystemExit):
        main(["consolidation", "new", "1", "--type", "poem"])
