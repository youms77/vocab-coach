"""Two real corrections through the gateway (M5.a1): the answer of the real model must reach the
acceptance criteria without a test-side change. If one fails, the prompt is what gets fixed
(`app/ai/prompts/production_correction.v1.txt`, or the taxonomy descriptions it quotes).

    VOCAB_RUN_LIVE=1 uv run pytest tests/live/test_live_correction.py -m live -v

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
from app.services import corrections, productions
from tests.conftest import sqlite_url
from tests.factories import NOW

EXAMPLES = Path(__file__).resolve().parents[3] / "content" / "examples"


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    with Session(engine) as session:  # `db upgrade` loads the taxonomy; the codes must exist
        sync_taxonomy(session)
        session.commit()
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def _correct(
    live_settings: Settings, engine: Engine, file: Path
) -> tuple[int, corrections.CorrectionResult]:
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    with factory() as session:
        attempt = productions.create_writing(
            session,
            text=file.read_text(encoding="utf-8"),
            prompt=None,
            target_item_ids=[],
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
    result = corrections.correct_production(factory, gateway, attempt_id)
    if result.status == "unavailable":
        reason = result.reason.value if result.reason else "unknown"
        pytest.skip(f"AI unavailable ({reason}): quota, rate limit or network")
    return attempt_id, result


def _codes(engine: Engine, result: corrections.CorrectionResult) -> list[str]:
    with Session(engine) as session:
        return [
            code
            for (code,) in session.execute(
                select(ErrorCategory.code)
                .join(ErrorEvent, ErrorEvent.category_id == ErrorCategory.id)
                .where(ErrorEvent.id.in_(result.error_ids))
                .order_by(ErrorEvent.id)
            )
        ]


def test_the_example_paragraph_gives_exactly_the_two_expected_codes(
    live_settings: Settings, live_engine: Engine
) -> None:
    _, result = _correct(live_settings, live_engine, EXAMPLES / "m5_paragraph.txt")
    assert result.status == "ok", result
    assert sorted(_codes(live_engine, result)) == [
        "grammar.preposition.fixed_expression",
        "grammar.tense.past_simple_vs_present_perfect",
    ]
    assert result.proposed_category_ids == []


def test_a_correct_paragraph_has_no_error_and_a_naturalness_note(
    live_settings: Settings, live_engine: Engine
) -> None:
    attempt_id, result = _correct(live_settings, live_engine, EXAMPLES / "m5_correct_paragraph.txt")
    assert result.status == "ok", result
    assert result.error_ids == [], _codes(live_engine, result)
    with Session(live_engine) as session:
        feedback = productions.get_production(session, attempt_id).ai_feedback
        assert feedback is not None
        assert len(feedback["output"]["naturalness_notes"]) >= 1
