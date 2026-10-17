"""`sentence_production` checked by the AI in a review (M5.a1): `POST /api/reviews/check-production`
then `POST /api/reviews` with `production_attempt_id`. Scripted fake provider, no network."""

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Success
from app.db.models import Card, ErrorEvent, ProductionAttempt, ReviewLog
from app.domain import exercises as ex
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import (
    DAY_2_START,
    add_all_templates,
    code,
    discover,
    quick_add,
    sheet_for,
    start_session,
    table_counts,
    write_sheet,
)
from tests.correction_support import error, output_for
from tests.library_support import events

GOOD_TEXT = "We can rule out chance in this design."
CHECK = {"ref": 0, "used": True, "used_correctly": True, "comment": ""}


class Review:
    """A discovered term whose productive card is due on day 2, in an open session."""

    def __init__(self, env: FakeAiEnv, term: str = "rule out") -> None:
        self.env = env
        self.item_id = quick_add(env.client, term, f"We cannot {term} chance here.")
        write_sheet(env.client, self.item_id, sheet_for(term))
        self.templates = add_all_templates(env.engine, self.item_id)
        discover(env.client, self.item_id, start_session(env.client))
        env.clock.current = DAY_2_START + timedelta(hours=1)
        self.session_id = start_session(env.client)
        with Session(env.engine) as session:
            cards = session.scalars(select(Card).where(Card.lexical_item_id == self.item_id))
            self.card_id = next(c.id for c in cards if str(c.direction) == "productive")

    def next_session(self) -> int:
        """End the open session and start another one (the card stays due)."""
        ended = self.env.client.post(f"/api/session/{self.session_id}/end")
        assert ended.status_code == 200, ended.text
        return start_session(self.env.client)

    def check(self, answer: str = GOOD_TEXT, **changes: Any) -> Any:
        body = {
            "card_id": self.card_id,
            "session_id": self.session_id,
            "exercise_template_id": self.templates[ex.SENTENCE_PRODUCTION],
            "answer": answer,
            "response_time_ms": 9000,
            **changes,
        }
        return self.env.client.post("/api/reviews/check-production", json=body)

    def record(self, **changes: Any) -> Any:
        body = {
            "card_id": self.card_id,
            "session_id": self.session_id,
            "exercise_type": ex.SENTENCE_PRODUCTION,
            "exercise_template_id": self.templates[ex.SENTENCE_PRODUCTION],
            "answer": GOOD_TEXT,
            "response_time_ms": 9000,
            "final_rating": 3,
            "expected_reps": 0,
            **changes,
        }
        return self.env.client.post("/api/reviews", json=body)

    def log(self) -> ReviewLog:
        with Session(self.env.engine) as session:
            log = session.scalars(select(ReviewLog).order_by(ReviewLog.id.desc())).first()
            assert log is not None
            return log


def _good(text: str = GOOD_TEXT, **changes: Any) -> Success:
    return Success(content=output_for(text, targets=[CHECK], **changes))


# --- check-production ----------------------------------------------------------------------------


def test_a_good_sentence_is_checked_and_proposed_good(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    response = review.check()
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["reason"], body["proposed_rating"]) == ("ok", None, 3)
    assert body["errors"] == [] and body["feedback"]["format"] == "correction-1"
    # The solution comes with the answer, after the attempt (D-103).
    assert "We can rule out chance." in json.dumps(body["solution"])
    assert body["sheet_summary"] is not None
    attempt_id = body["production_attempt_id"]
    # What the AI received: the situation as the prompt, the term as the target, mode sentence.
    request = fake_env.provider.requests[0].user
    assert "Mode: sentence" in request and "Say that chance is not a possible cause." in request
    assert '"term": "rule out"' in request
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, attempt_id)
        assert attempt is not None
        assert (attempt.text, attempt.study_session_id) == (GOOD_TEXT, review.session_id)
        assert attempt.prompt_text == "Say that chance is not a possible cause."
        [recorded] = events(session, "production.recorded")[-1:]
        assert recorded["origin"] == "review"


