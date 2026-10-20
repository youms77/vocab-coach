"""Free speaking through the API (M6.a2a): `POST /api/speech/speaking`, its correction by
`POST /api/productions/{id}/correct` and today's speaking topics. Scripted fake provider."""

import json
import re
import sqlite3
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
from app.db.models import ErrorEvent, EventLog, ProductionAttempt, ProductionTarget
from app.domain.enums import ErrorSource
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code, quick_add, start_session
from tests.library_support import count, events
from tests.speaking_support import EXPECTED_CODES, PROMPT, SPEECH, clean_output, speaking_output
from tests.speech_support import heard, wav_bytes

WAV = wav_bytes(1.0)
STT = (Capability.TEXT, Capability.TRANSCRIPTION)


def speak(env: FakeAiEnv, *script: Success | Failure) -> FakeProvider:
    provider = FakeProvider("fake", script, capabilities=STT)
    env.use(provider)
    return provider


def post(env: FakeAiEnv, **params: Any) -> Any:
    query = {"duration_s": 40.0, "prompt_text": PROMPT} | params
    query = {key: value for key, value in query.items() if value is not None}
    return env.client.post(
        "/api/speech/speaking", params=query, content=WAV, headers={"Content-Type": "audio/wav"}
    )


def correct(env: FakeAiEnv, production_id: int) -> Any:
    return env.client.post(f"/api/productions/{production_id}/correct")


def audio_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data" / "audio"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- Recording -----------------------------------------------------------------------------------


def test_a_speech_is_recorded_and_transcribed_without_the_topic(fake_env: FakeAiEnv) -> None:
    provider = speak(fake_env, heard(SPEECH, duration_s=41.5))
    response = post(fake_env)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transcription"] == {"status": "ok", "text": SPEECH, "reason": None}
    assert (body["comparison"], body["audio_seconds"]) == (None, 41.5)
    # The recogniser receives the audio under a generated name, never the topic (D-172).
    [request] = provider.transcriptions
    assert re.fullmatch(r"[0-9a-f]{32}\.wav", request.audio.filename)
    assert PROMPT not in repr(request)
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, body["production_id"])
        assert attempt is not None
        assert (attempt.kind, attempt.modality, attempt.prompt_text) == (
            "speaking",
            "oral",
            PROMPT,
        )
        # The words heard are the learner's own words: the denominator of the error rates.
        assert attempt.word_count == 55 and attempt.text == SPEECH
        [recorded] = events(session, "production.recorded")
        assert (recorded["origin"], recorded["kind"], recorded["word_count"]) == (
            "speaking",
            "speaking",
            0,
        )
    detail = fake_env.client.get(f"/api/productions/{body['production_id']}").json()
    assert (detail["transcription_status"], detail["corrected"]) == ("ok", False)


def test_the_target_terms_are_kept_unchecked_until_the_correction(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard(SPEECH))
    first = quick_add(fake_env.client, "present")
    second = quick_add(fake_env.client, "supervisor")
    response = post(fake_env, target_item_ids=[first, second, first])
    assert response.status_code == 201, response.text
    with Session(fake_env.engine) as session:
        targets = session.scalars(select(ProductionTarget).order_by(ProductionTarget.id)).all()
        assert [(t.lexical_item_id, t.used) for t in targets] == [(first, None), (second, None)]


