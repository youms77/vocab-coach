"""`python -m app library enrich | extend` (M3.b): dry run, batches, degraded mode, exit codes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_library
from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind
from app.cli import main
from app.config import Settings, get_settings
from app.db.engine import create_db_engine
from app.db.models import Enrichment, LexicalItem
from app.domain.enums import ItemStatus
from app.domain.events import ItemOrigin
from app.services import library
from tests.conftest import sqlite_url
from tests.enrichment_support import batch_output
from tests.factories import NOW
from tests.library_support import count

TERMS = ["to account for", "shed light on"]


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            deck = library.create_deck(session, name="Reading", at=NOW)
            for term in TERMS:
                item = library.create_item(
                    session,
                    term=term,
                    at=NOW,
                    origin=ItemOrigin.IMPORT,
                    intake=ItemStatus.QUEUED,
                )
                library.add_item_to_deck(session, deck, item, NOW)
            session.commit()
    finally:
        engine.dispose()
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


def _settings() -> Settings:
    return Settings()


def test_dry_run_lists_the_waiting_terms_and_calls_nothing(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["library", "enrich", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2 term(s) waiting for a usage sheet." in out and "to account for" in out
    assert _count(db_file, Enrichment) == 0


def test_enrich_writes_the_sheets(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeProvider("a", [Success(content=batch_output(TERMS))])
    code = cli_library.run_library_enrich(
        sqlite_url(db_file), _settings(), gateway_factory=_gateway(fake)
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "2 sheet(s) generated" in out and "0 still waiting" in out
    assert _count(db_file, Enrichment) == 2
    assert len(fake.requests) == 1


def test_enrich_with_nothing_waiting_is_a_quiet_success(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("a", [Success(content=batch_output(TERMS))])
    cli_library.run_library_enrich(sqlite_url(db_file), _settings(), gateway_factory=_gateway(fake))
    capsys.readouterr()
    again = FakeProvider("a", [])
    code = cli_library.run_library_enrich(
        sqlite_url(db_file), _settings(), gateway_factory=_gateway(again)
    )
    assert code == 0 and "0 term(s) waiting" in capsys.readouterr().out
    assert again.requests == []


def test_unavailable_ai_exits_1_and_keeps_the_terms_waiting(
    db_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeProvider("a", [Failure(ErrorKind.AUTH)])
    code = cli_library.run_library_enrich(
        sqlite_url(db_file), _settings(), gateway_factory=_gateway(fake)
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "The AI is unavailable" in captured.err and "2 still waiting" in captured.out
    assert _count(db_file, Enrichment) == 0


def test_enrich_usage_errors(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["library", "enrich", "--deck-id", "42", "--dry-run"]) == 2
    assert "42" in capsys.readouterr().err
    assert main(["library", "enrich", "--item-id", "999", "--dry-run"]) == 2
    missing = db_file.parent / "nope" / "x.sqlite3"
    assert cli_library.run_library_enrich(sqlite_url(missing), _settings(), dry_run=True) == 2
    assert "db upgrade" in capsys.readouterr().err


def test_extend_creates_terms_in_triage(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    suggestions = [
        {
            "term": f"selection bias {i}",
            "item_type": "collocation",
            "category": "technical",
            "example_sentence": f"We discuss selection bias {i} here.",
        }
        for i in range(10)
    ]
    fake = FakeProvider("a", [Success(content={"suggestions": suggestions})])
    code = cli_library.run_library_extend(
        sqlite_url(db_file), _settings(), 1, count=10, gateway_factory=_gateway(fake)
    )
    assert code == 0
    assert "10 new term(s) waiting for triage in deck #1" in capsys.readouterr().out
    assert _count(db_file, LexicalItem) == 2 + 10


def test_extend_failures_and_usage(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeProvider("a", [Failure(ErrorKind.AUTH)])
    assert (
        cli_library.run_library_extend(
            sqlite_url(db_file), _settings(), 1, count=10, gateway_factory=_gateway(fake)
        )
        == 1
    )
    assert "No suggestion" in capsys.readouterr().err
    assert (
        cli_library.run_library_extend(
            sqlite_url(db_file), _settings(), 42, count=10, gateway_factory=_gateway(fake)
        )
        == 2
    )
    with pytest.raises(SystemExit) as exc:
        main(["library", "extend", "1", "--count", "5"])
    assert exc.value.code == 2
    assert "between 10 and 30" in capsys.readouterr().err
