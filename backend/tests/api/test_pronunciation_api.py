"""Pronunciation assessment through the API (app/api/speech.py, app/api/productions.py)."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.pronunciation import PronunciationAssessmentOutput, WordScore
from app.ai.types import Capability, ErrorKind
from app.db.models import AICallLog, ErrorEvent, PronunciationResult
from tests.api.conftest import FakeAiEnv
from tests.audio_support import WEBM, wav
from tests.library_support import events
from tests.speech_support import HEARD, TARGET, heard

CLIP = wav(1.5)
CAPS = (Capability.TEXT, Capability.TRANSCRIPTION, Capability.PRONUNCIATION_ASSESSMENT)
OUTPUT = PronunciationAssessmentOutput(
    status="ok",
    accuracy=78,
    fluency=84,
    completeness=90,
    pronunciation=74.5,
    duration_s=1.5,
    words=[WordScore(word="fixed", accuracy=40, error_type="Mispronunciation")],
)


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.pronunciation.azure_configured", lambda: True)


def play(env: FakeAiEnv, *script: Success | Failure) -> FakeProvider:
    provider = FakeProvider("fake", script, capabilities=CAPS)
    env.use(provider)
    return provider


def turn_on(env: FakeAiEnv, value: str = "azure") -> None:
    assert env.client.patch("/api/settings", json={"pronunciation_assessment": value}).is_success


def shadow(env: FakeAiEnv, data: bytes = CLIP, content_type: str = "audio/wav") -> dict[str, Any]:
    response = env.client.post(
        "/api/speech/shadowing",
        params={"target_text": TARGET, "duration_s": 1.5},
        content=data,
        headers={"Content-Type": content_type},
    )
    assert response.status_code == 201, response.text
    return response.json()


def assess(env: FakeAiEnv, production_id: int):
    return env.client.post(f"/api/productions/{production_id}/pronunciation")


def test_assess_a_transcribed_shadowing(fake_env: FakeAiEnv) -> None:
    turn_on(fake_env)
    play(fake_env, heard(), Success(content="", assessment=OUTPUT))
    created = shadow(fake_env)
    assert created["assessable"] is True and created["assessable_reason"] is None
    assert created["pronunciation"] is None
    production_id = created["production_id"]

    response = assess(fake_env, production_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["production_id"], body["status"], body["reason"]) == (production_id, "ok", None)
    scores = body["scores"]
    assert scores["format"] == "azure-pa-1" and scores["overall"]["pronunciation"] == 74.5
    assert scores["words"][0] == {
        "word": "fixed",
        "accuracy": 40.0,
        "error_type": "Mispronunciation",
        "offset_ms": None,
        "duration_ms": None,
        "phonemes": [],
    }

    one = fake_env.client.get(f"/api/productions/{production_id}").json()
    assert one["pronunciation"] == scores
    assert (one["assessable"], one["assessable_reason"]) == (False, "already_assessed")
    assert one["comparison"]["unrecognized"][0]["word"] == "fixed"  # the transcription is kept
    listed = fake_env.client.get("/api/productions").json()["items"]
    assert listed[0]["pronunciation"] == scores
    again = assess(fake_env, production_id)
    assert (again.status_code, code(again)) == (409, "already_assessed")


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def test_assess_before_any_transcription(fake_env: FakeAiEnv) -> None:
    turn_on(fake_env)
    play(fake_env, Failure(ErrorKind.AUTH, status_code=401))  # the transcription fails first
    created = shadow(fake_env)
    assert created["transcription"]["status"] == "unavailable"
    production_id = created["production_id"]
    fake_env.gateway.reload()  # forget the "misconfigured" mark of the failed transcription
    play(fake_env, Success(content="", assessment=OUTPUT))
    assert assess(fake_env, production_id).json()["status"] == "ok"
    one = fake_env.client.get(f"/api/productions/{production_id}").json()
    assert one["transcription_status"] == "pending" and one["comparison"] is None
    assert one["pronunciation"]["status"] == "ok"
    play(fake_env, heard())
    done = fake_env.client.post(f"/api/productions/{production_id}/transcribe")
    assert done.status_code == 200
    assert done.json()["pronunciation"]["status"] == "ok"  # the scores survive
    assert done.json()["comparison"] is not None
    with Session(fake_env.engine) as session:
        assert session.scalar(select(func.count()).select_from(PronunciationResult)) == 1
        [row] = session.scalars(select(PronunciationResult))
        assert row.transcript == HEARD and row.scores is not None


def test_refusals_use_the_documented_codes(fake_env: FakeAiEnv) -> None:
    provider = play(fake_env, heard(), heard())
    created = shadow(fake_env)
    production_id = created["production_id"]
    assert created["assessable_reason"] == "disabled"
    off = assess(fake_env, production_id)
    assert (off.status_code, code(off)) == (409, "assessment_disabled")
    assert code(assess(fake_env, 99999)) == "production_not_found"
    turn_on(fake_env)
    webm = shadow(fake_env, WEBM, "audio/webm")
    assert webm["assessable_reason"] == "unsupported_format"
    bad = assess(fake_env, webm["production_id"])
    assert (bad.status_code, code(bad)) == (422, "unsupported_for_assessment")
    assert provider.calls == 2  # the two transcriptions only: no assessment was sent


def test_a_writing_is_not_assessable(fake_env: FakeAiEnv) -> None:
    turn_on(fake_env)
    created = fake_env.client.post("/api/productions", json={"text": "I fix the model."})
    assert created.status_code == 201
    body = created.json()
    assert (body["assessable"], body["assessable_reason"], body["pronunciation"]) == (
        False,
        "not_shadowing",
        None,
    )
    refused = assess(fake_env, body["id"])
    assert (refused.status_code, code(refused)) == (422, "not_assessable")


def test_an_ai_failure_is_a_200_and_can_be_retried(fake_env: FakeAiEnv) -> None:
    turn_on(fake_env)
    play(fake_env, heard(), Failure(ErrorKind.QUOTA_EXHAUSTED, status_code=429))
    production_id = shadow(fake_env)["production_id"]
    response = assess(fake_env, production_id)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["reason"], body["scores"]) == ("unavailable", "quota", None)
    with Session(fake_env.engine) as session:
        assert events(session, "pronunciation.assessed") == []
        assert session.scalar(select(func.count()).select_from(ErrorEvent)) == 0
        assert session.scalar(select(func.count()).select_from(AICallLog)) >= 2


def test_the_setting_off_hides_nothing_already_stored(fake_env: FakeAiEnv) -> None:
    turn_on(fake_env)
    play(fake_env, heard(), Success(content="", assessment=OUTPUT))
    production_id = shadow(fake_env)["production_id"]
    assess(fake_env, production_id)
    turn_on(fake_env, "off")
    one = fake_env.client.get(f"/api/productions/{production_id}").json()
    assert one["pronunciation"]["status"] == "ok" and one["assessable_reason"] == "disabled"


# --- Usage ---------------------------------------------------------------------------------------


def test_usage_counts_this_month_read_only(fake_env: FakeAiEnv) -> None:
    empty = fake_env.client.get("/api/speech/pronunciation/usage")
    assert empty.status_code == 200
    body = empty.json()
    assert (body["audio_seconds"], body["assessments"]) == (0.0, 0)
    assert (body["limit_seconds"], body["limit_checked_on"]) == (18000, "2026-10-24")
    assert body["month"] == fake_env.clock.now().strftime("%Y-%m")
    assert "not confirmed" in body["note"] and "estimate" in body["note"]

    turn_on(fake_env)
    play(fake_env, heard(), Success(content="", assessment=OUTPUT))
    assess(fake_env, shadow(fake_env)["production_id"])
    used = fake_env.client.get("/api/speech/pronunciation/usage").json()
    assert (used["audio_seconds"], used["assessments"]) == (3.4, 1)
    # The pooled connection was left writable after the read-only query.
    assert fake_env.client.patch("/api/settings", json={"new_items_per_day": 15}).is_success


def test_the_demo_keeps_the_endpoints_readable(fake_env: FakeAiEnv) -> None:
    assert fake_env.client.get("/api/speech/pronunciation/usage").is_success
    assert fake_env.client.get("/api/settings").json()["pronunciation_assessment"]["value"] == "off"