def test_recording_refusals_store_nothing(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    provider = speak(fake_env, heard(SPEECH))
    too_long = post(fake_env, prompt_text="p" * 501)
    assert (too_long.status_code, code(too_long)) == (422, "invalid_production")
    many = post(fake_env, target_item_ids=list(range(1, 17)))
    assert (many.status_code, code(many)) == (422, "invalid_production")
    unknown = post(fake_env, target_item_ids=[999])
    assert (unknown.status_code, code(unknown)) == (404, "item_not_found")
    short = post(fake_env, duration_s=4.9)
    assert (short.status_code, code(short)) == (422, "audio_too_short")
    assert short.json()["detail"]["min_s"] == 5.0
    long = post(fake_env, duration_s=180.5)
    assert (long.status_code, code(long)) == (422, "audio_too_long")
    assert long.json()["detail"]["max_s"] == 180.0
    missing = post(fake_env, study_session_id=999)
    assert (missing.status_code, code(missing)) == (404, "session_not_found")
    assert provider.calls == 0 and audio_files(tmp_path) == []
    with Session(fake_env.engine) as session:
        assert count(session, ProductionAttempt) == 0


def test_the_longest_accepted_take(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard(SPEECH))
    assert post(fake_env, duration_s=180.0).status_code == 201


# --- Correction ----------------------------------------------------------------------------------


def test_a_speech_is_corrected_with_the_speaking_source(fake_env: FakeAiEnv) -> None:
    provider = speak(fake_env, heard(SPEECH), Success(content=speaking_output()))
    study_id = start_session(fake_env.client)
    production_id = post(fake_env, study_session_id=study_id).json()["production_id"]

    response = correct(fake_env, production_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["reason"]) == ("ok", None)
    assert [e["category"]["code"] for e in body["errors"]] == EXPECTED_CODES
    assert {e["source"] for e in body["errors"]} == {"speaking"}
    assert body["errors"][0]["original_text"] == (
        "Um, so, I'm a master's student in statistics and I live in campus."
    )
    feedback = body["attempt"]["feedback"]
    assert feedback["format"] == "speaking-1"
    assert feedback["prompt_version"] == "speaking_correction.v1"
    assert feedback["output"]["structure"]["connectors_used"] == ["so", "and"]
    text = body["attempt"]["text"]
    assert [text[s["start"] : s["end"]] for s in feedback["spans"]] == [
        "in campus",
        "study here since two years",
        "I never presented",
    ]
    # What the AI received: monologue mode, the units and the topic framed as data, the taxonomy
    # without spelling and pronunciation.
    request = provider.requests[0]
    assert "Mode: monologue" in request.user
    assert '<<<USER_DATA\n{"index": 1, "text": "Um, so,' in request.user
    assert f"<<<USER_DATA\n{PROMPT}\nUSER_DATA>>>" in request.user
    taxonomy = request.user.rsplit("(code: description):", 1)[1]
    codes = re.findall(r"^([a-z_.]+):", taxonomy, re.MULTILINE)
    assert "grammar.preposition.by_for_since" in codes
    assert not [c for c in codes if c == "spelling" or c.startswith(("spelling.", "pronunc"))]
    with Session(fake_env.engine) as session:
        [corrected] = events(session, "production.corrected")
        assert corrected["kind"] == "speaking" and corrected["word_count"] == 55
        errors = session.scalars(select(ErrorEvent)).all()
        assert {e.source for e in errors} == {ErrorSource.SPEAKING}
        rows = session.scalars(select(EventLog).where(EventLog.event_type == "error.recorded"))
        assert {row.study_session_id for row in rows} == {study_id}


def test_a_clean_speech_gives_no_error(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard(SPEECH), Success(content=clean_output(SPEECH)))
    production_id = post(fake_env).json()["production_id"]
    body = correct(fake_env, production_id).json()
    assert (body["status"], body["errors"]) == ("ok", [])


def test_the_targets_are_checked_on_the_transcription(fake_env: FakeAiEnv) -> None:
    item_id = quick_add(fake_env.client, "supervisor")
    absent = quick_add(fake_env.client, "deadline")
    checks = [
        {"ref": 0, "used": True, "used_correctly": True, "comment": ""},
        {"ref": 1, "used": True, "used_correctly": True, "comment": ""},
    ]
    speak(fake_env, heard(SPEECH), Success(content=speaking_output(targets=checks)))
    production_id = post(fake_env, target_item_ids=[item_id, absent]).json()["production_id"]
    feedback = correct(fake_env, production_id).json()["attempt"]["feedback"]
    assert [(t["used"], t["used_correctly"]) for t in feedback["targets"]] == [
        (True, True),
        (False, False),
    ]
    assert feedback["targets"][1]["disagreement"] is True


def test_an_ai_failure_writes_nothing_and_can_be_retried(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard(SPEECH), Failure(ErrorKind.NETWORK))
    production_id = post(fake_env).json()["production_id"]
    failed = correct(fake_env, production_id).json()
    assert (failed["status"], failed["reason"]) == ("unavailable", "network")
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, production_id)
        assert attempt is not None and attempt.ai_feedback is None and attempt.ai_call_id is None
        assert count(session, ErrorEvent) == 0 and events(session, "production.corrected") == []
    speak(fake_env, Success(content=speaking_output()))
    again = correct(fake_env, production_id).json()
    assert again["status"] == "ok" and len(again["errors"]) == 3


def test_a_broken_answer_is_repaired_once_then_incomplete(fake_env: FakeAiEnv) -> None:
    broken = speaking_output(structure=None)  # required in monologue mode
    provider = speak(fake_env, heard(SPEECH), Success(content=broken))
    production_id = post(fake_env).json()["production_id"]
    body = correct(fake_env, production_id).json()
    assert body["status"] == "incomplete"
    assert len(provider.requests) == 2 and "structure: required" in provider.requests[1].user
    with Session(fake_env.engine) as session:
        assert count(session, ErrorEvent) == 0


def test_refusals_before_any_ai_call(fake_env: FakeAiEnv) -> None:
    # Not transcribed (the transcription failed): transcribe it first.
    provider = speak(fake_env, Failure(ErrorKind.NETWORK))
    pending = post(fake_env).json()["production_id"]
    refused = correct(fake_env, pending)
    assert (refused.status_code, code(refused)) == (409, "not_transcribed")
    # Silence: nothing to correct.
    speak(fake_env, heard("", segments=()))
    silent = post(fake_env).json()["production_id"]
    nothing = correct(fake_env, silent)
    assert (nothing.status_code, code(nothing)) == (422, "nothing_to_correct")
    # Too long to be corrected at once.
    speak(fake_env, heard("Yes. " * 801))
    talkative = post(fake_env).json()["production_id"]
    too_long = correct(fake_env, talkative)
    assert (too_long.status_code, code(too_long)) == (422, "text_too_long")
    # A shadowing is compared, never corrected.
    provider = speak(fake_env, heard("We account for it."))
    shadowing = fake_env.client.post(
        "/api/speech/shadowing",
        params={"target_text": "We account for it.", "duration_s": 2.0},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    ).json()["production_id"]
    not_correctable = correct(fake_env, shadowing)
    assert (not_correctable.status_code, code(not_correctable)) == (422, "not_correctable")
    assert provider.requests == []


