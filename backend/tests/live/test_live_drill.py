"""One real targeted drill through the gateway (M5.a2): 10 valid items on fixed expressions.

    VOCAB_RUN_LIVE=1 uv run pytest tests/live/test_live_drill.py -m live -v

One request (two if a repair is needed). A quota or a rate limit gives a skip, not a failure.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.db.taxonomy import sync_taxonomy
from app.domain.drills import GAP, SOLUTION_KEYS, public_item
from app.services import drills
from tests.conftest import sqlite_url
from tests.factories import NOW

CODE = "grammar.preposition.fixed_expression"


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


def test_a_ten_item_drill_on_fixed_expressions_is_valid(
    live_settings: Settings, live_engine: Engine
) -> None:
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    factory = lambda: Session(live_engine, expire_on_commit=False)  # noqa: E731
    gateway = Gateway(
        lambda: build_providers(live_settings),
        session_factory=factory,
        secrets=live_settings.secret_values,
    )
    result = drills.generate_drill(factory, gateway, CODE, count=10, clock=lambda: NOW)
    if result.status == "unavailable":
        reason = result.reason.value if result.reason else "unknown"
        pytest.skip(f"AI unavailable ({reason}): quota, rate limit or network")
    assert result.status == "ok", result
    assert result.drill_id is not None
    with factory() as session:
        attempt = drills.get_drill(session, result.drill_id)
        feedback = attempt.ai_feedback or {}
    items = feedback["items"]
    assert len(items) == 10
    assert all(item["sentence"].count(GAP) == 1 for item in items)
    assert {item["kind"] for item in items} <= {"gap_fill", "choice"}
    assert len({item["theme"] for item in items}) >= 2
    assert feedback["rule_en"] and feedback["rule_fr"]
    for index, item in enumerate(items):
        assert not SOLUTION_KEYS & set(public_item(result.drill_id, index, item))