def test_the_errors_of_a_checked_sentence_have_the_source_review(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    text = "We can rule out the chance of error."
    wrong = error(1, "the chance of error", "chance of error", "grammar")
    out = output_for(text, errors=[wrong], targets=[CHECK])
    out["sentences"][0]["status"] = "corrected"
    fake_env.script(Success(content=out))
    body = review.check(text).json()
    assert [e["source"] for e in body["errors"]] == ["review"]
    # An error of an attempt is not an error of a review (single origin): the link is the other way.
    assert body["errors"][0]["review_log_id"] is None
    assert body["errors"][0]["production_attempt_id"] == body["production_attempt_id"]
    assert body["proposed_rating"] == 3  # the error does not concern the target


def test_check_production_refuses_what_is_not_a_sentence_production(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    wrong_type = review.check(exercise_template_id=review.templates[ex.GAP_FILL])
    assert (wrong_type.status_code, code(wrong_type)) == (422, "exercise_mismatch")
    assert review.check("").status_code == 422
    assert review.check(session_id=999).status_code == 404
    assert review.check(card_id=999).status_code == 404
    assert review.check(response_time_ms=-1).status_code == 422
    assert fake_env.provider.calls == 0
    with Session(fake_env.engine) as session:
        assert session.scalars(select(ProductionAttempt)).all() == []


def test_unavailable_keeps_the_sentence_and_proposes_nothing(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.provider.configured = False
    response = review.check()
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["reason"]) == ("unavailable", "no_provider_configured")
    assert (body["proposed_rating"], body["feedback"], body["errors"]) == (None, None, [])
    assert "We can rule out chance." in json.dumps(body["solution"])
    # The user rates it themself: the review works exactly as before.
    recorded = review.record(production_attempt_id=body["production_attempt_id"], final_rating=2)
    assert recorded.status_code == 200, recorded.text
    assert review.log().auto_rating is None
    # The kept sentence can still be corrected later, and its errors are review errors.
    fake_env.provider.configured = True
    out = output_for(GOOD_TEXT, errors=[error(1, "rule out", "exclude", "lexis")], targets=[CHECK])
    out["sentences"][0]["status"] = "corrected"
    fake_env.script(Success(content=out))
    later = fake_env.client.post(f"/api/productions/{body['production_attempt_id']}/correct")
    assert [e["source"] for e in later.json()["errors"]] == ["review"]


# --- Recording with the production ---------------------------------------------------------------


def test_good_when_the_term_is_used_correctly(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    recorded = review.record(production_attempt_id=attempt_id)
    assert recorded.status_code == 200, recorded.text
    log = review.log()
    assert (log.auto_rating, log.final_rating, log.production_attempt_id) == (3, 3, attempt_id)
    assert log.answer_text == GOOD_TEXT


def test_the_user_may_override_the_proposed_rating(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    assert review.record(production_attempt_id=attempt_id, final_rating=4).status_code == 200
    log = review.log()
    assert (log.auto_rating, log.final_rating) == (3, 4)  # Easy is never proposed, only chosen


def test_again_when_the_ai_finds_the_term_misused(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    check = {"ref": 0, "used": True, "used_correctly": False, "comment": "Wrong meaning."}
    fake_env.script(Success(content=output_for(GOOD_TEXT, targets=[check])))
    body = review.check().json()
    assert body["proposed_rating"] == 1
    assert review.record(production_attempt_id=body["production_attempt_id"]).status_code == 200
    assert review.log().auto_rating == 1


def test_again_when_an_error_concerns_the_term(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    out = output_for(
        GOOD_TEXT,
        errors=[error(1, "rule out chance", "rule chance out", "lexis", target_ref=0)],
        targets=[CHECK],  # the AI says "correct" but also reports an error on the term
    )
    out["sentences"][0]["status"] = "corrected"
    fake_env.script(Success(content=out))
    body = review.check().json()
    assert body["proposed_rating"] == 1
    assert body["errors"][0]["term"]["term"] == "rule out"


def test_again_when_the_term_is_absent(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    text = "We can exclude chance in this design."
    # The AI claims the term was used; the deterministic check says it was not.
    fake_env.script(Success(content=output_for(text, targets=[CHECK])))
    body = review.check(text).json()
    assert body["proposed_rating"] == 1
    assert body["feedback"]["targets"][0]["used"] is False
    assert body["feedback"]["targets"][0]["disagreement"] is True


def test_no_proposal_when_the_correction_is_incomplete(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    broken = output_for(GOOD_TEXT, targets=[{**CHECK, "ref": 7}])  # unknown target
    fake_env.script(Success(content=broken))
    body = review.check().json()
    assert (body["status"], body["proposed_rating"]) == ("incomplete", None)
    assert review.record(production_attempt_id=body["production_attempt_id"]).status_code == 200
    assert review.log().auto_rating is None


def test_the_client_still_cannot_send_the_proposed_rating(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    response = review.record(auto_rating=3)
    assert response.status_code == 422


def test_without_a_production_the_review_is_unchanged(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    assert review.record().status_code == 200
    log = review.log()
    assert (log.auto_rating, log.production_attempt_id) == (None, None)


# --- production_mismatch -------------------------------------------------------------------------


def test_a_production_cannot_be_used_twice(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    assert review.record(production_attempt_id=attempt_id).status_code == 200
    fake_env.clock.advance(100 * 86_400)  # the card is due again, in the same session
    again = review.record(production_attempt_id=attempt_id, expected_reps=1)
    assert (again.status_code, code(again)) == (409, "production_mismatch")
    with Session(fake_env.engine) as session:
        # A discovery writes no review log: only the first review exists, the refused one left none.
        assert len(session.scalars(select(ReviewLog)).all()) == 1


def test_a_production_of_another_term_is_refused(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    other = Review(fake_env, "shed light on")
    fake_env.script(_good())
    other_attempt = other.check().json()["production_attempt_id"]
    refused = review.record(production_attempt_id=other_attempt)
    assert (refused.status_code, code(refused)) == (409, "production_mismatch")


def test_a_production_of_another_session_is_refused(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    new_session = review.next_session()
    refused = review.record(production_attempt_id=attempt_id, session_id=new_session)
    assert (refused.status_code, code(refused)) == (409, "production_mismatch")


def test_an_unknown_production_is_refused(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    refused = review.record(production_attempt_id=999)
    assert (refused.status_code, code(refused)) == (409, "production_mismatch")
    with Session(fake_env.engine) as session:
        assert (
            session.scalars(select(ReviewLog).where(ReviewLog.card_id == review.card_id)).all()
            == []
        )


def test_a_production_only_goes_with_a_sentence_production(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    refused = review.record(
        production_attempt_id=attempt_id,
        exercise_type=ex.GAP_FILL,
        exercise_template_id=review.templates[ex.GAP_FILL],
    )
    assert (refused.status_code, code(refused)) == (422, "exercise_mismatch")


def test_a_refused_review_writes_nothing(fake_env: FakeAiEnv) -> None:
    review = Review(fake_env)
    fake_env.script(_good())
    attempt_id = review.check().json()["production_attempt_id"]
    before = table_counts(fake_env.engine)
    review.record(production_attempt_id=attempt_id, session_id=review.next_session())
    after = table_counts(fake_env.engine)
    assert after["review_log"] == before["review_log"]
    assert after["error_event"] == before["error_event"] == 0
    with Session(fake_env.engine) as session:
        assert session.scalars(select(ErrorEvent)).all() == []
