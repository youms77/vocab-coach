"""Two real transcript analyses through the gateway (M5.a2): the answer of the real model must reach
the acceptance criteria without a test-side change. If one fails, the prompt is what gets fixed
(`app/ai/prompts/transcript_analysis.v1.txt`, or the taxonomy descriptions it quotes), as D-132.

    VOCAB_RUN_LIVE=1 uv run pytest tests/live/test_live_transcript.py -m live -v

Two requests (more if a repair is needed). A quota or a rate limit gives a skip, not a failure.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.db.models import ErrorCategory, ErrorEvent
from app.db.taxonomy import sync_taxonomy
from app.domain.transcript_import import UserByLabel, parse_transcript
from app.services import corrections, transcripts
from tests.conftest import sqlite_url
from tests.factories import NOW

EXAMPLES = Path(__file__).resolve().parents[3] / "content" / "examples"
USER = UserByLabel(label="You")


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def _analyse(
    live_settings: Settings, engine: Engine, file: Path
) -> tuple[str, corrections.CorrectionResult]:
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    text = file.read_text(encoding="utf-8")
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    with factory() as session:
        attempt = transcripts.record_transcript(
            session,
            text=text,
            user=USER,
            title=None,
            occurred_on=None,
            study_session_id=None,
            at=NOW,
        )
        session.commit()
        attempt_id = attempt.id
    gateway = Gateway(
        lambda: build_providers(live_settings),
        session_factory=factory,
        secrets=live_settings.secret_values,
    )
    result = transcripts.analyse_transcript(
        factory, gateway, attempt_id, source=transcripts.TranscriptSource(text, USER)
    )
    if result.status == "unavailable":
        reason = result.reason.value if result.reason else "unknown"
        pytest.skip(f"AI unavailable ({reason}): quota, rate limit or network")
    return text, result


def _errors(engine: Engine, result: corrections.CorrectionResult) -> list[tuple[str, str]]:
    """(code, wrong form) of each error, in order."""
    with Session(engine) as session:
        return [
            (code, wrong)
            for code, wrong in session.execute(
                select(ErrorCategory.code, ErrorEvent.erroneous_text)
                .join(ErrorEvent, ErrorEvent.category_id == ErrorCategory.id)
                .where(ErrorEvent.id.in_(result.error_ids))
                .order_by(ErrorEvent.id)
            )
        ]


def test_the_example_transcript_gives_exactly_the_three_expected_codes(
    live_settings: Settings, live_engine: Engine
) -> None:
    text, result = _analyse(live_settings, live_engine, EXAMPLES / "m5_transcript.txt")
    assert result.status == "ok", result
    found = _errors(live_engine, result)
    assert sorted(code for code, _ in found) == [
        "grammar.preposition.by_for_since",
        "grammar.preposition.fixed_expression",
        "grammar.tense.past_simple_vs_present_perfect",
    ], found
    # None comes from ChatGPT's turn: every wrong form is in the user's own words.
    mine = parse_transcript(text, USER).user_text.casefold()
    assert all(wrong.casefold() in mine for _, wrong in found), found
    assert result.proposed_category_ids == []


def test_a_clean_transcript_has_no_error(live_settings: Settings, live_engine: Engine) -> None:
    _, result = _analyse(live_settings, live_engine, EXAMPLES / "m5_transcript_clean.txt")
    assert result.status == "ok", result
    assert result.error_ids == [], _errors(live_engine, result)
