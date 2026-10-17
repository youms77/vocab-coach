"""Discovery endpoints: start, immediate exercises, complete."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, Enrichment, EventLog, ProductionAttempt, ProductionTarget
from app.domain import exercises as ex
from app.domain.events import parse_event
from app.domain.usage_sheet import skeleton_sheet
from tests.api.conftest import ApiEnv
from tests.api.session_support import (
    GAP_FILL,
    SENTENCE,
    add_template,
    code,
    quick_add,
    sheet_for,
    start_session,
    write_sheet,
)


def _start(env: ApiEnv, item_id: int, session_id: int, **body: object):
    return env.client.post(
        f"/api/discovery/{item_id}/start", json={"session_id": session_id, **body}
    )


def _complete(env: ApiEnv, item_id: int, session_id: int, **body: object):
    return env.client.post(
        f"/api/discovery/{item_id}/complete", json={"session_id": session_id, **body}
    )


def test_start_returns_the_sentence_never_the_sheet(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    response = _start(env, item_id, session_id)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "item_id": item_id,
        "term": "rule out",
        "item_type": body["item_type"],
        "status": "discovering",
        "resumed": False,
        "sentence": {"text": SENTENCE, "source": "origin"},
    }
    # A second start resumes; nothing changes.
    again = _start(env, item_id, session_id).json()
    assert again["resumed"] is True


def test_start_without_original_sentence_uses_the_first_example(env: ApiEnv) -> None:
    item_id = quick_add(env.client, sentence=None)
    write_sheet(env.client, item_id)
    body = _start(env, item_id, start_session(env.client)).json()
    assert body["sentence"] == {
        "text": "The authors rule out measurement error.",
        "source": "example",
    }


def test_sheet_required(env: ApiEnv) -> None:
    session_id = start_session(env.client)
    no_sheet = quick_add(env.client)
    response = _start(env, no_sheet, session_id)
    assert (response.status_code, code(response)) == (409, "sheet_required")
    # A sheet without a definition nor a translation cannot be saved; a skeleton (AI failure)
    # is not usable.
    skeleton = quick_add(env.client, "shed light on", None)
    with Session(env.engine) as session:
        session.add(
            Enrichment(
                lexical_item_id=skeleton,
                content=skeleton_sheet(),
                schema_version=1,
                status="needs_completion",
                is_current=True,
            )
        )
        session.commit()
    response = _start(env, skeleton, session_id)
    assert (response.status_code, code(response)) == (409, "sheet_required")
    with Session(env.engine) as session:
        payloads = session.scalars(
            select(EventLog.payload).where(EventLog.event_type == "item.status_changed")
        ).all()
    assert [p for p in payloads if p["to_status"] == "discovering"] == []


def test_exercises_are_prompts_only(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    gap_id = add_template(env.engine, item_id, ex.GAP_FILL, GAP_FILL)
    queued = env.client.get(f"/api/discovery/{item_id}/exercises")
    assert (queued.status_code, code(queued)) == (409, "review_not_allowed")
    _start(env, item_id, start_session(env.client))
    exercises = env.client.get(f"/api/discovery/{item_id}/exercises").json()
    assert [(e["exercise_type"], e["prompt"]) for e in exercises] == [
        (
            ex.TYPED_RECALL,
            {"cue_fr": "exclure", "cue_definition": sheet_for()["definition_simple"]},
        ),
        (ex.GAP_FILL, {"sentence": GAP_FILL["sentence"]}),
    ]
    graded = env.client.post(
        "/api/reviews/grade",
        json={
            "item_id": item_id,
            "exercise_type": ex.GAP_FILL,
            "exercise_template_id": gap_id,
            "answer": "rule out",
            "response_time_ms": 3000,
        },
    ).json()
    assert graded["outcome"] == "exact"
    assert graded["solution"]["sentence"] == "We cannot rule out a placebo effect."
    # Only typed recall and gap-fill are discovery exercises.
    other = env.client.post(
        "/api/reviews/grade",
        json={"item_id": item_id, "exercise_type": ex.SELF_ASSESSMENT, "response_time_ms": 1},
    )
    assert (other.status_code, code(other)) == (422, "exercise_mismatch")


def test_complete_without_initial_ratings(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    _start(env, item_id, session_id)
    response = _complete(
        env,
        item_id,
        session_id,
        duration_ms=150_000,
        guess="exclure quelque chose",
        exercise_results=[
            {"exercise_type": "typed_recall", "outcome": "typo"},
            {"exercise_type": "gap_fill", "outcome": "exact"},
        ],
        personal_sentence="We cannot exclude a placebo effect.",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "learning"
    assert body["warnings"] == ["term_missing"]
    assert [c["direction"] for c in body["cards"]] == ["receptive", "productive"]
    assert {c["due"] for c in body["cards"]} == {"2026-10-17T03:00:00Z"}

    with Session(env.engine) as session:
        cards = session.scalars(select(Card).where(Card.lexical_item_id == item_id)).all()
        assert {(c.srs_state, c.reps) for c in cards} == {("new", 0)}
        row = session.scalars(
            select(EventLog).where(EventLog.event_type == "discovery.completed")
        ).one()
        assert row.payload_version == 2
        assert row.study_session_id == session_id
        parse_event(row.event_type, row.payload)
        assert row.payload["guess"] == "exclure quelque chose"
        assert row.payload["exercise_results"][0] == {
            "exercise_type": "typed_recall",
            "outcome": "typo",
        }
        attempt = session.get_one(ProductionAttempt, body["production_attempt_id"])
        assert (attempt.kind, attempt.modality) == ("writing", "written")
        assert attempt.prompt_text == "discovery sentence"
        assert attempt.word_count == 6
        assert attempt.ai_feedback is None
        assert attempt.study_session_id == session_id
        target = session.scalars(select(ProductionTarget)).one()
        assert (target.lexical_item_id, target.used) == (item_id, False)
        recorded = session.scalars(
            select(EventLog).where(EventLog.event_type == "production.recorded")
        ).one()
        assert recorded.payload["word_count"] == 6

    again = _complete(env, item_id, session_id)
    assert (again.status_code, code(again)) == (409, "already_discovered")
    restart = _start(env, item_id, session_id)
    assert (restart.status_code, code(restart)) == (409, "already_discovered")


def test_version_1_payload_still_reads() -> None:
    event = parse_event("discovery.completed", {"lexical_item_id": 3, "duration_ms": 1000})
    assert event.model_dump() == {
        "lexical_item_id": 3,
        "duration_ms": 1000,
        "guess": None,
        "exercise_results": [],
    }


def test_complete_requires_a_started_discovery(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    response = _complete(env, item_id, start_session(env.client))
    assert (response.status_code, code(response)) == (409, "invalid_transition")


def test_paused_deck_and_wrong_status(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    write_sheet(env.client, item_id)
    session_id = start_session(env.client)
    deck_id = env.client.get(f"/api/items/{item_id}").json()["decks"][0]["id"]
    env.client.post(f"/api/decks/{deck_id}/status", json={"to": "paused"})
    paused = _start(env, item_id, session_id, deck_id=deck_id)
    assert (paused.status_code, code(paused)) == (409, "discovery_not_allowed")
    triage = env.client.post(f"/api/items/{item_id}/status", json={"to": "triage"})
    assert triage.status_code == 200
    response = _start(env, item_id, session_id)
    assert (response.status_code, code(response)) == (409, "invalid_transition")
    missing = _start(env, 999, session_id)
    assert (missing.status_code, code(missing)) == (404, "item_not_found")
    closed = env.client.post(f"/api/session/{session_id}/end")
    assert closed.status_code == 200
    after_end = _start(env, item_id, session_id)
    assert (after_end.status_code, code(after_end)) == (409, "session_closed")
