"""Shadowing recordings through the API (app/api/speech.py) with a scripted fake provider."""

import asyncio
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind, ProviderResponse, TranscriptionRequest
from app.api.speech import read_upload
from app.db.models import ProductionAttempt, PronunciationResult, StudySession
from app.services.speech import AudioTooLarge
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code, quick_add
from tests.library_support import count, events
from tests.speech_support import HEARD, TARGET, heard, wav_bytes

WAV = wav_bytes(1.5)
STT = (Capability.TEXT, Capability.TRANSCRIPTION)
STORED = re.compile(r"\d{4}/\d{2}/[0-9a-f]{32}\.wav")


def speak(env: FakeAiEnv, *script: Success | Failure) -> FakeProvider:
    provider = FakeProvider("fake", script, capabilities=STT)
    env.use(provider)
    return provider


def post(
    env: FakeAiEnv,
    data: bytes | Iterator[bytes] = WAV,
    *,
    content_type: str = "audio/wav",
    headers: dict[str, str] | None = None,
    **params: Any,
) -> Any:
    query = {"target_text": TARGET, "duration_s": 1.5} | params
    query = {key: value for key, value in query.items() if value is not None}
    return env.client.post(
        "/api/speech/shadowing",
        params=query,
        content=data,
        headers={"Content-Type": content_type} | (headers or {}),
    )


def audio_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data" / "audio"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- Upload --------------------------------------------------------------------------------------


def test_a_raw_recording_is_stored_transcribed_and_compared(
    fake_env: FakeAiEnv, tmp_path: Path
) -> None:
    speak(fake_env, heard())
    response = post(fake_env)

    assert response.status_code == 201, response.text
    body = response.json()
    production_id = body["production_id"]
    assert body["audio_url"] == f"/api/productions/{production_id}/audio"
    assert body["audio_seconds"] == 3.4
    assert body["transcription"] == {"status": "ok", "text": HEARD, "reason": None}
    comparison = body["comparison"]
    assert comparison["version"] == "speech-compare-1"
    assert comparison["word_accuracy"] == 0.8889
    assert (comparison["target_word_count"], comparison["recognized_count"]) == (9, 8)
    assert comparison["unrecognized"] == [{"position": 4, "word": "fixed", "heard": "fix"}]
    assert comparison["steps"][4] == {
        "op": "substituted",
        "target_start": 4,
        "target_end": 5,
        "heard_start": 4,
        "heard_end": 5,
        "target": "fixed",
        "heard": "fix",
    }
    [stored] = audio_files(tmp_path)
    assert stored.read_bytes() == WAV
    with Session(fake_env.engine) as session:
        attempt = session.get(ProductionAttempt, production_id)
        assert attempt is not None and STORED.fullmatch(attempt.audio_path or "")
        assert (tmp_path / "data" / "audio" / attempt.audio_path).resolve() == stored.resolve()


