"""Real consolidation calls through the gateway (M7.a2, D-054): a task, then the correction of the
example text `content/examples/m7_consolidation.txt`.

    VOCAB_RUN_LIVE=1 uv run pytest tests/live/test_live_consolidation.py -m live -v

Two to four requests. A quota or a rate limit gives a skip, not a failure. The example uses eight
terms of the demo's "Causal inference reading" deck: six used well, "noisy estimate" used wrongly
(a noun used as a verb), "underpowered" forgotten. When the model disagrees, the prompt is
adjusted, never the test (D-132).
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.config import REPO_ROOT, Settings
from app.db import migrate
from app.db.base import utcnow
from app.db.engine import create_db_engine
from app.db.models import ProductionTarget
from app.db.taxonomy import sync_taxonomy
from app.domain.consolidation import TaskType
from app.services import consolidation, consolidation_attempts, productions
from tests.conftest import sqlite_url
from tests.consolidation_deck_support import ready_deck

EXAMPLE = REPO_ROOT / "content" / "examples" / "m7_consolidation.txt"
TERMS = [
    "run a regression",
    "tease out",
    "back-of-the-envelope",
    "instrumental variable",
    "noisy estimate",
    "shed light on",
    "take into account",
    "underpowered",
    "identification strategy",
    "attrition",
]
WELL_USED = {
    "run a regression",
    "tease out",
    "instrumental variable",
    "shed light on",
    "take into account",
    "identification strategy",
}
MISUSED = "noisy estimate"


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


def _gateway(live_settings: Settings, factory) -> Gateway:  # type: ignore[no-untyped-def]
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    return Gateway(
        lambda: build_providers(live_settings),
        session_factory=factory,
        secrets=live_settings.secret_values,
    )


def test_a_real_task_then_the_correction_of_the_example(
    live_settings: Settings, live_engine: Engine
) -> None:
    factory = lambda: Session(live_engine, expire_on_commit=False)  # noqa: E731
    gateway = _gateway(live_settings, factory)
    with factory() as session:
        deck, _ = ready_deck(session, len(TERMS), terms=TERMS, stability=lambda n: 10.0 + n)
        session.commit()
        deck_id = deck.id
    created = consolidation.create_task(
        factory, gateway, deck_id, TaskType.TALK, term_count=len(TERMS)
    )
    if created.source == "template" and created.reason in (
        "quota",
        "network",
        "timeout",
        "all_failed",
    ):
        pytest.skip(f"AI unavailable ({created.reason}): quota, rate limit or network")
    assert created.source == "ai", created
    with factory() as session:
        task = consolidation.get_task(session, created.task_id)
        structure = task.suggested_structure
        assert 3 <= len(structure["sections"]) <= 6
        spread = sorted(i for s in structure["sections"] for i in s["item_ids"])
        assert spread == sorted(consolidation.task_item_ids(session, task.id))
        attempt = consolidation_attempts.record_written(
            session,
            task.id,
            text=EXAMPLE.read_text(encoding="utf-8"),
            study_session_id=None,
            at=utcnow(),
        )
        session.commit()
        attempt_id = attempt.id
    result = consolidation_attempts.correct_consolidation(factory, gateway, attempt_id)
    if result.status == "unavailable":
        reason = result.reason.value if result.reason else "unknown"
        pytest.skip(f"AI unavailable ({reason}): quota, rate limit or network")
    assert result.status == "ok", result
    assert result.consolidation is not None
    with factory() as session:
        verdict = {
            item.term: (target.used, target.used_correctly)
            for target, item in productions.targets_of(session, attempt_id)
        }
        assert session.scalars(select(ProductionTarget)).first() is not None
    assert verdict[MISUSED][0] is True and verdict[MISUSED][1] is False, verdict
    for term in WELL_USED:
        assert verdict[term] == (True, True), (term, verdict)
    assert verdict["underpowered"][0] is False
    assert result.consolidation["misused"] >= 1
    assert result.consolidation["used_correctly"] >= len(WELL_USED)
