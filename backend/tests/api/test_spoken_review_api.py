"""`spoken_answer` checked by transcription and the AI (M6.a2a): `POST /api/speech/review-answer`
then `POST /api/reviews` with `production_attempt_id`. Scripted fake provider, no network."""

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderRequest,
    ProviderResponse,
    TranscriptionRequest,
)
from app.db.models import Card, LexicalItem, ProductionAttempt, ReviewLog
from app.domain import exercises as ex
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import (
    DAY_2_START,
    SPOKEN,
    add_all_templates,
    code,
    discover,
    quick_add,
    sheet_for,
    start_session,
    table_counts,
    write_sheet,
)
from tests.library_support import events
from tests.speaking_support import error
from tests.speech_support import heard, wav_bytes

WAV = wav_bytes(1.0)
STT = (Capability.TEXT, Capability.TRANSCRIPTION)
ANSWER = "Um, our design cannot rule out selection, I think."
CHECK = {"ref": 0, "used": True, "used_correctly": True, "comment": ""}


def answer_output(text: str = ANSWER, **changes: Any) -> dict[str, Any]:
    """A valid `answer` mode output for a one-unit answer."""
    return {
        "sentences": [{"index": 1, "corrected": text, "status": "correct"}],
        "corrected_text": text,
        "natural_text": text,
        "errors": [],
        "naturalness_notes": [],
        "targets": [CHECK],
        "structure": None,
        "overall_comment": "Clear answer.",
    } | changes


