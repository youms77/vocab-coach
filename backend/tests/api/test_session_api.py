"""Session endpoints: today, start (idempotent, closes stale sessions), next, end."""

import random
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Card, ErrorEvent, EventLog, StudySession
from app.domain import exercises as ex
from app.domain import fsrs_engine
from app.domain.review_steps import SOLUTION_KEYS
from tests.api.conftest import ApiEnv
from tests.api.session_support import (
    DAY_2_START,
    add_all_templates,
    code,
    discover,
    quick_add,
    start_session,
    write_sheet,
)
from tests.factories import add_category


def _record(env: ApiEnv, session_id: int, step: dict, rating: int = 3, answer: str = "") -> dict:
    review = step["review"]
    response = env.client.post(
        "/api/reviews",
        json={
            "card_id": review["card_id"],
            "session_id": session_id,
            "exercise_type": review["exercise_type"],
            "exercise_template_id": review["exercise_template_id"],
            "answer": answer or None,
            "response_time_ms": 5000,
            "final_rating": rating,
            "expected_reps": review["expected_reps"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _discovered_term(env: ApiEnv, term: str = "rule out") -> int:
    """A term discovered on day 1, in a session that is then closed."""
    item_id = quick_add(env.client, term)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    discover(env.client, item_id, session_id)
    env.client.post(f"/api/session/{session_id}/end")
    return item_id


def test_today_without_session(env: ApiEnv) -> None:
    body = env.client.get("/api/session/today").json()
    assert body["open_session"] is None
    assert body["plan"]["study_day"] == "2026-10-16"


def test_start_is_idempotent_within_the_study_day(env: ApiEnv) -> None:
    first = env.client.post("/api/session/start")
    assert first.status_code == 201
    body = first.json()
    assert body["planned"]["format"] == "session-1"
    assert "blocks" in body["planned"]["plan"]
    assert body["study_day"] == "2026-10-16"
    env.clock.advance(3600)
    again = env.client.post("/api/session/start")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert env.client.get("/api/session/today").json()["open_session"]["id"] == body["id"]
    with Session(env.engine) as session:
        started = session.scalars(
            select(EventLog).where(EventLog.event_type == "session.started")
        ).all()
        assert len(started) == 1
        assert started[0].study_session_id == body["id"]


def test_start_closes_a_session_left_open_on_an_earlier_day(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    old = start_session(env.client)
    env.clock.advance(600)
    discover(env.client, item_id, old)
    last_activity = env.clock.current
    env.clock.current = DAY_2_START + timedelta(hours=2)
    new = env.client.post("/api/session/start")
    assert new.status_code == 201
    assert new.json()["id"] != old
    with Session(env.engine) as session:
        stale = session.get_one(StudySession, old)
        assert stale.ended_at == last_activity
        assert stale.summary is not None
        assert stale.summary["discoveries_completed"] == 1
        ended = session.scalars(
            select(EventLog).where(
                EventLog.event_type == "session.ended", EventLog.study_session_id == old
            )
        ).one()
        assert ended.occurred_at == last_activity


def test_next_returns_a_learning_card_after_ten_minutes(env: ApiEnv) -> None:
    _discovered_term(env)
    env.clock.current = DAY_2_START + timedelta(hours=1)
    session_id = start_session(env.client)

    # Both new cards are rated Good: each goes to the 10-minute learning step.
    for _ in range(2):
        step = env.client.get(f"/api/session/{session_id}/next").json()
        assert step["type"] == "review"
        recorded = _record(env, session_id, step, rating=3)
        assert recorded["state_after"] == "learning"
    step = env.client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "wait"
    until = step["wait"]["until"]
    assert step["progress"]["reviews_done"] == 2
    assert step["progress"]["reviews_remaining"] == 2

    env.clock.advance(5 * 60)
    assert env.client.get(f"/api/session/{session_id}/next").json()["type"] == "wait"
    env.clock.advance(5 * 60 + 1)
    step = env.client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "review"
    assert env.clock.current.isoformat().replace("+00:00", "Z") >= until


def test_done_and_practice_info(env: ApiEnv) -> None:
    # Two recent errors of one category: the plan has a targeted-practice block.
    with Session(env.engine) as session:
        category = add_category(session, "test.preposition")
        for minutes in (10, 20):
            session.add(
                ErrorEvent(
                    category_id=category.id,
                    source="manual",
                    erroneous_text="in campus",
                    correction="on campus",
                    occurred_at=env.clock.current - timedelta(minutes=minutes),
                )
            )
        session.commit()
    session_id = start_session(env.client)
    step = env.client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "practice_info"
    assert step["practice"]["targeted_practice"]["error_count"] == 2
    assert step["progress"]["estimated_seconds_remaining"] == 300.0
    done = env.client.get(f"/api/session/{session_id}/next?practice_seen=true").json()
    assert done["type"] == "done"
    assert done["progress"]["estimated_seconds_remaining"] == 0.0


def test_end_summary_comes_from_the_logs(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    discover(
        env.client,
        item_id,
        session_id,
        personal_sentence="Our design cannot rule out a placebo effect at all.",
    )
    env.clock.advance(900)
    ended = env.client.post(f"/api/session/{session_id}/end")
    assert ended.status_code == 200
    summary = ended.json()["summary"]
    assert summary == {
        "format": "session-1",
        "reviews": 0,
        "failed_reviews": 0,
        "discoveries_started": 1,
        "discoveries_completed": 1,
        "productions": 1,
        "words": 10,
        "duration_ms": 900_000,
        "planned_minutes": 2,
    }
    again = env.client.post(f"/api/session/{session_id}/end")
    assert (again.status_code, code(again)) == (409, "session_closed")
    closed = env.client.get(f"/api/session/{session_id}/next")
    assert (closed.status_code, code(closed)) == (409, "session_closed")


def test_summary_counts_reviews_and_failures(env: ApiEnv) -> None:
    _discovered_term(env)
    env.clock.current = DAY_2_START + timedelta(hours=1)
    session_id = start_session(env.client)
    first = env.client.get(f"/api/session/{session_id}/next").json()
    _record(env, session_id, first, rating=1)
    second = env.client.get(f"/api/session/{session_id}/next").json()
    _record(env, session_id, second, rating=3, answer="rule out")
    summary = env.client.post(f"/api/session/{session_id}/end").json()["summary"]
    assert (summary["reviews"], summary["failed_reviews"]) == (2, 1)
    assert summary["discoveries_started"] == 0


def test_unknown_session(env: ApiEnv) -> None:
    for response in (
        env.client.get("/api/session/999/next"),
        env.client.post("/api/session/999/end"),
    ):
        assert (response.status_code, code(response)) == (404, "session_not_found")


def test_new_items_skip_a_paused_deck(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    deck_id = env.client.get(f"/api/items/{item_id}").json()["decks"][0]["id"]
    paused = env.client.post(f"/api/decks/{deck_id}/status", json={"to": "paused"})
    assert paused.status_code == 200
    step = env.client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "done"
    assert step["progress"]["new_remaining"] == 0


def test_review_steps_never_carry_a_solution(env: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """Walk every step of four months with all template types and look for solution keys."""
    # Seeded fuzz: with the unseeded production generator, the cards sometimes stay below the
    # maturity threshold and the mature exercise types are not reached (flaky test).
    monkeypatch.setattr(fsrs_engine, "_PRODUCTION_RNG", random.Random(0))
    item_ids = [quick_add(env.client, term) for term in ("rule out", "shed light on")]
    for item_id in item_ids:
        write_sheet(env.client, item_id)
        add_all_templates(env.engine, item_id)
    session_id = start_session(env.client)
    seen_types: set[str] = set()
    steps: list[dict] = []
    for item_id in item_ids:
        started = env.client.post(
            f"/api/discovery/{item_id}/start", json={"session_id": session_id}
        ).json()
        steps.append(started)
        steps.append({"exercises": env.client.get(f"/api/discovery/{item_id}/exercises").json()})
        env.client.post(f"/api/discovery/{item_id}/complete", json={"session_id": session_id})
    env.clock.current = DAY_2_START + timedelta(hours=1)
    for _ in range(12):  # sessions, each on the day the next card is due
        session_id = start_session(env.client)
        for _ in range(20):
            step = env.client.get(f"/api/session/{session_id}/next").json()
            steps.append(step)
            if step["type"] == "wait":
                env.clock.current = env.clock.current + timedelta(minutes=11)
                continue
            if step["type"] != "review":
                break
            seen_types.add(step["review"]["exercise_type"])
            _record(env, session_id, step, rating=3)
        with Session(env.engine) as session:
            next_due = session.scalar(select(func.min(Card.due)))
        assert next_due is not None
        env.clock.current = max(env.clock.current, next_due) + timedelta(hours=1)

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys(v)}
        return set()

    for step in steps:
        assert not keys(step) & SOLUTION_KEYS, step
    assert {ex.RECOGNITION, ex.LISTENING, ex.TYPED_RECALL, ex.GAP_FILL} <= seen_types
    assert {ex.SENTENCE_PRODUCTION, ex.SPOKEN_ANSWER} <= seen_types