def test_the_client_file_name_is_ignored(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    speak(fake_env, heard())
    response = post(
        fake_env, headers={"Content-Disposition": 'attachment; filename="../../evil.wav"'}
    )
    assert response.status_code == 201
    [stored] = audio_files(tmp_path)
    assert "evil" not in str(stored) and re.fullmatch(r"[0-9a-f]{32}\.wav", stored.name)


def test_media_type_parameters_are_accepted(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    speak(fake_env, heard())
    response = post(fake_env, b"\x1aE\xdf\xa3webm", content_type="audio/webm;codecs=opus")
    assert response.status_code == 201, response.text
    [stored] = audio_files(tmp_path)
    assert stored.suffix == ".webm"


def test_without_a_provider_the_recording_is_kept(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    response = post(fake_env)  # fake_env's default provider cannot transcribe

    assert response.status_code == 201
    body = response.json()
    assert body["transcription"] == {
        "status": "unavailable",
        "text": None,
        "reason": "no_provider_configured",
    }
    assert body["comparison"] is None and body["audio_seconds"] == 1.5
    assert len(audio_files(tmp_path)) == 1
    playback = fake_env.client.get(body["audio_url"])
    assert playback.status_code == 200 and playback.content == WAV


def test_a_silent_recording(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard("", segments=()))
    body = post(fake_env).json()
    assert body["transcription"] == {"status": "silence", "text": None, "reason": None}
    assert body["comparison"] is None


def test_a_provider_failure_is_a_result(fake_env: FakeAiEnv) -> None:
    speak(fake_env, Failure(ErrorKind.QUOTA_EXHAUSTED))
    response = post(fake_env)
    assert response.status_code == 201
    assert response.json()["transcription"]["reason"] == "quota"


# --- Refusals ------------------------------------------------------------------------------------


def test_too_large_by_content_length(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    response = post(fake_env, b"\x00" * (10 * 1024 * 1024 + 1))
    assert (response.status_code, code(response)) == (413, "audio_too_large")
    assert response.json()["detail"]["max_bytes"] == 10 * 1024 * 1024
    assert audio_files(tmp_path) == []


def test_too_large_while_streaming(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    def chunks() -> Iterator[bytes]:  # no Content-Length: chunked transfer
        for _ in range(11):
            yield b"\x00" * (1024 * 1024)

    response = post(fake_env, chunks())
    assert (response.status_code, code(response)) == (413, "audio_too_large")
    assert audio_files(tmp_path) == []


def test_content_length_is_checked_before_reading() -> None:
    async def receive() -> dict[str, Any]:
        raise AssertionError("the body must not be read")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/speech/shadowing",
        "headers": [(b"content-type", b"audio/wav"), (b"content-length", b"99999999")],
    }
    with pytest.raises(AudioTooLarge):
        asyncio.run(read_upload(Request(scope, receive)))


def test_a_streamed_recording_under_the_limit_is_accepted(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard())

    def chunks() -> Iterator[bytes]:
        yield WAV[:100]
        yield WAV[100:]

    response = post(fake_env, chunks())
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("content_type", ["audio/flac", "audio/aac", "audio/x-ms-wma"])
def test_an_audio_type_that_is_not_accepted(
    fake_env: FakeAiEnv, tmp_path: Path, content_type: str
) -> None:
    response = post(fake_env, content_type=content_type)
    assert (response.status_code, code(response)) == (415, "unsupported_audio")
    assert audio_files(tmp_path) == []


@pytest.mark.parametrize("content_type", ["text/plain", "multipart/form-data; boundary=x"])
def test_a_body_that_is_not_audio_is_refused_by_the_guard(
    fake_env: FakeAiEnv, content_type: str
) -> None:
    response = post(fake_env, content_type=content_type)
    assert (response.status_code, code(response)) == (415, "unsupported_media_type")


@pytest.mark.parametrize(
    ("changes", "status", "error"),
    [
        ({"target_text": None}, 422, "invalid_request"),
        ({"duration_s": None}, 422, "invalid_request"),
        ({"duration_s": "nan"}, 422, "invalid_request"),
        ({"duration_s": "inf"}, 422, "invalid_request"),
        ({"duration_s": "abc"}, 422, "invalid_request"),
        ({"origin": "review"}, 422, "invalid_request"),
        ({"target_text": ""}, 422, "invalid_target"),
        ({"target_text": "?!"}, 422, "invalid_target"),
        ({"target_text": "x" * 401}, 422, "invalid_target"),
        ({"duration_s": 0.2}, 422, "audio_too_short"),
        ({"duration_s": 31}, 422, "audio_too_long"),
        ({"item_id": 999}, 404, "item_not_found"),
        ({"study_session_id": 999}, 404, "session_not_found"),
    ],
)
def test_invalid_requests(
    fake_env: FakeAiEnv, tmp_path: Path, changes: dict[str, Any], status: int, error: str
) -> None:
    provider = speak(fake_env, heard())
    response = post(fake_env, **changes)
    assert (response.status_code, code(response)) == (status, error), response.text
    assert audio_files(tmp_path) == []
    assert provider.transcriptions == []
    with Session(fake_env.engine) as session:
        assert count(session, ProductionAttempt) == 0


def test_an_empty_recording(fake_env: FakeAiEnv) -> None:
    response = post(fake_env, b"")
    assert (response.status_code, code(response)) == (422, "audio_empty")


def test_duration_errors_give_the_bounds(fake_env: FakeAiEnv) -> None:
    detail = post(fake_env, duration_s=45).json()["detail"]
    assert (detail["min_s"], detail["max_s"]) == (0.5, 30.0)


def test_a_closed_study_session(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    with Session(fake_env.engine) as session:
        study = StudySession(started_at=fake_env.clock.now(), ended_at=fake_env.clock.now())
        session.add(study)
        session.commit()
        study_id = study.id
    response = post(fake_env, study_session_id=study_id)
    assert (response.status_code, code(response)) == (409, "session_closed")
    assert audio_files(tmp_path) == []


def test_a_term_and_the_discovery_origin(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard())
    item_id = quick_add(fake_env.client, "account for")
    response = post(fake_env, item_id=item_id, origin="discovery")
    assert response.status_code == 201
    detail = fake_env.client.get(f"/api/productions/{response.json()['production_id']}").json()
    assert [t["lexical_item_id"] for t in detail["targets"]] == [item_id]
    with Session(fake_env.engine) as session:
        [recorded] = events(session, "production.recorded")
        assert recorded["origin"] == "discovery"


def test_no_write_transaction_is_open_during_the_call(fake_env: FakeAiEnv) -> None:
    path = fake_env.db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    class Probing(FakeProvider):
        def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")  # 'database is locked' if a writer is open
                other.rollback()
            probes.append("free")
            return super().transcribe(request)

    fake_env.use(Probing("fake", [Failure(ErrorKind.NETWORK), heard()], capabilities=STT))
    production_id = post(fake_env).json()["production_id"]
    retry = fake_env.client.post(f"/api/productions/{production_id}/transcribe")
    assert retry.json()["transcription"]["status"] == "ok"
    assert probes == ["free", "free"]


# --- Transcribing again --------------------------------------------------------------------------


def test_a_failed_transcription_is_run_again(fake_env: FakeAiEnv) -> None:
    production_id = post(fake_env).json()["production_id"]
    speak(fake_env, heard())

    response = fake_env.client.post(f"/api/productions/{production_id}/transcribe")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["production_id"] == production_id
    assert body["transcription"]["status"] == "ok" and body["audio_seconds"] == 3.4
    assert body["comparison"]["recognized_count"] == 8
    again = fake_env.client.post(f"/api/productions/{production_id}/transcribe")
    assert (again.status_code, code(again)) == (409, "already_transcribed")
    with Session(fake_env.engine) as session:
        assert count(session, PronunciationResult) == 1


def test_transcribing_a_written_production(fake_env: FakeAiEnv) -> None:
    created = fake_env.client.post("/api/productions", json={"text": "A short text."})
    production_id = created.json()["id"]
    response = fake_env.client.post(f"/api/productions/{production_id}/transcribe")
    assert (response.status_code, code(response)) == (422, "no_audio")


def test_transcribing_an_unknown_production(fake_env: FakeAiEnv) -> None:
    response = fake_env.client.post("/api/productions/999/transcribe")
    assert (response.status_code, code(response)) == (404, "production_not_found")


# --- Playback ------------------------------------------------------------------------------------


def test_playback_gives_the_bytes_and_the_type(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard())
    url = post(fake_env).json()["audio_url"]

    response = fake_env.client.get(url)

    assert response.status_code == 200
    assert response.content == WAV
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["accept-ranges"] == "bytes"


def test_playback_answers_range_requests(fake_env: FakeAiEnv) -> None:
    url = post(fake_env).json()["audio_url"]
    response = fake_env.client.get(url, headers={"Range": "bytes=4-11"})
    assert response.status_code == 206
    assert response.content == WAV[4:12]
    assert response.headers["content-range"] == f"bytes 4-11/{len(WAV)}"


def test_playback_of_a_webm_recording(fake_env: FakeAiEnv) -> None:
    url = post(fake_env, b"\x1aE\xdf\xa3webm", content_type="audio/webm").json()["audio_url"]
    assert fake_env.client.get(url).headers["content-type"] == "audio/webm"


def test_playback_without_a_recording(fake_env: FakeAiEnv) -> None:
    production_id = fake_env.client.post("/api/productions", json={"text": "Text."}).json()["id"]
    response = fake_env.client.get(f"/api/productions/{production_id}/audio")
    assert (response.status_code, code(response)) == (404, "no_audio")


def test_playback_when_the_file_is_gone(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    url = post(fake_env).json()["audio_url"]
    for path in audio_files(tmp_path):
        path.unlink()
    response = fake_env.client.get(url)
    assert (response.status_code, code(response)) == (404, "no_audio")


def test_a_tampered_path_is_never_served(fake_env: FakeAiEnv, tmp_path: Path) -> None:
    url = post(fake_env).json()["audio_url"]
    secret = tmp_path / "data" / "secret.wav"
    secret.write_bytes(b"private")
    with Session(fake_env.engine) as session:
        attempt = session.scalars(select(ProductionAttempt)).one()
        attempt.audio_path = "../secret.wav"
        session.commit()
    response = fake_env.client.get(url)
    assert (response.status_code, code(response)) == (404, "no_audio")


def test_playback_of_an_unknown_production(fake_env: FakeAiEnv) -> None:
    response = fake_env.client.get("/api/productions/999/audio")
    assert (response.status_code, code(response)) == (404, "production_not_found")


# --- Productions list and detail -----------------------------------------------------------------


def test_productions_show_the_recording_and_the_comparison(fake_env: FakeAiEnv) -> None:
    speak(fake_env, heard())
    transcribed = post(fake_env).json()["production_id"]
    speak(fake_env, Failure(ErrorKind.NETWORK))
    pending = post(fake_env).json()["production_id"]
    written = fake_env.client.post("/api/productions", json={"text": "Text."}).json()["id"]

    page = fake_env.client.get("/api/productions", params={"kind": "shadowing"}).json()

    assert page["total"] == 2
    by_id = {item["id"]: item for item in page["items"]}
    assert set(by_id) == {transcribed, pending}
    done = by_id[transcribed]
    assert (done["kind"], done["modality"], done["prompt_text"]) == ("shadowing", "oral", TARGET)
    assert (done["text"], done["word_count"], done["corrected"]) == (HEARD, 0, False)
    assert done["audio_url"] == f"/api/productions/{transcribed}/audio"
    assert done["audio_seconds"] == 3.4
    assert done["transcription_status"] == "ok"
    assert done["comparison"]["unrecognized"] == [{"position": 4, "word": "fixed", "heard": "fix"}]
    waiting = by_id[pending]
    assert (waiting["transcription_status"], waiting["comparison"]) == ("pending", None)
    assert waiting["audio_seconds"] == 1.5

    detail = fake_env.client.get(f"/api/productions/{transcribed}").json()
    assert detail["comparison"] == done["comparison"]
    plain = fake_env.client.get(f"/api/productions/{written}").json()
    assert (plain["audio_url"], plain["audio_seconds"]) == (None, None)
    assert (plain["transcription_status"], plain["comparison"]) == (None, None)


def test_the_upload_is_described_in_openapi(fake_env: FakeAiEnv) -> None:
    spec = fake_env.client.get("/openapi.json").json()
    body = spec["paths"]["/api/speech/shadowing"]["post"]["requestBody"]
    assert body["required"] is True
    assert set(body["content"]) == {
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
    }
    assert body["content"]["audio/wav"]["schema"] == {"type": "string", "format": "binary"}