class SpokenReview:
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

    def speak(self, *script: Success | Failure) -> FakeProvider:
        provider = FakeProvider("fake", script, capabilities=STT)
        self.env.use(provider)
        return provider

    def answer(self, data: bytes = WAV, *, content_type: str = "audio/wav", **changes: Any) -> Any:
        params = {
            "card_id": self.card_id,
            "session_id": self.session_id,
            "exercise_template_id": self.templates[ex.SPOKEN_ANSWER],
            "duration_s": 6.0,
            "response_time_ms": 9000,
        } | changes
        return self.env.client.post(
            "/api/speech/review-answer",
            params={k: v for k, v in params.items() if v is not None},
            content=data,
            headers={"Content-Type": content_type},
        )

    def record(self, **changes: Any) -> Any:
        body = {
            "card_id": self.card_id,
            "session_id": self.session_id,
            "exercise_type": ex.SPOKEN_ANSWER,
            "exercise_template_id": self.templates[ex.SPOKEN_ANSWER],
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


def audio_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data" / "audio"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- review-answer -------------------------------------------------------------------------------


def test_a_good_answer_is_transcribed_corrected_and_proposed_good(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    provider = review.speak(heard(ANSWER, duration_s=6.4), Success(content=answer_output()))
    response = review.answer()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcription"] == {"status": "ok", "text": ANSWER, "reason": None}
    assert (body["status"], body["reason"], body["proposed_rating"]) == ("ok", None, 3)
    assert (body["errors"], body["warnings"]) == ([], [])
    assert body["feedback"]["format"] == "speaking-1"
    assert body["solution"] == {"example_answer": SPOKEN["example_answer"]}
    assert body["sheet_summary"]["term"] == "rule out"
    # Neither the question nor the example answer goes to the recogniser (D-172).
    [transcription] = provider.transcriptions
    assert SPOKEN["question"] not in repr(transcription)
    assert SPOKEN["example_answer"] not in repr(transcription)
    # The AI got the question as the task, the term as the target, `answer` mode.
    [request] = provider.requests
    assert "Mode: answer" in request.user and SPOKEN["question"] in request.user
    assert '"term": "rule out"' in request.user
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, body["production_attempt_id"])
        assert attempt is not None
        assert (attempt.kind, attempt.prompt_text, attempt.study_session_id) == (
            "speaking",
            SPOKEN["question"],
            review.session_id,
        )
        assert attempt.audio_seconds == 6.4
        [recorded] = events(session, "production.recorded")[-1:]
        assert recorded["origin"] == "review"


def test_the_errors_of_a_spoken_answer_have_the_source_review(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    text = "Our design cannot rule out the selection."
    out = answer_output(text, errors=[error(1, "the selection", "selection", "grammar")])
    out["sentences"][0]["status"] = "corrected"
    review.speak(heard(text), Success(content=out))
    body = review.answer().json()
    assert [e["source"] for e in body["errors"]] == ["review"]
    assert body["errors"][0]["review_log_id"] is None
    assert body["errors"][0]["production_attempt_id"] == body["production_attempt_id"]
    assert body["proposed_rating"] == 3  # the error does not concern the target


def test_again_when_an_error_concerns_the_term(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    out = answer_output(
        errors=[error(1, "rule out selection", "rule selection out", "lexis", target_ref=0)]
    )
    out["sentences"][0]["status"] = "corrected"
    review.speak(heard(ANSWER), Success(content=out))
    assert review.answer().json()["proposed_rating"] == 1


def test_a_term_not_heard_gives_a_warning_and_no_rating(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    text = "Our design cannot exclude selection."
    review.speak(heard(text), Success(content=answer_output(text)))
    body = review.answer().json()
    assert (body["status"], body["proposed_rating"], body["warnings"]) == (
        "ok",
        None,
        ["term_not_heard"],
    )
    assert body["feedback"]["targets"][0]["used"] is False


def test_a_failed_transcription_keeps_the_recording_and_proposes_nothing(
    fake_env: FakeAiEnv, tmp_path: Path
) -> None:
    review = SpokenReview(fake_env)
    review.speak(Failure(ErrorKind.NETWORK))
    body = review.answer().json()
    assert body["transcription"] == {"status": "unavailable", "text": None, "reason": "network"}
    assert (body["status"], body["reason"]) == ("unavailable", "network")
    assert (body["proposed_rating"], body["feedback"], body["errors"]) == (None, None, [])
    assert body["solution"] == {"example_answer": SPOKEN["example_answer"]}
    assert len(audio_files(tmp_path)) == 1
    # The user rates it themself; the recording is linked to the review.
    recorded = review.record(production_attempt_id=body["production_attempt_id"], final_rating=2)
    assert recorded.status_code == 200, recorded.text
    log = review.log()
    assert (log.auto_rating, log.final_rating) == (None, 2)
    with Session(fake_env.engine) as session:
        attempt = session.get_one(ProductionAttempt, body["production_attempt_id"])
        assert log.audio_path == attempt.audio_path and log.audio_path


def test_silence_is_unavailable_with_its_reason(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    provider = review.speak(heard("", segments=()))
    body = review.answer().json()
    assert body["transcription"]["status"] == "silence"
    assert (body["status"], body["reason"], body["proposed_rating"]) == (
        "unavailable",
        "silence",
        None,
    )
    assert provider.requests == []  # nothing to correct


def test_a_failed_correction_returns_the_transcription(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Failure(ErrorKind.NETWORK))
    body = review.answer().json()
    assert body["transcription"]["text"] == ANSWER
    assert (body["status"], body["reason"], body["proposed_rating"]) == (
        "unavailable",
        "network",
        None,
    )
    # Corrected later by the usual route: still `answer` mode and the source `review`.
    out = answer_output(errors=[error(1, "rule out", "exclude", "lexis")])
    out["sentences"][0]["status"] = "corrected"
    provider = review.speak(Success(content=out))
    later = fake_env.client.post(f"/api/productions/{body['production_attempt_id']}/correct")
    assert [e["source"] for e in later.json()["errors"]] == ["review"]
    assert "Mode: answer" in provider.requests[0].user


def test_refusals_come_before_any_write_and_any_ai_call(
    fake_env: FakeAiEnv, tmp_path: Path
) -> None:
    review = SpokenReview(fake_env)
    provider = review.speak(heard(ANSWER), Success(content=answer_output()))
    before = table_counts(fake_env.engine)

    def refused(response: Any) -> tuple[int, str]:
        return response.status_code, code(response)

    wrong_type = review.answer(exercise_template_id=review.templates[ex.SENTENCE_PRODUCTION])
    assert refused(wrong_type) == (422, "exercise_mismatch")
    assert refused(review.answer(card_id=999)) == (404, "card_not_found")
    assert refused(review.answer(session_id=999)) == (404, "session_not_found")
    assert refused(review.answer(duration_s=0.5)) == (422, "audio_too_short")
    assert refused(review.answer(duration_s=91.0)) == (422, "audio_too_long")
    assert refused(review.answer(b"")) == (422, "audio_empty")
    assert refused(review.answer(content_type="audio/flac")) == (415, "unsupported_audio")
    assert review.answer(response_time_ms=-1).status_code == 422
    with Session(fake_env.engine) as session:
        receptive = session.scalars(
            select(Card).where(Card.lexical_item_id == review.item_id, Card.id != review.card_id)
        ).one()
    assert refused(review.answer(card_id=receptive.id)) == (422, "exercise_mismatch")
    # Not due: the card rated Easy waits several days.
    assert review.record(final_rating=4).status_code == 200
    assert refused(review.answer()) == (409, "not_due")
    # A term that is no longer reviewed.
    with Session(fake_env.engine) as session:
        session.get_one(LexicalItem, review.item_id).status = "archived"
        session.commit()
    fake_env.clock.advance(100 * 86_400)
    assert refused(review.answer()) == (409, "review_not_allowed")
    # A closed session.
    with Session(fake_env.engine) as session:
        session.get_one(LexicalItem, review.item_id).status = "learning"
        session.commit()
    ended = fake_env.client.post(f"/api/session/{review.session_id}/end")
    assert ended.status_code == 200
    assert refused(review.answer()) == (409, "session_closed")

    assert provider.calls == 0 and audio_files(tmp_path) == []
    after = table_counts(fake_env.engine)
    for table in ("production_attempt", "production_target", "ai_call_log", "error_event"):
        assert after[table] == before[table] == 0, table
    with Session(fake_env.engine) as session:
        assert events(session, "production.recorded") == []


def test_no_write_transaction_is_open_during_either_call(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    path = fake_env.db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    def probe() -> None:
        with sqlite3.connect(path, timeout=0.5) as other:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()

    class Probing(FakeProvider):
        def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
            probe()
            probes.append("transcribe")
            return super().transcribe(request)

        def generate_json(self, request: ProviderRequest) -> ProviderResponse:
            probe()
            probes.append("correct")
            return super().generate_json(request)

    fake_env.use(
        Probing("fake", [heard(ANSWER), Success(content=answer_output())], capabilities=STT)
    )
    assert review.answer().json()["status"] == "ok"
    assert probes == ["transcribe", "correct"]


# --- POST /api/reviews with the spoken answer ----------------------------------------------------


def test_the_review_takes_the_proposed_rating_from_the_server(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    attempt_id = review.answer().json()["production_attempt_id"]
    recorded = review.record(production_attempt_id=attempt_id, final_rating=4)
    assert recorded.status_code == 200, recorded.text
    log = review.log()
    assert (log.auto_rating, log.final_rating, log.production_attempt_id) == (3, 4, attempt_id)
    assert log.audio_path is not None and log.exercise_type == ex.SPOKEN_ANSWER


def test_the_client_cannot_send_the_proposed_rating(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    attempt_id = review.answer().json()["production_attempt_id"]
    lying = review.record(production_attempt_id=attempt_id, auto_rating=1)
    assert lying.status_code == 422
    assert review.record(production_attempt_id=attempt_id).status_code == 200
    assert review.log().auto_rating == 3  # computed again from the stored correction


def test_production_mismatches_are_refused(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    other = SpokenReview(fake_env, "shed light on")
    fake_env.clock.advance(86_400)  # both cards are due on day 3, in one session
    review.session_id = other.session_id = start_session(fake_env.client)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    other_attempt = other.answer().json()["production_attempt_id"]

    def mismatch(**changes: Any) -> None:
        response = review.record(**changes)
        assert (response.status_code, code(response)) == (409, "production_mismatch"), changes

    mismatch(production_attempt_id=999)
    mismatch(production_attempt_id=other_attempt)  # another term's answer
    # A free speech is not the answer of a review, even for the same term.
    free = fake_env.client.post(
        "/api/speech/speaking",
        params={"duration_s": 6.0, "target_item_ids": [review.item_id]},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    mismatch(production_attempt_id=free.json()["production_id"])
    # A written sentence checked for this card is not a spoken answer.
    review.speak(Success(content=output_sentence()))
    sentence = fake_env.client.post(
        "/api/reviews/check-production",
        json={
            "card_id": review.card_id,
            "session_id": review.session_id,
            "exercise_template_id": review.templates[ex.SENTENCE_PRODUCTION],
            "answer": "We can rule out chance.",
            "response_time_ms": 1000,
        },
    ).json()["production_attempt_id"]
    mismatch(production_attempt_id=sentence)
    with Session(fake_env.engine) as session:
        assert session.scalars(select(ReviewLog)).all() == []


def test_a_spoken_answer_is_not_a_sentence_production(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    attempt_id = review.answer().json()["production_attempt_id"]
    refused = review.record(
        production_attempt_id=attempt_id,
        exercise_type=ex.SENTENCE_PRODUCTION,
        exercise_template_id=review.templates[ex.SENTENCE_PRODUCTION],
        answer="We can rule out chance.",
    )
    assert (refused.status_code, code(refused)) == (409, "production_mismatch")
    gap = review.record(
        production_attempt_id=attempt_id,
        exercise_type=ex.GAP_FILL,
        exercise_template_id=review.templates[ex.GAP_FILL],
    )
    assert (gap.status_code, code(gap)) == (422, "exercise_mismatch")


def test_an_answer_of_another_session_is_refused(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    attempt_id = review.answer().json()["production_attempt_id"]
    ended = fake_env.client.post(f"/api/session/{review.session_id}/end")
    assert ended.status_code == 200
    new_session = start_session(fake_env.client)
    refused = review.record(production_attempt_id=attempt_id, session_id=new_session)
    assert (refused.status_code, code(refused)) == (409, "production_mismatch")


def test_a_spoken_answer_cannot_be_used_twice(fake_env: FakeAiEnv) -> None:
    review = SpokenReview(fake_env)
    review.speak(heard(ANSWER), Success(content=answer_output()))
    attempt_id = review.answer().json()["production_attempt_id"]
    assert review.record(production_attempt_id=attempt_id).status_code == 200
    fake_env.clock.advance(100 * 86_400)
    again = review.record(production_attempt_id=attempt_id, expected_reps=1)
    assert (again.status_code, code(again)) == (409, "production_mismatch")


def test_the_route_is_described_in_openapi(fake_env: FakeAiEnv) -> None:
    schema = fake_env.client.get("/openapi.json").json()
    route = schema["paths"]["/api/speech/review-answer"]["post"]
    assert "audio/wav" in route["requestBody"]["content"]
    assert {p["name"] for p in route["parameters"]} == {
        "card_id",
        "session_id",
        "exercise_template_id",
        "duration_s",
        "response_time_ms",
    }
    assert "/api/reviews/review-answer" not in json.dumps(schema)


def output_sentence() -> dict[str, Any]:
    text = "We can rule out chance."
    return {
        "sentences": [{"index": 1, "corrected": text, "status": "correct"}],
        "corrected_text": text,
        "natural_text": text,
        "errors": [],
        "naturalness_notes": [],
        "targets": [CHECK],
        "overall_comment": "Good.",
    }
