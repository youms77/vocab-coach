"""M4.a acceptance scenario, through the API with an injected clock (NowDep, D-097).

Import a term, type its sheet by hand, start the session, discover the term; it is not due the
same day, then comes back in `next` at the start of the next study day; a typo is graded `typo`
with Hard proposed, and the user records Good instead.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, ReviewLog
from app.domain import exercises as ex
from tests.api.conftest import ApiEnv
from tests.api.session_support import DAY_2_START, SENTENCE, TERM, code, sheet_for

IMPORT = f"""---
deck: Causal inference reading
---
- {TERM} | {SENTENCE}
"""


def test_import_discover_then_review_the_next_study_day(env: ApiEnv) -> None:
    client = env.client

    # Import (intake straight to the queue) and type the sheet by hand (degraded mode).
    preview = client.post("/api/import/preview", json={"text": IMPORT}).json()
    rows = [{"term": r["term"], "sentence": r["sentence"]} for r in preview["rows"]]
    imported = client.post(
        "/api/import/commit",
        json={"header": preview["header"], "rows": rows, "intake": "queued"},
    ).json()
    item_id = imported["item_ids"][0]
    put = client.put(f"/api/items/{item_id}/sheet", json={"content": sheet_for()})
    assert put.status_code == 200

    # Day 1: the plan proposes the term; the session starts and offers its discovery.
    today = client.get("/api/session/today").json()
    assert today["open_session"] is None
    new_items = [b for b in today["plan"]["blocks"] if b["kind"] == "new_items"][0]
    assert [e["lexical_item_id"] for e in new_items["entries"]] == [item_id]
    started = client.post("/api/session/start")
    assert started.status_code == 201
    session_id = started.json()["id"]
    step = client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "new_item"
    assert step["new_item"]["item_id"] == item_id

    # Discovery: sentence first, then the immediate exercises graded by term, then complete.
    first = client.post(f"/api/discovery/{item_id}/start", json={"session_id": session_id}).json()
    assert first["sentence"] == {"text": SENTENCE, "source": "origin"}
    exercises = client.get(f"/api/discovery/{item_id}/exercises").json()
    assert [e["exercise_type"] for e in exercises] == [ex.TYPED_RECALL]
    recall = exercises[0]
    graded = client.post(
        "/api/reviews/grade",
        json={
            "item_id": item_id,
            "exercise_type": ex.TYPED_RECALL,
            "exercise_template_id": recall["exercise_template_id"],
            "answer": "rule out",
            "response_time_ms": 4000,
        },
    ).json()
    assert graded["outcome"] == "exact"
    done = client.post(
        f"/api/discovery/{item_id}/complete",
        json={
            "session_id": session_id,
            "duration_ms": 140_000,
            "guess": "exclure ?",
            "exercise_results": [{"exercise_type": ex.TYPED_RECALL, "outcome": "exact"}],
            "personal_sentence": "My data cannot rule out a seasonal effect.",
        },
    ).json()
    assert done["status"] == "learning"
    assert {c["due"] for c in done["cards"]} == {"2026-10-17T03:00:00Z"}

    # Not due the same day: nothing left, and a review is refused.
    step = client.get(f"/api/session/{session_id}/next").json()
    assert step["type"] == "done"
    assert step["progress"]["new_done"] == 1
    productive = next(c for c in done["cards"] if c["direction"] == "productive")
    refused = client.post(
        "/api/reviews",
        json={
            "card_id": productive["card_id"],
            "session_id": session_id,
            "exercise_type": ex.TYPED_RECALL,
            "exercise_template_id": recall["exercise_template_id"],
            "answer": "rule out",
            "response_time_ms": 3000,
            "final_rating": 3,
            "expected_reps": 0,
        },
    )
    assert refused.status_code == 409
    assert code(refused) == "not_due"

    # Day 2, at the start of the study day: a new session closes yesterday's.
    env.clock.current = DAY_2_START
    started = client.post("/api/session/start")
    assert started.status_code == 201
    day_2 = started.json()["id"]
    assert day_2 != session_id
    assert client.post(f"/api/session/{session_id}/end").json()["detail"]["code"] == (
        "session_closed"
    )

    # The receptive card first: no receptive template, so a self-assessment.
    step = client.get(f"/api/session/{day_2}/next").json()
    assert step["type"] == "review"
    review = step["review"]
    assert review["direction"] == "receptive"
    assert review["exercise_type"] == ex.SELF_ASSESSMENT
    assert review["prompt"] == {"term": TERM, "sentence": SENTENCE}
    revealed = client.post(
        "/api/reviews/reveal",
        json={"card_id": review["card_id"], "exercise_type": ex.SELF_ASSESSMENT},
    ).json()
    assert revealed["solution"]["translation_fr"] == ["exclure", "écarter"]
    recorded = client.post(
        "/api/reviews",
        json={
            "card_id": review["card_id"],
            "session_id": day_2,
            "exercise_type": ex.SELF_ASSESSMENT,
            "response_time_ms": 6000,
            "final_rating": 3,
            "expected_reps": 0,
        },
    )
    assert recorded.status_code == 200, recorded.text

    # Then the productive card: typed recall, answered with a typo.
    step = client.get(f"/api/session/{day_2}/next").json()
    review = step["review"]
    assert review["direction"] == "productive"
    assert review["exercise_type"] == ex.TYPED_RECALL
    assert review["term"] is None
    assert review["prompt"]["cue_fr"] == "exclure"
    attempt = {
        "card_id": review["card_id"],
        "exercise_type": ex.TYPED_RECALL,
        "exercise_template_id": review["exercise_template_id"],
        "answer": "rul out",
        "response_time_ms": 7000,
    }
    graded = client.post("/api/reviews/grade", json=attempt).json()
    assert graded["outcome"] == "typo"
    assert graded["proposed_rating"] == 2
    assert graded["expected"] == "rule out"
    assert graded["diff"] is not None
    recorded = client.post(
        "/api/reviews",
        json={**attempt, "session_id": day_2, "final_rating": 3, "expected_reps": 0},
    )
    assert recorded.status_code == 200, recorded.text

    with Session(env.engine) as session:
        log = session.get_one(ReviewLog, recorded.json()["review_log_id"])
        assert (log.auto_rating, log.final_rating) == (2, 3)
        assert log.answer_text == "rul out"
        assert log.study_session_id == day_2
        card = session.scalar(select(Card).where(Card.id == review["card_id"]))
        assert card is not None and card.reps == 1
