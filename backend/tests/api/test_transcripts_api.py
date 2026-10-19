"""`/api/transcripts` and the transcript analysis through `/api/productions/{id}/correct`
(scripted fake provider, no network)."""

import sqlite3
import unicodedata
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind, ProviderRequest, ProviderResponse
from app.db.models import AICallLog, ErrorEvent, EventLog, ProductionAttempt
from app.domain.transcript_import import CONTEXT_MAX_CHARS, split_units
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code
from tests.library_support import count, events
from tests.transcript_support import (
    BROKEN,
    CHATGPT_QUOTE,
    EXAMPLE,
    EXAMPLE_TURNS,
    UNLABELLED_FILE,
    broken,
    error,
    example_output,
    output_for,
)

USER = {"label": "You"}


def _record(env: FakeAiEnv, text: str = EXAMPLE, **extra: Any) -> int:
    body = {"text": text, "user": USER} | extra
    response = env.client.post("/api/transcripts", json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _analyse(env: FakeAiEnv, production_id: int, text: str | None = EXAMPLE, user=None) -> Any:
    body = {"transcript": {"text": text, "user": user or USER}} if text is not None else None
    return env.client.post(f"/api/productions/{production_id}/correct", json=body)


def _rows(env: FakeAiEnv) -> dict[str, int]:
    with Session(env.engine) as session:
        return {
            "productions": count(session, ProductionAttempt),
            "errors": count(session, ErrorEvent),
            "events": count(session, EventLog),
        }


# --- Preview -------------------------------------------------------------------------------------


def test_the_preview_shows_turns_labels_and_the_suggested_user(fake_env: FakeAiEnv) -> None:
    before = _rows(fake_env)
    response = fake_env.client.post("/api/transcripts/preview", json={"text": EXAMPLE})
    body = response.json()
    assert response.status_code == 200
    assert body["suggested_user_label"] == "You"
    assert body["designation"] == {"label": "You"}
    assert [(t["speaker_label"], t["is_user"]) for t in body["turns"]][:2] == [
        ("ChatGPT", False),
        ("You", True),
    ]
    labels = {label["label"]: label for label in body["labels"]}
    assert labels["You"]["turns"] == 4 and labels["ChatGPT"]["turns"] == 4
    assert labels["You"]["known"] == "user" and labels["ChatGPT"]["known"] == "other"
    you_words = sum(len(turn.split()) for turn in EXAMPLE_TURNS)
    assert labels["You"]["words"] == you_words
    assert body["user"] == {
        "turns": 4,
        "words": you_words,
        "chars": sum(len(turn) for turn in EXAMPLE_TURNS),
    }
    assert body["problems"] == []
    assert body["turns"][1]["text"] == EXAMPLE_TURNS[0]  # timestamp and label removed
    assert body["turns"][1]["line_start"] == 2
    assert _rows(fake_env) == before  # nothing written
    assert fake_env.provider.calls == 0


def test_the_preview_of_an_unlabelled_transcript_with_a_mode(fake_env: FakeAiEnv) -> None:
    text = UNLABELLED_FILE.read_text(encoding="utf-8")
    plain = fake_env.client.post("/api/transcripts/preview", json={"text": text}).json()
    assert [p["code"] for p in plain["problems"]] == ["no_speaker_labels"]
    assert plain["user"] is None and plain["suggested_user_label"] is None
    mine = fake_env.client.post(
        "/api/transcripts/preview",
        json={"text": text, "user": {"mode": "alternating_user_second"}},
    ).json()
    assert mine["user"]["turns"] == 3
    assert [t["is_user"] for t in mine["turns"]] == [False, True] * 3


def test_the_preview_reports_the_problems_of_a_choice(fake_env: FakeAiEnv) -> None:
    response = fake_env.client.post(
        "/api/transcripts/preview", json={"text": "x", "user": {"label": "Nobody"}}
    )
    assert response.status_code == 200
    assert [p["code"] for p in response.json()["problems"]] == [
        "no_speaker_labels",
        "single_speaker",
        "unknown_label",
        "no_user_turns",
    ]


# --- Recording -----------------------------------------------------------------------------------


def test_only_the_users_turns_are_stored(fake_env: FakeAiEnv) -> None:
    response = fake_env.client.post(
        "/api/transcripts",
        json={"text": EXAMPLE, "user": USER, "title": "Call with my tutor"},
    )
    body = response.json()
    assert response.status_code == 201, body
    assert (body["kind"], body["modality"], body["corrected"]) == (
        "transcript_analysis",
        "oral",
        False,
    )
    assert body["text"] == "\n\n".join(EXAMPLE_TURNS)
    assert "ChatGPT" not in body["text"] and "on campus" not in body["text"]
    assert body["word_count"] == sum(len(turn.split()) for turn in EXAMPLE_TURNS)
    assert body["prompt_text"] == "Call with my tutor"
    assert fake_env.provider.calls == 0
    with Session(fake_env.engine) as session:
        [recorded] = events(session, "production.recorded")
        assert recorded == {
            "production_attempt_id": body["id"],
            "kind": "transcript_analysis",
            "modality": "oral",
            "word_count": body["word_count"],
            "audio_seconds": None,
            "origin": "transcript",
            "turns_total": 8,
            "turns_user": 4,
            "words_user": body["word_count"],
            "occurred_on": None,
        }
        row = session.scalars(select(EventLog).order_by(EventLog.id.desc())).first()
        assert row is not None and row.payload_version == 5  # v5 since M6.a2 (speaking)


def test_recording_refusals(fake_env: FakeAiEnv) -> None:
    post = fake_env.client.post
    unknown = post("/api/transcripts", json={"text": EXAMPLE, "user": {"label": "Jordan"}})
    assert (unknown.status_code, code(unknown)) == (422, "invalid_transcript")
    assert unknown.json()["detail"]["codes"] == ["unknown_label", "no_user_turns"]
    empty = post("/api/transcripts", json={"text": "  \n ", "user": USER})
    assert (empty.status_code, code(empty)) == (422, "invalid_transcript")
    long_turns = "\n".join(f"You: {'word ' * 200}\nChatGPT: ok" for _ in range(7))
    too_long = post("/api/transcripts", json={"text": long_turns, "user": USER})
    assert (too_long.status_code, code(too_long)) == (422, "text_too_long")
    pasted = post("/api/transcripts", json={"text": "You: " + "a" * 60_001, "user": USER})
    assert (pasted.status_code, code(pasted)) == (422, "text_too_long")
    future = post(
        "/api/transcripts", json={"text": EXAMPLE, "user": USER, "occurred_on": "2099-01-01"}
    )
    assert (future.status_code, code(future)) == (422, "invalid_transcript")
    assert future.json()["detail"]["codes"] == ["future_date"]
    title = post("/api/transcripts", json={"text": EXAMPLE, "user": USER, "title": "t" * 201})
    assert (title.status_code, code(title)) == (422, "invalid_request")
    no_user = post("/api/transcripts", json={"text": EXAMPLE})
    assert no_user.status_code == 422
    session = post("/api/transcripts", json={"text": EXAMPLE, "user": USER, "study_session_id": 9})
    assert (session.status_code, code(session)) == (404, "session_not_found")
    assert _rows(fake_env)["productions"] == 0


def test_transcripts_are_listed_by_kind(fake_env: FakeAiEnv) -> None:
    production_id = _record(fake_env)
    fake_env.client.post("/api/productions", json={"kind": "writing", "text": "Fine."})
    page = fake_env.client.get("/api/productions", params={"kind": "transcript_analysis"}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == production_id


# --- Analysis ------------------------------------------------------------------------------------


def test_the_example_gives_three_errors_with_the_transcript_source(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=example_output()))
    production_id = _record(fake_env, occurred_on="2026-10-10")
    response = _analyse(fake_env, production_id)
    body = response.json()
    assert response.status_code == 200, body
    assert (body["status"], body["reason"]) == ("ok", None)
    assert [e["category"]["code"] for e in body["errors"]] == [
        "grammar.preposition.fixed_expression",
        "grammar.preposition.by_for_since",
        "grammar.tense.past_simple_vs_present_perfect",
    ]
    assert {e["source"] for e in body["errors"]} == {"transcript"}
    assert {e["production_attempt_id"] for e in body["errors"]} == {production_id}
    first = body["errors"][0]
    assert first["original_text"] == EXAMPLE_TURNS[0]
    assert first["explanation_fr"] == "Dites « on campus » ici."
    # The day of the conversation, at the start of its study day (Africa/Douala, 04:00 by default).
    with Session(fake_env.engine) as session:
        stored = session.scalars(select(ErrorEvent).order_by(ErrorEvent.id)).all()
        assert {e.occurred_at for e in stored} == {datetime(2026, 10, 10, 3, 0, tzinfo=UTC)}
    feedback = body["attempt"]["feedback"]
    assert feedback["format"] == "transcript-1"
    assert feedback["prompt_version"] == "transcript_analysis.v1"
    assert set(feedback["output"]) == {
        "sentences",
        "corrected_text",
        "natural_text",
        "errors",
        "naturalness_notes",
        "targets",
        "overall_comment",
    }
    assert [s["index"] for s in feedback["output"]["sentences"]] == [1, 2, 3, 4]
    assert feedback["output"]["errors"][0]["sentence_index"] == 1
    assert feedback["output"]["natural_text"] is None
    assert feedback["context_sent"] is True
    text = body["attempt"]["text"]
    assert [text[s["start"] : s["end"]] for s in feedback["spans"]] == [
        "in campus",
        "since two years",
        "Yesterday I have finished",
    ]
    assert feedback["error_event_ids"] == [e["id"] for e in body["errors"]]
    assert body["attempt"]["corrected"] is True
    with Session(fake_env.engine) as session:
        [corrected] = events(session, "production.corrected")
        assert corrected["error_count"] == 3 and corrected["sentence_count"] == 4
        call = session.scalars(select(AICallLog).order_by(AICallLog.id.desc())).first()
        assert call is not None and call.task == "transcript_analysis"
        assert body["attempt"]["ai_call_id"] == call.id
    listed = fake_env.client.get("/api/errors", params={"source": "transcript"}).json()
    assert listed["total"] == 3


def test_without_a_date_the_errors_happen_at_the_analysis(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=example_output()))
    production_id = _record(fake_env)
    _analyse(fake_env, production_id)
    with Session(fake_env.engine) as session:
        dates = {e.occurred_at for e in session.scalars(select(ErrorEvent))}
    assert dates == {fake_env.clock.now()}


