"""Cards made from errors and suggestions through the API (M5.a3)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, ErrorEvent
from app.db.taxonomy import sync_taxonomy
from app.domain import exercises as ex
from tests.api.conftest import ApiEnv
from tests.api.session_support import DAY_2_START, code, start_session, table_counts

PREPOSITION = "grammar.preposition.fixed_expression"


@pytest.fixture(autouse=True)
def taxonomy(env: ApiEnv) -> None:
    with Session(env.engine) as session:
        sync_taxonomy(session)
        session.commit()


def add_error(env: ApiEnv, **changes: Any) -> int:
    body = {
        "original_text": "Most of my friends live in campus this year.",
        "erroneous_text": "in campus",
        "correction": "on campus",
        "category_code": PREPOSITION,
        "explanation": "With 'campus', English uses 'on'.",
        **changes,
    }
    response = env.client.post("/api/errors", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_make_a_card_from_an_error(env: ApiEnv) -> None:
    error_id = add_error(env)
    response = env.client.post(f"/api/errors/{error_id}/card", json={})
    assert response.status_code == 201, response.text
    made = response.json()
    assert made["term"] == "on campus"
    assert made["sentence"] == "Most of my friends live on campus this year."
    assert made["due"].startswith("2026-10-17T03:00")  # the start of the next study day

    error = env.client.get(f"/api/errors/{error_id}").json()
    assert error["card"] == {"id": made["item_id"], "term": "on campus"}
    item = env.client.get(f"/api/items/{made['item_id']}").json()
    assert (item["status"], item["term"]) == ("learning", "on campus")
    decks = env.client.get("/api/decks").json()
    assert [(d["name"], d["kind"], d["status"]) for d in decks] == [
        ("Error cards", "error_drill", "active")
    ]
    listed = env.client.get("/api/errors").json()["errors"]
    assert [e["card"] for e in listed] == [error["card"]]


def test_a_second_card_for_the_same_error_is_refused(env: ApiEnv) -> None:
    error_id = add_error(env)
    first = env.client.post(f"/api/errors/{error_id}/card", json={}).json()
    again = env.client.post(f"/api/errors/{error_id}/card", json={})
    assert (again.status_code, code(again)) == (409, "card_exists")
    assert again.json()["detail"]["item_id"] == first["item_id"]


@pytest.mark.parametrize(
    ("changes", "body", "reason"),
    [
        ({"original_text": None}, {}, "no_context"),
        ({"original_text": None}, {"sentence": "He is at home."}, "invalid_sentence"),
        ({}, {"term": "a b c d e f g"}, "invalid_term"),
    ],
)
def test_not_cardable_says_why_and_writes_nothing(
    env: ApiEnv, changes: dict[str, Any], body: dict[str, Any], reason: str
) -> None:
    error_id = add_error(env, **changes)
    before = table_counts(env.engine)
    response = env.client.post(f"/api/errors/{error_id}/card", json=body)
    assert (response.status_code, code(response)) == (422, "not_cardable")
    assert response.json()["detail"]["reason"] == reason
    assert table_counts(env.engine) == before


def test_unknown_error_and_malformed_body(env: ApiEnv) -> None:
    assert env.client.post("/api/errors/99/card", json={}).status_code == 404
    error_id = add_error(env)
    for body in ({"term": ""}, {"sentence": "x" * 401}, {"surprise": 1}):
        assert env.client.post(f"/api/errors/{error_id}/card", json=body).status_code == 422


def test_a_sentence_and_a_term_of_the_user(env: ApiEnv) -> None:
    error_id = add_error(env, original_text=None)
    response = env.client.post(
        f"/api/errors/{error_id}/card", json={"sentence": "We met on campus.", "term": "on campus"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["sentence"] == "We met on campus."


def test_suggestions_then_card_then_dismiss(env: ApiEnv) -> None:
    for _ in range(3):
        add_error(env)
        env.clock.current += timedelta(minutes=5)
    add_error(
        env,
        erroneous_text="in university",
        correction="at university",
        original_text="She is in university.",
    )
    add_error(
        env,
        erroneous_text="in university",
        correction="at university",
        original_text="He is in university.",
    )
    add_error(env, erroneous_text="by purpose", correction="on purpose", original_text=None)

    suggestions = env.client.get("/api/errors/suggestions").json()["suggestions"]
    assert [(s["key"], s["count"], s["term"], s["cardable"]) for s in suggestions] == [
        ("in campus => on campus", 3, "on campus", True),
        ("in university => at university", 2, "at university", True),
    ]
    first = suggestions[0]
    assert first["category"]["code"] == PREPOSITION
    assert first["category"]["label_en"]
    assert len(first["sample_error_ids"]) == 3 and first["error_id"] == first["sample_error_ids"][0]

    assert env.client.post(f"/api/errors/{first['error_id']}/card", json={}).status_code == 201
    dismissed = env.client.post(
        "/api/errors/suggestions/dismiss", json={"key": "in university => at university"}
    )
    assert dismissed.json() == {"dismissed": True}
    assert env.client.post(
        "/api/errors/suggestions/dismiss", json={"key": "in university => at university"}
    ).json() == {"dismissed": False}
    assert env.client.get("/api/errors/suggestions").json() == {"suggestions": []}


def test_suggestion_filters_and_unknown_key(env: ApiEnv) -> None:
    add_error(env)
    add_error(env)
    assert len(env.client.get("/api/errors/suggestions?min_count=3").json()["suggestions"]) == 0
    assert len(env.client.get("/api/errors/suggestions?min_count=1").json()["suggestions"]) == 1
    for query in ("min_count=0", "limit=0", "limit=51"):
        assert env.client.get(f"/api/errors/suggestions?{query}").status_code == 422
    unknown = env.client.post("/api/errors/suggestions/dismiss", json={"key": "a => b"})
    assert (unknown.status_code, code(unknown)) == (404, "suggestion_not_found")
    assert env.client.post("/api/errors/suggestions/dismiss", json={}).status_code == 422


def test_the_card_is_reviewed_and_falling_back_logs_the_same_error_again(env: ApiEnv) -> None:
    error_id = add_error(env)
    made = env.client.post(f"/api/errors/{error_id}/card", json={}).json()
    env.clock.current = DAY_2_START + timedelta(hours=1)
    session_id = start_session(env.client)

    step = env.client.get(f"/api/session/{session_id}/next").json()["review"]
    assert step["exercise_type"] == ex.GAP_FILL
    assert step["prompt"] == {"sentence": "Most of my friends live ___ campus this year."}
    assert "answer" not in str(step) and "on campus" not in str(step)  # active recall

    body = {
        "card_id": step["card_id"],
        "exercise_type": step["exercise_type"],
        "exercise_template_id": step["exercise_template_id"],
        "answer": "in",
        "response_time_ms": 3000,
    }
    graded = env.client.post("/api/reviews/grade", json=body).json()
    assert graded["outcome"] == "wrong"  # "in" is one letter from "on": never a typo
    assert graded["solution"]["sentence"] == "Most of my friends live on campus this year."

    recorded = env.client.post(
        "/api/reviews",
        json={**body, "session_id": session_id, "final_rating": 1, "expected_reps": 0},
    )
    assert recorded.status_code == 200, recorded.text
    again = env.client.get(f"/api/errors/{recorded.json()['error_event_id']}").json()
    assert again["category"]["code"] == PREPOSITION
    assert again["source"] == "review"
    assert (again["erroneous_text"], again["correction"]) == ("in", "on")
    assert again["term"] == {"id": made["item_id"], "term": "on campus"}

    with Session(env.engine) as session:
        card = session.get_one(Card, made["card_id"])
        assert card.reps == 1
        assert session.scalars(select(ErrorEvent)).all().__len__() == 2
