"""The scenario units of the demo database (dataset v7, M8.a2): written, read, shadowed and spoken
through the services, in the three states the screens need (done, in progress, written only)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.engine import create_db_engine
from app.db.models import (
    CurriculumTrack,
    CurriculumUnit,
    Deck,
    EventLog,
    LexicalItem,
    ProductionAttempt,
)
from app.demo.dataset import load_dataset
from app.demo.seed import seed_demo, sqlite_url
from app.domain.enums import ProductionKind, UnitContentStatus, UnitProgress
from app.services import curriculum
from tests.demo_support import DEMO_ANCHOR, DEMO_SEED


@pytest.fixture(scope="module")
def demo_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    path = tmp_path_factory.mktemp("demo-units") / "vocab-coach-demo.sqlite3"
    seed_demo(path, seed=DEMO_SEED, days=60, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()


@pytest.fixture
def db(demo_engine: Engine) -> Iterator[Session]:
    with Session(demo_engine) as session:
        yield session
        session.rollback()


def units(db: Session) -> dict[str, CurriculumUnit]:
    return {u.code: u for u in db.scalars(select(CurriculumUnit).order_by(CurriculumUnit.id))}


def test_the_dataset_has_three_units_that_pass_the_ai_schema() -> None:
    dataset = load_dataset()
    assert dataset.dataset_version == 7
    assert [u.number for u in dataset.units] == [1, 3, 5]


def test_three_units_in_three_states(db: Session) -> None:
    found = units(db)
    assert list(found) == ["job_interview_1", "presenting_data_1", "meetings_1"]
    states = {code: (u.content_status, u.progress) for code, u in found.items()}
    assert states == {
        "job_interview_1": (UnitContentStatus.GENERATED, UnitProgress.DONE),
        "presenting_data_1": (UnitContentStatus.GENERATED, UnitProgress.IN_PROGRESS),
        "meetings_1": (UnitContentStatus.GENERATED, UnitProgress.NOT_STARTED),
    }
    for unit in found.values():
        assert (unit.provider, unit.model, unit.prompt_version) == ("demo", None, "demo-unit-v1")
        assert (unit.content or {})["format"] == "curriculum-unit-1"


def test_the_done_unit_was_worked_through_every_step(db: Session) -> None:
    unit = units(db)["job_interview_1"]
    out = curriculum.get_unit(db, unit.id)
    scenario = out.scenario
    assert scenario is not None and scenario.next_step is None
    assert all(scenario.steps.values()) and scenario.final_task.corrected
    assert [s.take_count >= 1 for s in scenario.shadowing] == [True] * 6
    (talk_id,) = scenario.final_task.attempt_ids
    talk = db.get_one(ProductionAttempt, talk_id)
    assert talk.curriculum_unit_id == unit.id and talk.kind is ProductionKind.SPEAKING
    assert talk.ai_feedback is not None and talk.word_count >= 80
    assert (talk.prompt_text or "").startswith("You are in a job interview")


def test_the_second_unit_is_half_done(db: Session) -> None:
    unit = units(db)["presenting_data_1"]
    scenario = curriculum.get_unit(db, unit.id).scenario
    assert scenario is not None
    assert scenario.steps == {
        "formulas": True,
        "dialogue": True,
        "shadowing": False,
        "final_task": False,
    }
    assert [s.take_count for s in scenario.shadowing] == [1, 1, 0, 0, 0, 0]
    assert scenario.next_step == "shadowing"


def test_the_written_only_unit_has_nothing_done(db: Session) -> None:
    unit = units(db)["meetings_1"]
    scenario = curriculum.get_unit(db, unit.id).scenario
    assert scenario is not None and scenario.next_step == "formulas"
    assert (
        db.scalar(
            select(func.count())
            .select_from(ProductionAttempt)
            .where(ProductionAttempt.curriculum_unit_id == unit.id)
        )
        == 0
    )


def test_the_demo_adds_no_term_and_no_deck_for_the_units(db: Session) -> None:
    assert [t.code for t in db.scalars(select(CurriculumTrack))] == ["speaking_scenarios"]
    assert curriculum.find_deck(db, "speaking_scenarios") is None
    assert all(u.deck_id is None for u in units(db).values())
    assert (
        db.scalar(
            select(func.count())
            .select_from(LexicalItem)
            .where(LexicalItem.term == "take the initiative")
        )
        == 0
    )
    assert "Speaking scenarios" not in [d.name for d in db.scalars(select(Deck))]


def test_the_events_tell_the_story(db: Session) -> None:
    kinds = db.scalars(
        select(EventLog.event_type).where(EventLog.event_type.like("curriculum.%"))
    ).all()
    assert sorted(kinds) == sorted(
        ["curriculum.unit_generated"] * 3
        + ["curriculum.unit_step_completed"] * 6  # 4 for the done unit, 2 for the second
        + ["curriculum.unit_completed"]
    )


def test_a_short_history_scales_the_days(tmp_path: Path) -> None:
    path = tmp_path / "short.sqlite3"
    seed_demo(path, seed=DEMO_SEED, days=21, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            assert [u.progress for u in units(session).values()] == [
                UnitProgress.DONE,
                UnitProgress.IN_PROGRESS,
                UnitProgress.NOT_STARTED,
            ]
    finally:
        engine.dispose()
