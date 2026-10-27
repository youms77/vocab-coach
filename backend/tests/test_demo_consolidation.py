"""The consolidation task of the demo database (dataset v6, M7.a2): made through the services at
about day -10, a written text corrected, the result applied, the task completed; and a deck ready
at the anchor for the manual scenario."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.engine import create_db_engine
from app.db.models import (
    Card,
    ConsolidationTask,
    ConsolidationTaskItem,
    Deck,
    ErrorEvent,
    EventLog,
    LexicalItem,
    ProductionAttempt,
    ReviewLog,
)
from app.demo.dataset import Fate, load_dataset
from app.demo.seed import seed_demo, sqlite_url
from app.domain.consolidation import NotReadyReason
from app.domain.enums import ConsolidationTaskStatus, ErrorSource, ItemStatus, ProductionKind
from app.services import consolidation
from tests.demo_support import DEMO_ANCHOR, DEMO_SEED


@pytest.fixture(scope="module")
def demo_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    folder = tmp_path_factory.mktemp("demo-consolidation")
    path = folder / "vocab-coach-demo.sqlite3"
    seed_demo(path, seed=DEMO_SEED, days=60, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()


@pytest.fixture
def db(demo_engine: Engine) -> Iterator[Session]:
    with Session(demo_engine) as session:
        yield session
        session.rollback()


def test_one_completed_task_about_ten_days_before_the_anchor(db: Session) -> None:
    (task,) = db.scalars(select(ConsolidationTask)).all()
    deck = db.get_one(Deck, task.deck_id)
    assert deck.name == "Causal inference reading"
    assert task.status is ConsolidationTaskStatus.DONE and task.completed_at is not None
    assert (DEMO_ANCHOR - task.created_at.date()).days == 10
    structure = task.suggested_structure
    assert structure["source"] == "ai" and structure["provider"] == "demo"
    assert structure["task_type"] == "talk"
    assert len(consolidation.task_item_ids(db, task.id)) == 15


def test_the_text_is_corrected_and_its_result_applied(db: Session) -> None:
    (attempt,) = db.scalars(
        select(ProductionAttempt).where(ProductionAttempt.kind == ProductionKind.CONSOLIDATION)
    ).all()
    assert attempt.ai_feedback is not None and attempt.consolidation_task_id is not None
    errors = db.scalars(select(ErrorEvent).where(ErrorEvent.source == ErrorSource.CONSOLIDATION))
    (error,) = errors.all()
    assert error.production_attempt_id == attempt.id and error.lexical_item_id is not None
    (payload,) = db.scalars(
        select(EventLog.payload).where(EventLog.event_type == "consolidation.attempt_checked")
    ).all()
    assert payload["targets"] == 15 and payload["misused"] == 1 and payload["absent"] >= 1
    assert payload["used_correctly"] == len(payload["activated_item_ids"]) >= 10
    (again,) = db.scalars(
        select(ReviewLog).where(ReviewLog.exercise_type == "consolidation_misuse")
    ).all()
    assert again.final_rating == 1 and again.production_attempt_id is None
    card = db.get_one(Card, again.card_id)
    assert card.lexical_item_id == error.lexical_item_id
    # The misused term and the forgotten ones did not become active through the task.
    activated = set(payload["activated_item_ids"])
    assert error.lexical_item_id not in activated


def test_the_dataset_active_terms_are_active(db: Session) -> None:
    """Terms the task selected became active through it; the rest keep the direct switch
    (`MARK_ACTIVE_DAY`), the only one left (D-229)."""
    wanted = {t.term.lower() for t in load_dataset().all_terms() if t.fate == Fate.ACTIVE}
    status = {
        i.term.lower(): i.status
        for i in db.scalars(select(LexicalItem).where(LexicalItem.status == ItemStatus.ACTIVE))
    }
    assert wanted <= set(status)
    selected = set(db.scalars(select(ConsolidationTaskItem.lexical_item_id)))
    via_task = [
        i
        for i in db.scalars(select(LexicalItem))
        if i.id in selected and i.status == ItemStatus.ACTIVE
    ]
    assert len(via_task) >= 10


def test_a_deck_is_ready_at_the_anchor_for_the_manual_scenario(db: Session) -> None:
    states = {s.deck.name: s for s in consolidation.deck_overview(db)}
    causal = states["Causal inference reading"]
    assert causal.readiness.ready and causal.open_task_id is None
    assert len(causal.readiness.candidates) >= 8
    # No deck is held back by an open task: the task of the history is completed.
    assert all(s.readiness.reason is not NotReadyReason.TASK_OPEN for s in states.values())