def test_the_other_speaker_is_sent_only_as_a_cut_context(fake_env: FakeAiEnv) -> None:
    long_question = "Tell me about your day. " * 30 + "Where do you live?"
    text = f"ChatGPT: {long_question}\nYou: I live in campus.\nChatGPT: We say on campus.\n"
    fake_env.script(Success(content=output_for([(1, "I live in campus.")])))
    production_id = _record(fake_env, text)
    assert _analyse(fake_env, production_id, text).json()["status"] == "ok"
    [request] = fake_env.provider.requests
    contexts_part, units_part = request.user.split("The learner's units", 1)
    assert "We say on campus" not in request.user  # the turn after is never sent
    assert "Tell me about your day." not in units_part
    context_line = next(
        line for line in contexts_part.splitlines() if line.startswith('{"before_unit"')
    )
    assert "Where do you live?" in context_line
    context_text = context_line.split('"text": "', 1)[1].rsplit('"', 1)[0]
    assert len(context_text) <= CONTEXT_MAX_CHARS
    assert "context, never to be corrected" in request.user
    assert request.user.count("<<<USER_DATA") == 2  # units and contexts, each framed as data


def test_without_the_transcript_the_units_go_without_context(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=example_output()))
    production_id = _record(fake_env)
    body = _analyse(fake_env, production_id, text=None).json()
    assert body["status"] == "ok"
    [request] = fake_env.provider.requests
    assert "ChatGPT" not in request.user and CHATGPT_QUOTE not in request.user
    assert "Where do you live" not in request.user
    assert body["attempt"]["feedback"]["context_sent"] is False


