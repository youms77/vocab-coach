"""Targeted practice ignores the errors made in drills (D-029 as amended in M5.a2, D-136)."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.taxonomy import sync_taxonomy
from app.domain.enums import ErrorSource
from app.domain.planner import pick_targeted_category
from app.services import error_log
from app.services.planning import build_plan_inputs, plan_today
from tests.factories import NOW

PREPOSITION = "grammar.preposition.fixed_expression"
TENSE = "grammar.tense.past_simple_vs_present_perfect"


def _error(session: Session, code: str, source: ErrorSource, hours_ago: int) -> None:
    error_log.record_error(
        session,
        source=source,
        category=error_log.active_category(session, code),
        erroneous_text="wrong",
        correction="right",
        at=NOW - timedelta(hours=hours_ago),
    )


def test_drill_errors_do_not_choose_the_targeted_practice(session: Session) -> None:
    sync_taxonomy(session)
    for hours in range(1, 6):  # five recent drill errors on prepositions
        _error(session, PREPOSITION, ErrorSource.DRILL, hours)
    _error(session, TENSE, ErrorSource.WRITING, 30)
    _error(session, TENSE, ErrorSource.WRITING, 40)
    session.commit()

    inputs = build_plan_inputs(session, NOW)
    assert {sample.category_code for sample in inputs.recent_errors} == {TENSE}
    assert pick_targeted_category(inputs.recent_errors, NOW) == (TENSE, 2)
    plan = plan_today(session, NOW)
    targeted = [
        entry
        for block in plan.model_dump()["blocks"]
        for entry in block["entries"]
        if entry["kind"] == "targeted_practice"
    ]
    assert [(e["category_code"], e["error_count"]) for e in targeted] == [(TENSE, 2)]


def test_only_drill_errors_give_no_targeted_practice(session: Session) -> None:
    sync_taxonomy(session)
    for hours in range(1, 6):
        _error(session, PREPOSITION, ErrorSource.DRILL, hours)
    session.commit()
    assert build_plan_inputs(session, NOW).recent_errors == []
