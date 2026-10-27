"""`/api/consolidation` (M7.a1): readiness, creating a task with the scripted provider, statuses,
export, and the task in today's plan."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, Success
from app.ai.types import ErrorKind
from app.db.models import Card, ConsolidationTask, EventLog
from app.domain.consolidation import term_ref
from app.domain.enums import DeckKind, DeckStatus
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code, start_session
from tests.consolidation_deck_support import ready_deck
from tests.consolidation_support import task_output

FAR = datetime(2035, 1, 1, tzinfo=UTC)


@pytest.fixture
def deck_id(fake_env: FakeAiEnv) -> int:
    with Session(fake_env.engine) as session:
        deck, _ = ready_deck(session, 10)
        for card in session.scalars(select(Card)):
            card.due = FAR  # nothing to review today: the plan is only the consolidation block
        session.commit()
        return deck.id


def create(env: FakeAiEnv, deck_id: int, **extra: Any) -> Any:
    return env.client.post(
        "/api/consolidation/tasks", json={"deck_id": deck_id, "task_type": "talk", **extra}
    )


def refs(count: int) -> list[str]:
    return [term_ref(i) for i in range(count)]


def test_decks_ready_and_not(fake_env: FakeAiEnv, deck_id: int) -> None:
    with Session(fake_env.engine) as session:
        other, _ = ready_deck(session, 3, name="Too small")
        drill, _ = ready_deck(session, 10, name="Mistakes")
        drill.kind = DeckKind.ERROR_DRILL
        done, _ = ready_deck(session, 10, name="Finished")
        done.status = DeckStatus.DONE
        session.commit()
    rows = {row["name"]: row for row in fake_env.client.get("/api/consolidation/decks").json()}
    ready = rows["Causal inference reading"]
    assert ready == {
        "deck_id": deck_id,
        "name": "Causal inference reading",
        "ready": True,
        "reason": None,
        "ratio": 1.0,
        "stable_cards": 10,
        "productive_cards": 10,
        "threshold_ratio": 0.8,
        "min_stability_days": 7,
        "candidates": 10,
        "open_task_id": None,
    }
    assert rows["Too small"]["reason"] == "not_enough_candidates"
    assert rows["Mistakes"]["reason"] == "excluded_kind"
    assert rows["Finished"]["reason"] == "deck_done"


def test_creating_a_task_with_the_ai(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Success(content=task_output(refs(10))))
    response = create(fake_env, deck_id, term_count=10)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["source"], body["reason"]) == ("ok", "ai", None)
    task = body["task"]
    assert task["status"] == "proposed" and task["task_type"] == "talk"
    assert task["deck"] == {"id": deck_id, "name": "Causal inference reading"}
    assert task["title"]["en"] and task["title"]["fr"]
    assert len(task["targets"]) == 10 and task["attempts"] == []
    assert task["targets"][0]["item_status"] == "consolidated"
    assert task["targets"][0]["used_correctly_count"] == 0
    assert sorted(i for s in task["sections"] for i in s["item_ids"]) == sorted(
        t["item_id"] for t in task["targets"]
    )
    assert fake_env.client.get(f"/api/consolidation/tasks/{task['id']}").json() == task
    page = fake_env.client.get("/api/consolidation/tasks").json()
    assert page["total"] == 1 and page["items"][0] == task


def test_a_template_without_ai(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Failure(ErrorKind.AUTH))
    response = create(fake_env, deck_id, task_type="speech")
    assert response.status_code == 201
    body = response.json()
    assert (body["source"], body["reason"]) == ("template", "auth")
    assert body["task"]["task_type"] == "speech" and len(body["task"]["targets"]) == 10


def test_creation_refusals(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Failure(ErrorKind.AUTH))
    assert code(create(fake_env, 999)) == "deck_not_found"
    assert create(fake_env, deck_id, term_count=7).status_code == 422
    assert code(create(fake_env, deck_id, term_count=16)) == "invalid_request"
    assert create(fake_env, deck_id, task_type="poem").status_code == 422
    first = create(fake_env, deck_id).json()["task"]["id"]
    again = create(fake_env, deck_id)
    assert again.status_code == 409 and code(again) == "task_open"
    assert again.json()["detail"]["task_id"] == first
    with Session(fake_env.engine) as session:
        other, _ = ready_deck(session, 5, name="Small")
        session.commit()
        small = other.id
    refused = create(fake_env, small)
    assert refused.status_code == 409 and code(refused) == "not_ready"
    assert refused.json()["detail"]["reason"] == "not_enough_candidates"


def test_statuses(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Failure(ErrorKind.AUTH))
    task_id = create(fake_env, deck_id).json()["task"]["id"]
    url = f"/api/consolidation/tasks/{task_id}/status"
    skipped = fake_env.client.post(url, json={"to": "completed"})
    assert skipped.status_code == 409 and code(skipped) == "invalid_transition"
    assert fake_env.client.post(url, json={"to": "accepted"}).json()["status"] == "accepted"
    assert fake_env.client.post(url, json={"to": "completed"}).json()["status"] == "completed"
    assert code(fake_env.client.post(url, json={"to": "dismissed"})) == "invalid_transition"
    assert fake_env.client.post(url, json={"to": "bogus"}).status_code == 422
    with Session(fake_env.engine) as session:
        task = session.get_one(ConsolidationTask, task_id)
        assert str(task.status) == "done" and task.completed_at is not None
    assert code(
        fake_env.client.post("/api/consolidation/tasks/999/status", json={"to": "accepted"})
    ) == ("task_not_found")
    assert code(fake_env.client.get("/api/consolidation/tasks/999")) == "task_not_found"
    filtered = fake_env.client.get("/api/consolidation/tasks?status=completed").json()
    assert filtered["total"] == 1
    assert fake_env.client.get("/api/consolidation/tasks?status=proposed").json()["total"] == 0


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_export(fake_env: FakeAiEnv, deck_id: int, lang: str) -> None:
    fake_env.script(Success(content=task_output(refs(10))))
    task_id = create(fake_env, deck_id, term_count=10).json()["task"]["id"]
    response = fake_env.client.get(f"/api/consolidation/tasks/{task_id}/export?lang={lang}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="consolidation-task-{task_id}-{lang}.md"'
    )
    assert "**term number 1**" in response.text
    assert ("Écoute tout mon exposé" in response.text) is (lang == "fr")
    assert (
        fake_env.client.get(f"/api/consolidation/tasks/{task_id}/export?lang=de").status_code == 422
    )
    assert code(fake_env.client.get("/api/consolidation/tasks/999/export")) == "task_not_found"


def test_the_task_is_in_today_plan_and_practice_info(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Failure(ErrorKind.AUTH))
    task_id = create(fake_env, deck_id).json()["task"]["id"]
    plan = fake_env.client.get("/api/session/today").json()["plan"]
    entries = [e for b in plan["blocks"] if b["kind"] == "consolidation" for e in b["entries"]]
    assert [e["consolidation_task_id"] for e in entries] == [task_id]
    session_id = start_session(fake_env.client)
    step = fake_env.client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "practice_info"
    assert step["practice"]["consolidation_task_id"] == task_id


def test_events_carry_no_free_text(fake_env: FakeAiEnv, deck_id: int) -> None:
    fake_env.script(Success(content=task_output(refs(10))))
    create(fake_env, deck_id, term_count=10)
    with Session(fake_env.engine) as session:
        payload = session.scalars(
            select(EventLog.payload).where(EventLog.event_type == "consolidation.task_created")
        ).one()
    assert set(payload) == {"task_id", "deck_id", "task_type", "source", "term_count"}
    assert payload["term_count"] == 10