def test_the_example_quote_of_chatgpt_reaches_the_provider_only_as_context(
    fake_env: FakeAiEnv,
) -> None:
    fake_env.script(Success(content=example_output()))
    _analyse(fake_env, _record(fake_env))
    [request] = fake_env.provider.requests
    units_part = request.user.split("The learner's units", 1)[1]
    assert CHATGPT_QUOTE not in units_part
    taxonomy = request.user.split("The taxonomy of errors", 1)[1].splitlines()
    assert not [line for line in taxonomy if line.startswith(("spelling", "pronunciation"))]
    assert "grammar.preposition.by_for_since:" in request.user


def test_a_transcript_that_does_not_match_is_refused(fake_env: FakeAiEnv) -> None:
    production_id = _record(fake_env)
    other = EXAMPLE.replace("small room", "big room")
    response = _analyse(fake_env, production_id, other)
    assert (response.status_code, code(response)) == (409, "transcript_mismatch")
    mode = _analyse(fake_env, production_id, EXAMPLE, {"mode": "all_mine"})
    assert (mode.status_code, code(mode)) == (409, "transcript_mismatch")
    assert fake_env.provider.calls == 0


def test_a_transcript_body_on_a_written_production_is_refused(fake_env: FakeAiEnv) -> None:
    created = fake_env.client.post("/api/productions", json={"kind": "writing", "text": "Fine."})
    response = _analyse(fake_env, created.json()["id"])
    assert (response.status_code, code(response)) == (422, "invalid_production")


