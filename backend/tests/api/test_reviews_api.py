"""Review endpoints: grade (writes nothing), record (server-side auto rating), reveal."""

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Card, LexicalItem, ReviewLog
from app.domain import exercises as ex
from tests.api.conftest import ApiEnv
from tests.api.session_support import (
    DAY_2_START,
    RECOGNITION,
    add_all_templates,
    code,
    discover,
    quick_add,
    sheet_for,
    start_session,
    table_counts,
    write_sheet,
)


def _ready(env: ApiEnv, *, templates: bool = True) -> tuple[int, dict[str, Any]]:
    """Day 2 of a discovered term: (session id, {direction: review step})."""
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    if templates:
        add_all_templates(env.engine, item_id)
    discover(env.client, item_id, start_session(env.client))
    env.clock.current = DAY_2_START + timedelta(hours=1)
    session_id = start_session(env.client)
    step = env.client.get(f"/api/session/{session_id}/next").json()
    with Session(env.engine) as session:
        cards = {
            card.direction: card for card in session.query(Card).filter_by(lexical_item_id=item_id)
        }
    steps = {"receptive": step["review"]}
    assert step["review"]["card_id"] == cards["receptive"].id
    steps["productive"] = {
        "card_id": cards["productive"].id,
        "exercise_type": ex.TYPED_RECALL,
        "exercise_template_id": _typed_recall_id(env, item_id),
    }
    return session_id, steps


def _typed_recall_id(env: ApiEnv, item_id: int) -> int:
    exercises = env.client.get(f"/api/items/{item_id}/exercises").json()
    return next(e["id"] for e in exercises if e["exercise_type"] == ex.TYPED_RECALL)


def _body(step: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "card_id": step["card_id"],
        "exercise_type": step["exercise_type"],
        "exercise_template_id": step["exercise_template_id"],
        "answer": None,
        "response_time_ms": 5000,
        **changes,
    }


def _record(env: ApiEnv, session_id: int, step: dict[str, Any], **changes: Any) -> Any:
    body = {**_body(step), "session_id": session_id, "final_rating": 3, "expected_reps": 0}
    return env.client.post("/api/reviews", json={**body, **changes})


def test_grade_writes_nothing(env: ApiEnv) -> None:
    _, steps = _ready(env)
    before = table_counts(env.engine)
    for answer in ("rule out", "rul out", "affect", ""):
        response = env.client.post(
            "/api/reviews/grade", json=_body(steps["productive"], answer=answer)
        )
        assert response.status_code == 200
    receptive = steps["receptive"]
    for index in range(4):
        env.client.post("/api/reviews/grade", json=_body(receptive, choice_index=index))
    assert table_counts(env.engine) == before


