"""Errors from reviews (M5.a1): a typed answer that is wrong because of a lexical confusion
creates one error event when the review is recorded; nothing else does."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, ErrorEvent, EventLog
from app.db.taxonomy import sync_taxonomy
from app.domain import exercises as ex
from app.domain.enums import ItemType
from app.services.review_flow import confusion_category
from tests.api.conftest import ApiEnv
from tests.api.session_support import (
    DAY_2_START,
    add_all_templates,
    discover,
    quick_add,
    sheet_for,
    start_session,
    table_counts,
    write_sheet,
)


@pytest.fixture(autouse=True)
def taxonomy(env: ApiEnv) -> None:
    with Session(env.engine) as session:
        sync_taxonomy(session)
        session.commit()


def _cards(env: ApiEnv, item_id: int) -> dict[str, int]:
    with Session(env.engine) as session:
        return {
            str(card.direction): card.id
            for card in session.scalars(select(Card).where(Card.lexical_item_id == item_id))
        }


def _template_id(env: ApiEnv, item_id: int, exercise_type: str) -> int:
    exercises = env.client.get(f"/api/items/{item_id}/exercises").json()
    return next(e["id"] for e in exercises if e["exercise_type"] == exercise_type)


def _day_two(env: ApiEnv, term: str, sentence: str | None, **sheet: Any) -> tuple[int, int]:
    """A discovered term reviewed on day 2: (item id, session id)."""
    item_id = quick_add(env.client, term, sentence)
    write_sheet(env.client, item_id, sheet_for(term, **sheet))
    discover(env.client, item_id, start_session(env.client))
    env.clock.current = DAY_2_START + timedelta(hours=1)
    return item_id, start_session(env.client)


def _record(
    env: ApiEnv,
    session_id: int,
    card_id: int,
    exercise_type: str,
    template_id: int | None,
    **kw: Any,
) -> Any:
    body = {
        "card_id": card_id,
        "session_id": session_id,
        "exercise_type": exercise_type,
        "exercise_template_id": template_id,
        "answer": None,
        "response_time_ms": 4000,
        "final_rating": 1,
        "expected_reps": 0,
        **kw,
    }
    response = env.client.post("/api/reviews", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _errors(env: ApiEnv) -> list[ErrorEvent]:
    with Session(env.engine) as session:
        return list(session.scalars(select(ErrorEvent).order_by(ErrorEvent.id)))


def test_affect_for_effect_logs_a_wrong_word_error(env: ApiEnv) -> None:
    item_id, session_id = _day_two(
        env, "effect", "The effect of the policy is small.", confusables=[]
    )
    quick_add(env.client, "affect", None)
    cards = _cards(env, item_id)
    typed_recall = _template_id(env, item_id, ex.TYPED_RECALL)
    body = _record(
        env, session_id, cards["productive"], ex.TYPED_RECALL, typed_recall, answer="affect"
    )
    [error] = _errors(env)
    assert body["error_event_id"] == error.id
    assert (error.source, error.review_log_id, error.lexical_item_id) == (
        "review",
        body["review_log_id"],
        item_id,
    )
    assert (error.erroneous_text, error.correction) == ("affect", "effect")
    assert error.production_attempt_id is None
    assert "effect" in error.explanation  # the generic sentence: no sheet entry explains it
    assert "exclure" in error.original_text  # typed recall: the cue
    listed = env.client.get(f"/api/errors/{error.id}").json()
    assert listed["category"]["code"] == "lexis.wrong_word"
    with Session(env.engine) as session:
        event = session.scalars(
            select(EventLog).where(EventLog.event_type == "error.recorded")
        ).one()
        assert event.payload == {
            "error_event_id": error.id,
            "category_code": "lexis.wrong_word",
            "source": "review",
            "lexical_item_id": item_id,
        }
        assert event.study_session_id == session_id


def test_a_gap_fill_pitfall_uses_the_sheet_explanation_and_the_completed_sentence(
    env: ApiEnv,
) -> None:
    pitfall = {
        "wrong": "rule away",
        "right": "rule out",
        "explanation": "The particle is 'out', never 'away'.",
    }
    item_id, session_id = _day_two(
        env, "rule out", "We cannot rule out chance.", french_speaker_pitfalls=[pitfall]
    )
    templates = add_all_templates(env.engine, item_id)
    body = _record(
        env,
        session_id,
        _cards(env, item_id)["productive"],
        ex.GAP_FILL,
        templates[ex.GAP_FILL],
        answer="Rule away",
    )
    [error] = _errors(env)
    assert body["error_event_id"] == error.id
    assert error.original_text == "We cannot Rule away a placebo effect."
    assert error.explanation == "The particle is 'out', never 'away'."
    assert (error.erroneous_text, error.correction) == ("Rule away", "rule out")


def test_the_sheet_confusable_explains_the_difference(env: ApiEnv) -> None:
    item_id, session_id = _day_two(env, "rule out", "We cannot rule out chance.")
    _record(
        env,
        session_id,
        _cards(env, item_id)["productive"],
        ex.TYPED_RECALL,
        _template_id(env, item_id, ex.TYPED_RECALL),
        answer="rule over",
    )
    [error] = _errors(env)
    assert error.explanation == "to govern a country"


@pytest.mark.parametrize("answer", ["rul out", "explain", "", None])
def test_no_error_for_a_typo_an_unknown_word_or_no_answer(env: ApiEnv, answer: str | None) -> None:
    item_id, session_id = _day_two(env, "rule out", "We cannot rule out chance.")
    body = _record(
        env,
        session_id,
        _cards(env, item_id)["productive"],
        ex.TYPED_RECALL,
        _template_id(env, item_id, ex.TYPED_RECALL),
        answer=answer,
    )
    assert body["error_event_id"] is None
    assert _errors(env) == []


def test_no_error_for_a_wrong_choice_or_a_self_graded_type(env: ApiEnv) -> None:
    item_id, session_id = _day_two(env, "rule out", "We cannot rule out chance.")
    templates = add_all_templates(env.engine, item_id)
    cards = _cards(env, item_id)
    step = env.client.get(f"/api/session/{session_id}/next").json()["review"]
    assert step["exercise_type"] == ex.RECOGNITION
    graded = env.client.post(
        "/api/reviews/grade",
        json={
            "card_id": cards["receptive"],
            "exercise_type": ex.RECOGNITION,
            "exercise_template_id": templates[ex.RECOGNITION],
            "choice_index": 0,
            "response_time_ms": 1000,
        },
    ).json()
    wrong = (graded["solution"]["correct_index"] + 1) % 4
    body = _record(
        env,
        session_id,
        cards["receptive"],
        ex.RECOGNITION,
        templates[ex.RECOGNITION],
        choice_index=wrong,
    )
    assert body["error_event_id"] is None
    body = _record(
        env, session_id, cards["productive"], ex.SELF_ASSESSMENT, None, answer="rule over"
    )
    assert body["error_event_id"] is None
    assert _errors(env) == []


def test_grade_and_reveal_still_write_nothing_with_the_taxonomy_loaded(env: ApiEnv) -> None:
    item_id, _ = _day_two(env, "rule out", "We cannot rule out chance.")
    templates = add_all_templates(env.engine, item_id)
    cards = _cards(env, item_id)
    before = table_counts(env.engine)
    for answer in ("rule over", "rul out", "explain"):
        response = env.client.post(
            "/api/reviews/grade",
            json={
                "card_id": cards["productive"],
                "exercise_type": ex.GAP_FILL,
                "exercise_template_id": templates[ex.GAP_FILL],
                "answer": answer,
                "response_time_ms": 1000,
            },
        )
        assert response.status_code == 200
    revealed = env.client.post(
        "/api/reviews/reveal",
        json={"card_id": cards["productive"], "exercise_type": ex.SELF_ASSESSMENT},
    )
    assert revealed.status_code == 200
    assert table_counts(env.engine) == before


@pytest.mark.parametrize(
    ("item_type", "given", "expected", "category"),
    [
        (ItemType.COLLOCATION, "make a conclusion", "draw a conclusion", "lexis.collocation"),
        (
            ItemType.PHRASE,
            "it is worth to note that",
            "it is worth noting that",
            "lexis.wrong_word",
        ),
        (ItemType.SPOKEN_FORMULA, "as you can look", "as you can see", "lexis.collocation"),
        (ItemType.WORD, "affect", "effect", "lexis.wrong_word"),
        (ItemType.COLLOCATION, "make conclusions", "draw a conclusion", "lexis.wrong_word"),
    ],
)
def test_confusion_category(item_type: ItemType, given: str, expected: str, category: str) -> None:
    assert confusion_category(item_type, given, expected) == category