@pytest.mark.parametrize("change", BROKEN)
def test_a_broken_answer_is_repaired_once_then_incomplete(fake_env: FakeAiEnv, change: str) -> None:
    fake_env.script(Success(content=broken(change)))
    production_id = _record(fake_env)
    response = _analyse(fake_env, production_id)
    assert response.status_code == 200
    assert response.json()["status"] == "incomplete"
    assert fake_env.provider.calls == 2
    assert "rejected" in fake_env.provider.requests[1].user
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, production_id)
        assert attempt is not None and attempt.ai_feedback is None
        assert count(session, ErrorEvent) == 0
        assert events(session, "production.corrected") == []


def test_a_broken_answer_is_repaired_when_the_second_one_is_valid(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=broken("wrong_from_the_context")), Success(example_output()))
    body = _analyse(fake_env, _record(fake_env)).json()
    assert body["status"] == "ok" and len(body["errors"]) == 3


# --- Chunks --------------------------------------------------------------------------------------


def _long_transcript(first_turn: str) -> tuple[str, list[str]]:
    """Seven user turns of about 480 characters: two chunks (5 + 2)."""
    filler = "We talked about the course and the exams of the semester. " * 8
    turns = [f"{first_turn} {filler}".strip()] + [
        f"Turn {n}. {filler}".strip() for n in range(2, 8)
    ]
    text = "\n".join(f"ChatGPT: Question {n}?\nYou: {turn}" for n, turn in enumerate(turns))
    return text, turns


def _chunk_outputs(turns: list[str], errors: dict[int, list[dict[str, Any]]]) -> list[Success]:
    units = split_units("\n\n".join(turns))
    first, second = units[:5], units[5:]
    outputs = []
    for chunk in (first, second):
        out = output_for(chunk, errors=[e for u in chunk for e in errors.get(u.index, [])])
        for unit in out["units"]:
            if unit["index"] in errors:
                unit["status"] = "corrected"
        outputs.append(Success(content=out))
    return outputs


def test_spans_are_right_over_two_chunks_with_both_unicode_forms(fake_env: FakeAiEnv) -> None:
    nfd = unicodedata.normalize("NFD", "Yaoundé")
    text, turns = _long_transcript(f"I live in Yaoundé since 2020, in {nfd} centre.")
    assert len(split_units("\n\n".join(turns))) == 7
    script = _chunk_outputs(
        turns,
        {
            1: [error(1, "live in Yaoundé since", "have lived in Yaoundé since", "grammar.tense")],
            6: [error(6, "Turn 6", "Turn six", "lexis.wrong_word")],
        },
    )
    # The AI writes "Yaoundé" composed, the text has it once composed, once decomposed.
    fake_env.script(*script)
    production_id = _record(fake_env, text)
    body = _analyse(fake_env, production_id, text).json()
    assert body["status"] == "ok", body
    assert fake_env.provider.calls == 2
    stored = body["attempt"]["text"]
    spans = body["attempt"]["feedback"]["spans"]
    assert [stored[s["start"] : s["end"]] for s in spans] == [
        "live in Yaoundé since",
        "Turn 6",
    ]
    assert [s["sentence_index"] for s in spans] == [1, 6]
    calls = body["attempt"]["feedback"]["calls"]
    assert [c["units"] for c in calls] == [[1, 5], [6, 7]]
    second = fake_env.provider.requests[1].user.split("The learner's units", 1)[1]
    assert '"index": 6' in second and '"index": 1,' not in second