def test_choice_grading_and_the_stored_answer(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    receptive = steps["receptive"]
    assert receptive["exercise_type"] == ex.RECOGNITION
    options = receptive["prompt"]["options"]
    right = options.index(RECOGNITION["meaning"])
    graded = env.client.post("/api/reviews/grade", json=_body(receptive, choice_index=right)).json()
    assert (graded["outcome"], graded["proposed_rating"]) == ("exact", 3)
    assert graded["solution"]["correct_index"] == right
    assert graded["sheet_summary"]["translation_fr"] == ["exclure", "écarter"]
    wrong = (right + 1) % 4
    graded = env.client.post("/api/reviews/grade", json=_body(receptive, choice_index=wrong)).json()
    assert (graded["outcome"], graded["proposed_rating"]) == ("wrong", 1)
    out_of_range = env.client.post("/api/reviews/grade", json=_body(receptive, choice_index=4))
    assert (out_of_range.status_code, code(out_of_range)) == (422, "exercise_mismatch")

    recorded = _record(env, session_id, receptive, choice_index=wrong, final_rating=1)
    assert recorded.status_code == 200
    with Session(env.engine) as session:
        log = session.get_one(ReviewLog, recorded.json()["review_log_id"])
        assert log.answer_text == options[wrong]
        assert (log.auto_rating, log.final_rating) == (1, 1)


def test_auto_rating_is_computed_by_the_server(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    productive = steps["productive"]
    # The client cannot send its own proposal.
    lying = _record(env, session_id, productive, answer="explain", auto_rating=3)
    assert (lying.status_code, code(lying)) == (422, "invalid_request")
    # A wrong answer recorded as Easy: the stored proposal is still Again.
    recorded = _record(env, session_id, productive, answer="explain", final_rating=4)
    assert recorded.status_code == 200
    with Session(env.engine) as session:
        log = session.get_one(ReviewLog, recorded.json()["review_log_id"])
        assert (log.auto_rating, log.final_rating) == (1, 4)


def test_confusion_with_another_library_term_is_wrong(env: ApiEnv) -> None:
    item_id = quick_add(env.client, "effect", "The effect of the policy is small.")
    write_sheet(env.client, item_id, sheet_for("effect", confusables=[]))
    discover(env.client, item_id, start_session(env.client))
    env.clock.current = DAY_2_START + timedelta(hours=1)
    with Session(env.engine) as session:
        card = session.query(Card).filter_by(lexical_item_id=item_id, direction="productive").one()
    body = {
        "card_id": card.id,
        "exercise_type": ex.TYPED_RECALL,
        "exercise_template_id": _typed_recall_id(env, item_id),
        "answer": "affect",
        "response_time_ms": 4000,
    }
    assert env.client.post("/api/reviews/grade", json=body).json()["outcome"] == "typo"
    quick_add(env.client, "affect", None)
    graded = env.client.post("/api/reviews/grade", json=body).json()
    assert (graded["outcome"], graded["proposed_rating"], graded["diff"]) == ("wrong", 1, None)


def test_a_confusable_of_the_sheet_is_wrong(env: ApiEnv) -> None:
    _, steps = _ready(env)
    graded = env.client.post(
        "/api/reviews/grade", json=_body(steps["productive"], answer="rule over")
    ).json()
    assert graded["outcome"] == "wrong"


def test_card_changed_on_a_second_submission(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    productive = steps["productive"]
    first = _record(env, session_id, productive, answer="rule out")
    assert first.status_code == 200
    body = first.json()
    assert body["state_after"] == "learning"
    assert body["item_status"] == "learning"
    assert body["item_status_changed"] is False
    again = _record(env, session_id, productive, answer="rule out")
    assert (again.status_code, code(again)) == (409, "card_changed")


def test_review_not_allowed_for_an_archived_term(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    with Session(env.engine) as session:
        card = session.get_one(Card, steps["productive"]["card_id"])
        session.get_one(LexicalItem, card.lexical_item_id).status = "archived"
        session.commit()
    response = _record(env, session_id, steps["productive"], answer="rule out")
    assert (response.status_code, code(response)) == (409, "review_not_allowed")


def test_not_due_unless_due_today(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    productive = steps["productive"]
    with Session(env.engine) as session:
        card = session.get_one(Card, productive["card_id"])
        card.due = env.clock.current + timedelta(days=3)
        session.commit()
    response = _record(env, session_id, productive, answer="rule out")
    assert (response.status_code, code(response)) == (409, "not_due")
    # Due later today: accepted.
    with Session(env.engine) as session:
        session.get_one(Card, productive["card_id"]).due = env.clock.current + timedelta(hours=5)
        session.commit()
    assert _record(env, session_id, productive, answer="rule out").status_code == 200


def test_response_time_is_capped(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    recorded = _record(
        env, session_id, steps["productive"], answer="rule out", response_time_ms=999_999
    )
    with Session(env.engine) as session:
        log = session.get_one(ReviewLog, recorded.json()["review_log_id"])
        assert log.response_time_ms == 300_000
    negative = _record(env, session_id, steps["receptive"], response_time_ms=-1)
    assert (negative.status_code, code(negative)) == (422, "invalid_request")


def test_unknown_card_and_mismatched_exercises(env: ApiEnv) -> None:
    session_id, steps = _ready(env)
    missing = env.client.post("/api/reviews/grade", json=_body(steps["productive"], card_id=999))
    assert (missing.status_code, code(missing)) == (404, "card_not_found")
    recognition_id = steps["receptive"]["exercise_template_id"]
    cases = [
        # a receptive type on a productive card
        _body(
            steps["productive"], exercise_type=ex.RECOGNITION, exercise_template_id=recognition_id
        ),
        # a template of another type
        _body(steps["productive"], exercise_template_id=recognition_id),
        # a template-based type without a template
        _body(steps["productive"], exercise_template_id=None),
        # self-assessment with a template
        _body(steps["productive"], exercise_type=ex.SELF_ASSESSMENT),
        # unknown type
        _body(steps["productive"], exercise_type="karaoke"),
    ]
    for body in cases:
        response = env.client.post("/api/reviews/grade", json=body)
        assert (response.status_code, code(response)) == (422, "exercise_mismatch"), body
    both = env.client.post("/api/reviews/grade", json={**_body(steps["productive"]), "item_id": 1})
    assert (both.status_code, code(both)) == (422, "invalid_request")
    other = quick_add(env.client, "shed light on", None)
    write_sheet(env.client, other)
    foreign = _typed_recall_id(env, other)
    response = env.client.post(
        "/api/reviews/grade", json=_body(steps["productive"], exercise_template_id=foreign)
    )
    assert (response.status_code, code(response)) == (422, "exercise_mismatch")
    closed = env.client.post(f"/api/session/{session_id}/end")
    assert closed.status_code == 200
    after_end = _record(env, session_id, steps["productive"], answer="rule out")
    assert (after_end.status_code, code(after_end)) == (409, "session_closed")
    unknown_session = _record(env, 999, steps["productive"], answer="rule out")
    assert (unknown_session.status_code, code(unknown_session)) == (404, "session_not_found")


def test_reveal_only_for_self_graded_exercises(env: ApiEnv) -> None:
    _, steps = _ready(env)
    card_id = steps["productive"]["card_id"]
    before = table_counts(env.engine)
    revealed = env.client.post(
        "/api/reviews/reveal", json={"card_id": card_id, "exercise_type": ex.SELF_ASSESSMENT}
    )
    assert revealed.status_code == 200
    assert revealed.json()["solution"]["term"] == "rule out"
    assert table_counts(env.engine) == before
    graded_type = env.client.post(
        "/api/reviews/reveal",
        json={
            "card_id": card_id,
            "exercise_type": ex.TYPED_RECALL,
            "exercise_template_id": steps["productive"]["exercise_template_id"],
        },
    )
    assert (graded_type.status_code, code(graded_type)) == (422, "exercise_mismatch")


def test_sentence_production_warns_when_the_term_is_missing(env: ApiEnv) -> None:
    _, steps = _ready(env)
    exercises = env.client.get(
        f"/api/items/{_item_of(env, steps['productive']['card_id'])}/exercises"
    ).json()
    production = next(e for e in exercises if e["exercise_type"] == ex.SENTENCE_PRODUCTION)
    body = _body(
        steps["productive"],
        exercise_type=ex.SENTENCE_PRODUCTION,
        exercise_template_id=production["id"],
    )
    missing = env.client.post(
        "/api/reviews/grade", json={**body, "answer": "We exclude chance."}
    ).json()
    assert (missing["outcome"], missing["proposed_rating"]) == (None, None)
    assert missing["warnings"] == ["term_missing"]
    assert missing["solution"] == {"example_answer": "We can rule out chance."}
    used = env.client.post(
        "/api/reviews/grade", json={**body, "answer": "We ruled out chance."}
    ).json()
    assert used["warnings"] == []


def _item_of(env: ApiEnv, card_id: int) -> int:
    with Session(env.engine) as session:
        return session.get_one(Card, card_id).lexical_item_id


def test_self_assessment_without_templates(env: ApiEnv) -> None:
    session_id, steps = _ready(env, templates=False)
    receptive = steps["receptive"]
    assert receptive["exercise_type"] == ex.SELF_ASSESSMENT
    assert receptive["self_graded"] is True
    assert receptive["input"] == "none"
    graded = env.client.post("/api/reviews/grade", json=_body(receptive)).json()
    assert (graded["outcome"], graded["proposed_rating"]) == (None, None)
    recorded = _record(env, session_id, receptive, final_rating=2)
    with Session(env.engine) as session:
        log = session.get_one(ReviewLog, recorded.json()["review_log_id"])
        assert (log.exercise_type, log.auto_rating, log.final_rating) == (
            "self_assessment",
            None,
            2,
        )
        assert log.exercise_template_id is None
