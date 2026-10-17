"""Deck status and queue endpoints (D-026, D-027) and the plan's pace on each deck."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventLog
from tests.api.conftest import ApiEnv
from tests.api.session_support import code


def _deck(env: ApiEnv, name: str, **fields: Any) -> dict[str, Any]:
    response = env.client.post("/api/decks", json={"name": name, **fields})
    assert response.status_code == 201
    return response.json()


def _status(env: ApiEnv, deck_id: int, to: str) -> Any:
    return env.client.post(f"/api/decks/{deck_id}/status", json={"to": to})


def test_pause_resume_done_reopen(env: ApiEnv) -> None:
    deck = _deck(env, "Causal inference reading")
    assert deck["status"] == "queued"
    assert (deck["pace"], deck["warnings"]) == (None, [])
    for to in ("paused", "active", "done", "active"):
        response = _status(env, deck["id"], to)
        assert response.status_code == 200
        assert response.json()["status"] == to
    with Session(env.engine) as session:
        changes = session.scalars(
            select(EventLog.payload).where(EventLog.event_type == "deck.status_changed")
        ).all()
    assert [(c["from_status"], c["to_status"]) for c in changes] == [
        ("queued", "paused"),
        ("paused", "active"),
        ("active", "done"),
        ("done", "active"),
    ]


def test_invalid_transition(env: ApiEnv) -> None:
    deck = _deck(env, "Talk")
    response = _status(env, deck["id"], "queued")
    assert (response.status_code, code(response)) == (409, "invalid_transition")
    assert response.json()["detail"]["from_status"] == "queued"
    unknown = _status(env, 999, "paused")
    assert (unknown.status_code, code(unknown)) == (404, "deck_not_found")
    bad = _status(env, deck["id"], "sleeping")
    assert (bad.status_code, code(bad)) == (422, "invalid_request")


def test_reorder_queue(env: ApiEnv) -> None:
    a, b, c = (_deck(env, name)["id"] for name in ("A", "B", "C"))
    _status(env, c, "done")
    response = env.client.put("/api/decks/queue", json={"deck_ids": [b, a]})
    assert response.status_code == 200
    positions = {d["id"]: d["queue_position"] for d in response.json()}
    assert (positions[b], positions[a]) == (0, 1)
    for wrong in ([a], [a, b, c], [a, a, b], [a, b, 999]):
        response = env.client.put("/api/decks/queue", json={"deck_ids": wrong})
        assert (response.status_code, code(response)) == (422, "invalid_queue"), wrong


def test_decks_carry_the_plan_pace_and_warnings(env: ApiEnv) -> None:
    deck = _deck(env, "Job talk", deadline="2026-10-19")
    terms = "\n".join(f"- term number {n}" for n in range(60))
    preview = env.client.post("/api/import/preview", json={"text": terms}).json()
    rows = [{"term": r["term"]} for r in preview["rows"]]
    committed = env.client.post(
        "/api/import/commit",
        json={
            "header": preview["header"],
            "rows": rows,
            "target": {"deck_id": deck["id"]},
            "intake": "queued",
        },
    )
    assert committed.status_code == 200
    listed = {d["id"]: d for d in env.client.get("/api/decks").json()}[deck["id"]]
    assert listed["pace"] == {
        "deck_id": deck["id"],
        "deadline": "2026-10-19",
        "remaining": 60,
        "days_left": 3,
        "required_per_day": 20,
    }
    assert [w["code"] for w in listed["warnings"]] == ["deadline_unrealistic"]
    plan = env.client.get("/api/session/today").json()["plan"]
    assert listed["warnings"] == [
        w for w in plan["warnings"] if w["code"] == "deadline_unrealistic"
    ]