def test_spans_find_a_decomposed_form_written_composed(fake_env: FakeAiEnv) -> None:
    nfd = unicodedata.normalize("NFD", "Yaoundé")
    text, turns = _long_transcript("Hello.")
    turns_text = "\n\n".join(turns)
    script = _chunk_outputs(turns, {})
    # Put a decomposed "Yaoundé" error in the second chunk.
    text = text.replace("Turn 7.", f"Turn 7 in {nfd} is fine.")
    turns[6] = turns[6].replace("Turn 7.", f"Turn 7 in {nfd} is fine.")
    turns_text = "\n\n".join(turns)
    units = split_units(turns_text)
    second = output_for(
        units[5:], errors=[error(7, "in Yaoundé is", "in Yaoundé was", "grammar.tense")]
    )
    second["units"][1]["status"] = "corrected"
    fake_env.script(script[0], Success(content=second))
    production_id = _record(fake_env, text)
    body = _analyse(fake_env, production_id, text).json()
    assert body["status"] == "ok", body
    span = body["attempt"]["feedback"]["spans"][0]
    assert body["attempt"]["text"][span["start"] : span["end"]] == f"in {nfd} is"


def test_one_failed_chunk_writes_nothing(fake_env: FakeAiEnv) -> None:
    text, turns = _long_transcript("First.")
    ok = _chunk_outputs(turns, {})
    fake_env.script(ok[0], Failure(ErrorKind.QUOTA_EXHAUSTED))
    production_id = _record(fake_env, text)
    before = _rows(fake_env)
    body = _analyse(fake_env, production_id, text).json()
    assert body["status"] == "unavailable" and body["errors"] == []
    assert _rows(fake_env) == before
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, production_id)
        assert attempt is not None and attempt.ai_feedback is None and attempt.ai_call_id is None
    # Both calls are in the journal, and the transcript can be analysed again (after the quota
    # cooldown of the provider, D-039).
    with Session(fake_env.engine) as session:
        assert count(session, AICallLog) == 2
    fake_env.clock.advance(3601)
    fake_env.script(*ok)
    assert _analyse(fake_env, production_id, text).json()["status"] == "ok"


def test_one_incomplete_chunk_writes_nothing(fake_env: FakeAiEnv) -> None:
    text, turns = _long_transcript("First.")
    ok = _chunk_outputs(turns, {})
    bad = Success(content={"units": []})
    fake_env.script(ok[0], bad)
    production_id = _record(fake_env, text)
    body = _analyse(fake_env, production_id, text).json()
    assert body["status"] == "incomplete"
    with Session(fake_env.engine) as session:
        assert count(session, ErrorEvent) == 0
        assert events(session, "production.corrected") == []


def test_no_write_transaction_is_open_during_the_ai_calls(fake_env: FakeAiEnv) -> None:
    text, turns = _long_transcript("First.")
    production_id = _record(fake_env, text)
    path = fake_env.db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    class Probing(FakeProvider):
        def generate_json(self, request: ProviderRequest) -> ProviderResponse:
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")  # 'database is locked' if a writer is open
                other.rollback()
            probes.append("free")
            return super().generate_json(request)

    fake_env.use(Probing("fake", _chunk_outputs(turns, {})))
    assert _analyse(fake_env, production_id, text).json()["status"] == "ok"
    assert probes == ["free", "free"]


def test_a_second_analysis_is_refused(fake_env: FakeAiEnv) -> None:
    fake_env.script(Success(content=example_output()))
    production_id = _record(fake_env)
    assert _analyse(fake_env, production_id).json()["status"] == "ok"
    again = _analyse(fake_env, production_id)
    assert (again.status_code, code(again)) == (409, "already_corrected")
