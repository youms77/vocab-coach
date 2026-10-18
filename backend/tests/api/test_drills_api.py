"""`/api/drills`: generation (scripted fake provider), active recall, exact grading, errors."""

import sqlite3
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import FakeProvider, Success
from app.ai.types import ProviderRequest, ProviderResponse
from app.db.models import ErrorEvent, ProductionAttempt
from app.domain.drills import SOLUTION_KEYS, options_order
from app.domain.enums import ErrorSource
from app.services import error_log
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code
from tests.drill_support import BROKEN, FIXED, broken, choice_item, drill_output, gap_item
from tests.library_support import count, events

TENSE = "grammar.tense.past_simple_vs_present_perfect"


def _create(env: FakeAiEnv, category: str = FIXED, **extra: Any) -> Any:
    return env.client.post("/api/drills", json={"category_code": category, **extra})


def _drill(env: FakeAiEnv, output: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    env.script(Success(content=output or drill_output(extra.get("count", 10))))
    response = _create(env, **extra)
    assert response.status_code == 201, response.text
    return response.json()["drill"]


def _answer(env: FakeAiEnv, drill_id: int, index: int, **body: Any) -> Any:
    return env.client.post(
        f"/api/drills/{drill_id}/items/{index}/answer", json={"response_time_ms": 2000, **body}
    )


def _record(env: FakeAiEnv, code_: str, source: ErrorSource, wrong: str, hours_ago: int) -> None:
    with Session(env.engine) as session:
        error_log.record_error(
            session,
            source=source,
            category=error_log.active_category(session, code_),
            erroneous_text=wrong,
            correction="right form",
            at=env.clock.now() - timedelta(hours=hours_ago),
        )
        session.commit()


def _keys(value: Any) -> set[str]:
    """Every key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


# --- Generation ----------------------------------------------------------------------------------


def test_a_drill_is_generated_stored_and_shown_without_solutions(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=drill_output()))
    response = _create(fake_env)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["reason"]) == ("ok", None)
    drill = body["drill"]
    assert drill["category"]["code"] == FIXED and drill["category"]["label_en"]
    assert drill["rule_en"].startswith("Some phrases") and drill["rule_fr"]
    assert len(drill["items"]) == 10 and drill["completed"] is False
    assert drill["score"] == {"correct": 0, "wrong": 0, "empty": 0, "answered": 0, "total": 10}
    assert [item["index"] for item in drill["items"]] == list(range(10))
    assert drill["items"][0]["options"] is None and drill["items"][1]["options"] is not None
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, drill["id"])
        assert attempt is not None
        assert (attempt.kind, attempt.prompt_text, attempt.word_count, attempt.text) == (
            "drill",
            FIXED,
            0,
            "",
        )
        feedback = attempt.ai_feedback or {}
        assert feedback["format"] == "drill-1" and feedback["answers"] == []
        assert feedback["prompt_version"] == "targeted_drill.v1"
        assert feedback["items"][1]["answer"] == "at"  # solutions stay server side
        assert attempt.ai_call_id is not None
        [generated] = events(session, "drill.generated")
        assert generated["drill_id"] == drill["id"] and generated["items"] == 10
        assert generated["category_code"] == FIXED


def test_the_inputs_are_the_category_family_and_recent_non_drill_errors(
    fake_env: FakeAiEnv,
) -> None:
    for hours in range(1, 7):
        _record(fake_env, FIXED, ErrorSource.WRITING, f"writing mistake {hours}", hours)
    _record(fake_env, FIXED, ErrorSource.DRILL, "drill mistake", 0)
    _record(fake_env, TENSE, ErrorSource.WRITING, "tense mistake", 0)
    _drill(fake_env, category="grammar.preposition", output=drill_output())
    [request] = fake_env.provider.requests
    user = request.user
    assert "grammar.preposition: " in user and f"{FIXED}: " in user  # the family
    assert "grammar.tense" not in user
    assert "drill mistake" not in user and "tense mistake" not in user
    assert [n for n in range(1, 7) if f"writing mistake {n}" in user] == [1, 2, 3, 4, 5]
    assert "Number of items: 10" in user
    assert user.count("<<<USER_DATA") == 2  # the category and the errors are data


@pytest.mark.parametrize(
    ("category", "status", "error_code"),
    [
        ("grammar", 422, "not_drillable"),
        ("pronunciation.sound", 422, "not_drillable"),
        ("grammar.invented", 404, "category_not_found"),
    ],
)
def test_refused_categories(
    fake_env: FakeAiEnv, category: str, status: int, error_code: str
) -> None:
    response = _create(fake_env, category)
    assert (response.status_code, code(response)) == (status, error_code)
    assert fake_env.provider.calls == 0


def test_proposed_and_rejected_categories_are_refused(fake_env: FakeAiEnv) -> None:
    with Session(fake_env.engine) as session:
        outcome = error_log.propose_category(
            session,
            error_log.Proposal(
                parent_code="grammar.preposition",
                slug="campus_words",
                label_en="Campus words",
                label_fr="Mots du campus",
                description_en="Prepositions with places of the university.",
            ),
            at=fake_env.clock.now(),
        )
        session.commit()
        proposed_id = outcome.category.id
    response = _create(fake_env, "grammar.preposition.campus_words")
    assert (response.status_code, code(response)) == (422, "not_drillable")
    resolve = f"/api/error-categories/{proposed_id}/resolve"
    assert fake_env.client.post(resolve, json={"decision": "reject"}).status_code == 200
    rejected = _create(fake_env, "grammar.preposition.campus_words")
    assert (rejected.status_code, code(rejected)) == (422, "not_drillable")
    assert fake_env.provider.calls == 0


def test_request_validation(fake_env: FakeAiEnv) -> None:
    for count_ in (4, 16):
        response = _create(fake_env, count=count_)
        assert (response.status_code, code(response)) == (422, "invalid_request")
    session = _create(fake_env, study_session_id=999)
    assert (session.status_code, code(session)) == (404, "session_not_found")
    assert fake_env.provider.calls == 0


@pytest.mark.parametrize("change", BROKEN)
def test_a_broken_drill_is_repaired_once_then_incomplete(fake_env: FakeAiEnv, change: str) -> None:
    fake_env.script(Success(content=broken(change)))
    response = _create(fake_env)
    assert response.status_code == 200
    assert response.json() == {"status": "incomplete", "reason": None, "drill": None}
    assert fake_env.provider.calls == 2
    with Session(fake_env.engine) as session:
        assert count(session, ProductionAttempt) == 0
        assert events(session, "drill.generated") == []


def test_an_unavailable_ai_writes_nothing(fake_env: FakeAiEnv) -> None:
    fake_env.provider.configured = False
    response = _create(fake_env)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "no_provider_configured"
    with Session(fake_env.engine) as session:
        assert count(session, ProductionAttempt) == 0


def test_no_write_transaction_is_open_during_the_ai_call(fake_env: FakeAiEnv) -> None:
    path = fake_env.db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    class Probing(FakeProvider):
        def generate_json(self, request: ProviderRequest) -> ProviderResponse:
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
            probes.append("free")
            return super().generate_json(request)

    fake_env.use(Probing("fake", [Success(content=drill_output())]))
    assert _create(fake_env).status_code == 201
    assert probes == ["free"]


# --- Active recall -------------------------------------------------------------------------------


def test_no_unanswered_item_leaks_its_solution_anywhere(fake_env: FakeAiEnv) -> None:
    ids = []
    for count_ in (5, 10, 15):
        created = _drill(fake_env, drill_output(count_), count=count_)
        ids.append(created["id"])
        assert all(not SOLUTION_KEYS & _keys(item) for item in created["items"])
    # Answer one item of the first drill: only that item carries its result.
    _answer(fake_env, ids[0], 0, answer="on")
    responses = [fake_env.client.get(f"/api/drills/{i}").json() for i in ids]
    responses += fake_env.client.get("/api/drills").json()["items"]
    walked = 0
    for drill in responses:
        for item in drill["items"]:
            if item["answered"]:
                assert item["result"]["expected"] == "on"
                continue
            assert item["result"] is None
            assert not SOLUTION_KEYS & _keys(item), item
            walked += 1
    assert walked == 2 * (5 + 10 + 15) - 2
    # The productions routes never show a drill's feedback.
    listed = fake_env.client.get("/api/productions", params={"kind": "drill"}).json()
    assert listed["total"] == 3
    for production in listed["items"]:
        assert production["feedback"] is None and production["corrected"] is False
        assert not SOLUTION_KEYS & _keys(production)
    one = fake_env.client.get(f"/api/productions/{ids[1]}").json()
    assert one["feedback"] is None


def test_the_options_order_is_deterministic_and_computed(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env)
    again = fake_env.client.get(f"/api/drills/{drill['id']}").json()
    assert [i["options"] for i in drill["items"]] == [i["options"] for i in again["items"]]
    stored = drill_output()["items"]
    for index, item in enumerate(drill["items"]):
        if item["kind"] == "choice":
            assert item["options"] == options_order(drill["id"], index, stored[index]["options"])


# --- Answering -----------------------------------------------------------------------------------


def _tense_drill(env: FakeAiEnv) -> dict[str, Any]:
    output = drill_output(5)
    output["items"][0] = gap_item(
        0,
        sentence="The data ___ cleaned since Monday.",
        answer="has been",
        accepted=["'s been"],
        category_code=TENSE,
        explanation_en="Since Monday links the past to now: present perfect.",
        explanation_fr="Since Monday relie le passé au présent : present perfect.",
    )
    for item in output["items"][1:]:
        item["category_code"] = TENSE
    return _drill(env, output, category="grammar.tense", count=5)


def test_a_wrong_answer_is_graded_exactly_and_logged(fake_env: FakeAiEnv) -> None:
    drill = _tense_drill(fake_env)
    response = _answer(fake_env, drill["id"], 0, answer="had been")
    body = response.json()
    assert response.status_code == 200, body
    assert body["result"] == {
        "outcome": "wrong",
        "expected": "has been",
        "accepted": ["'s been"],
        "correct_index": None,
        "explanation_en": "Since Monday links the past to now: present perfect.",
        "explanation_fr": "Since Monday relie le passé au présent : present perfect.",
        "given": "had been",
    }
    error_id = body["error_event_id"]
    assert error_id is not None
    error = fake_env.client.get(f"/api/errors/{error_id}").json()
    assert error["source"] == "drill"
    assert error["erroneous_text"] == "The data had been cleaned since Monday."
    assert error["correction"] == "The data has been cleaned since Monday."
    assert error["original_text"] == "The data ___ cleaned since Monday."
    assert error["alternatives"] == ["The data 's been cleaned since Monday."]
    assert error["category"]["code"] == TENSE
    assert error["explanation"] == "Since Monday links the past to now: present perfect."
    assert error["explanation_fr"] == "Since Monday relie le passé au présent : present perfect."
    assert error["production_attempt_id"] == drill["id"]
    listed = fake_env.client.get("/api/errors", params={"source": "drill"}).json()
    assert [e["id"] for e in listed["errors"]] == [error_id]
    item = body["drill"]["items"][0]
    assert item["answered"] and item["result"]["outcome"] == "wrong"
    with Session(fake_env.engine) as session:
        [answered] = events(session, "drill.item_answered")
        assert answered == {
            "drill_id": drill["id"],
            "index": 0,
            "category_code": TENSE,
            "outcome": "wrong",
            "response_time_ms": 2000,
        }


def test_exact_and_empty_answers(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env, count=5)
    exact = _answer(fake_env, drill["id"], 0, answer=" On ").json()
    assert exact["result"]["outcome"] == "exact" and exact["error_event_id"] is None
    empty = _answer(fake_env, drill["id"], 2, answer="   ").json()
    assert empty["result"]["outcome"] == "empty" and empty["error_event_id"] is None
    no_choice = _answer(fake_env, drill["id"], 1).json()
    assert no_choice["result"]["outcome"] == "empty"
    with Session(fake_env.engine) as session:
        assert count(session, ErrorEvent) == 0


def test_a_choice_is_graded_on_the_shown_order(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env, count=5)
    options = drill["items"][1]["options"]
    right = options.index("at")
    good = _answer(fake_env, drill["id"], 1, choice_index=right).json()
    assert good["result"]["outcome"] == "exact" and good["result"]["correct_index"] == right
    wrong_index = (right + 1) % len(options)
    bad = _answer(fake_env, drill["id"], 3, choice_index=wrong_index).json()
    assert bad["result"]["outcome"] == "wrong" and bad["result"]["given"] == options[wrong_index]
    error = fake_env.client.get(f"/api/errors/{bad['error_event_id']}").json()
    assert error["erroneous_text"] == choice_item(3)["sentence"].replace(
        "___", options[wrong_index]
    )


def test_refusals_when_answering(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env, count=5)
    drill_id = drill["id"]
    assert _answer(fake_env, drill_id, 0, answer="on").status_code == 200
    again = _answer(fake_env, drill_id, 0, answer="on")
    assert (again.status_code, code(again)) == (409, "already_answered")
    gap_choice = _answer(fake_env, drill_id, 2, choice_index=0)
    assert (gap_choice.status_code, code(gap_choice)) == (422, "exercise_mismatch")
    text_on_choice = _answer(fake_env, drill_id, 1, answer="at")
    assert (text_on_choice.status_code, code(text_on_choice)) == (422, "exercise_mismatch")
    out_of_range = _answer(fake_env, drill_id, 1, choice_index=7)
    assert (out_of_range.status_code, code(out_of_range)) == (422, "exercise_mismatch")
    item = _answer(fake_env, drill_id, 5, answer="on")
    assert (item.status_code, code(item)) == (404, "item_not_found")
    missing = _answer(fake_env, 999, 0, answer="on")
    assert (missing.status_code, code(missing)) == (404, "drill_not_found")
    writing = fake_env.client.post("/api/productions", json={"kind": "writing", "text": "Fine."})
    not_a_drill = _answer(fake_env, writing.json()["id"], 0, answer="on")
    assert (not_a_drill.status_code, code(not_a_drill)) == (404, "drill_not_found")
    negative = _answer(fake_env, drill_id, 2, answer="on", response_time_ms=-1)
    assert negative.status_code == 422
    with Session(fake_env.engine) as session:
        assert len(events(session, "drill.item_answered")) == 1


def test_the_last_answer_completes_the_drill(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env, count=5)
    drill_id = drill["id"]
    right = drill["items"][1]["options"].index("at")
    _answer(fake_env, drill_id, 0, answer="on")
    _answer(fake_env, drill_id, 1, choice_index=right)
    _answer(fake_env, drill_id, 2, answer="in")
    _answer(fake_env, drill_id, 3)
    with Session(fake_env.engine) as session:
        assert events(session, "drill.completed") == []
    last = _answer(fake_env, drill_id, 4, answer="on", response_time_ms=900_000).json()
    assert last["drill"]["completed"] is True
    assert last["drill"]["score"] == {
        "correct": 3,
        "wrong": 1,
        "empty": 1,
        "answered": 5,
        "total": 5,
    }
    with Session(fake_env.engine) as session:
        [completed] = events(session, "drill.completed")
        assert completed == {
            "drill_id": drill_id,
            "category_code": FIXED,
            "items": 5,
            "correct": 3,
            "wrong": 1,
            "empty": 1,
        }
        answered = events(session, "drill.item_answered")
        assert answered[-1]["response_time_ms"] == 300_000  # capped (D-106)
        attempt = session.scalar(select(ProductionAttempt).where(ProductionAttempt.id == drill_id))
        assert attempt is not None and len((attempt.ai_feedback or {})["answers"]) == 5


def test_drills_are_listed_by_category_prefix(fake_env: FakeAiEnv) -> None:
    first = _drill(fake_env, count=5)
    fake_env.clock.advance(60)
    second = _tense_drill(fake_env)
    page = fake_env.client.get("/api/drills").json()
    assert [d["id"] for d in page["items"]] == [second["id"], first["id"]]
    prepositions = fake_env.client.get("/api/drills", params={"category": "grammar.preposition"})
    assert [d["id"] for d in prepositions.json()["items"]] == [first["id"]]
    assert fake_env.client.get("/api/drills", params={"category": "lexis"}).json()["total"] == 0
    missing = fake_env.client.get("/api/drills/999")
    assert (missing.status_code, code(missing)) == (404, "drill_not_found")


def test_a_drill_cannot_be_corrected(fake_env: FakeAiEnv) -> None:
    drill = _drill(fake_env, count=5)
    response = fake_env.client.post(f"/api/productions/{drill['id']}/correct")
    assert (response.status_code, code(response)) == (422, "not_correctable")