def test_a_second_correction_is_refused(fake_env: FakeAiEnv) -> None:
    provider = speak(fake_env, heard(SPEECH), Success(content=speaking_output()))
    production_id = post(fake_env).json()["production_id"]
    assert correct(fake_env, production_id).json()["status"] == "ok"
    again = correct(fake_env, production_id)
    assert (again.status_code, code(again)) == (409, "already_corrected")
    assert len(provider.requests) == 1


def test_a_transcript_body_is_refused_for_a_speech(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard(SPEECH))
    production_id = post(fake_env).json()["production_id"]
    body = {"transcript": {"text": "You: hello", "user": {"label": "You"}}}
    refused = fake_env.client.post(f"/api/productions/{production_id}/correct", json=body)
    assert (refused.status_code, code(refused)) == (422, "invalid_production")


def test_no_write_transaction_is_open_during_the_calls(fake_env: FakeAiEnv) -> None:
    path = fake_env.db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    def probe() -> None:
        with sqlite3.connect(path, timeout=0.5) as other:
            other.execute("BEGIN IMMEDIATE")  # 'database is locked' if a writer is open
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
        Probing("fake", [heard(SPEECH), Success(content=speaking_output())], capabilities=STT)
    )
    production_id = post(fake_env).json()["production_id"]
    assert correct(fake_env, production_id).json()["status"] == "ok"
    assert probes == ["transcribe", "correct"]


def test_a_failed_transcription_then_its_correction(fake_env: FakeAiEnv) -> None:
    speak(fake_env, Failure(ErrorKind.NETWORK))
    body = post(fake_env).json()
    assert body["transcription"]["status"] == "unavailable"
    production_id = body["production_id"]
    speak(fake_env, heard(SPEECH), Success(content=speaking_output()))
    retried = fake_env.client.post(f"/api/productions/{production_id}/transcribe").json()
    assert retried["transcription"]["status"] == "ok"
    assert correct(fake_env, production_id).json()["status"] == "ok"
    listed = fake_env.client.get("/api/productions", params={"kind": "speaking"}).json()
    assert [p["id"] for p in listed["items"]] == [production_id]
    assert listed["items"][0]["feedback"]["format"] == "speaking-1"


# --- Topics --------------------------------------------------------------------------------------


def test_speaking_topics_of_the_day(fake_env: FakeAiEnv) -> None:
    first = fake_env.client.get("/api/speaking/topics").json()
    assert len(first) == 3 and first == fake_env.client.get("/api/speaking/topics").json()
    assert set(first[0]) == {"id", "en", "fr", "tags"}
    presenting = fake_env.client.get(
        "/api/speaking/topics", params={"tag": "presenting", "count": 10}
    ).json()
    assert presenting and all("presenting" in t["tags"] for t in presenting)
    assert fake_env.client.get("/api/speaking/topics", params={"tag": "x"}).status_code == 422
    assert fake_env.client.get("/api/speaking/topics", params={"count": 11}).status_code == 422
    fake_env.clock.advance(86_400)
    assert fake_env.client.get("/api/speaking/topics").json() != first


def test_a_topic_spoken_this_week_is_not_proposed_but_a_written_one_is(
    fake_env: FakeAiEnv,
) -> None:
    [topic] = fake_env.client.get("/api/speaking/topics", params={"count": 1}).json()
    written = fake_env.client.post(
        "/api/productions", json={"text": "Fine.", "prompt": topic["en"]}
    )
    assert written.status_code == 201
    assert fake_env.client.get("/api/speaking/topics", params={"count": 1}).json() == [topic]
    speak(fake_env, heard(SPEECH))
    assert post(fake_env, prompt_text=topic["fr"]).status_code == 201
    [other] = fake_env.client.get("/api/speaking/topics", params={"count": 1}).json()
    assert other["id"] != topic["id"]


def test_the_upload_is_described_in_openapi(fake_env: FakeAiEnv) -> None:
    schema = fake_env.client.get("/openapi.json").json()
    body = schema["paths"]["/api/speech/speaking"]["post"]["requestBody"]
    assert "audio/webm" in body["content"]
    params = {p["name"] for p in schema["paths"]["/api/speech/speaking"]["post"]["parameters"]}
    assert params == {"duration_s", "prompt_text", "target_item_ids", "study_session_id"}
    assert json.dumps(schema).count("/api/speaking/topics") == 1
