"""One real request per configured provider (see `conftest.py` for how to run them)."""

import os
import warnings
from pathlib import Path

import pytest

from app.ai.providers import Provider
from app.ai.providers.gemini import GeminiProvider
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AudioClip, ErrorKind, ProviderError, ProviderRequest, TranscriptionRequest

AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}


def _request(timeout_s: float) -> ProviderRequest:
    return ProviderRequest(
        system="You are a connectivity probe. Reply with one JSON object and nothing else.",
        user='Set "ok" to true and copy the text below, unchanged, into "echo".\n\nping',
        json_schema=ConnectionTestOutput.model_json_schema(),
        timeout_s=timeout_s,
        max_output_tokens=100,
    )


def _live_call(provider: Provider, timeout_s: float) -> ConnectionTestOutput:
    try:
        response = provider.generate_json(_request(timeout_s))
    except ProviderError as exc:
        if exc.kind in (ErrorKind.RATE_LIMITED, ErrorKind.QUOTA_EXHAUSTED):
            pytest.skip(f"quota or rate limit reached ({exc.kind.value}): {exc.message}")
        pytest.fail(f"{provider.name}: {exc.kind.value} (HTTP {exc.status_code}): {exc.message}")
    assert response.model
    return ConnectionTestOutput.model_validate_json(response.text)


def test_gemini_answers_with_valid_json(gemini: GeminiProvider) -> None:
    # Settles risk n° 1 (D-058). If Google refuses the `responseFormat` field, the adapter switches
    # to `responseMimeType` + `responseJsonSchema` by itself: the second request (at most) then
    # proves the older fields work, and a warning tells the owner which mode is the right one.
    started_in = gemini.json_mode
    try:
        answer = _live_call(gemini, timeout_s=30)
    except pytest.fail.Exception:
        if gemini.json_mode == started_in:
            raise
        answer = _live_call(gemini, timeout_s=30)
        warnings.warn(
            f"Gemini refused the {started_in!r} JSON fields; {gemini.json_mode!r} works: "
            "update D-058 and make it the default",
            stacklevel=1,
        )
    assert answer.ok is True and "ping" in answer.echo


def test_groq_answers_with_valid_json(groq: Provider) -> None:
    answer = _live_call(groq, timeout_s=30)
    assert answer.ok is True and "ping" in answer.echo


def test_ollama_answers_with_valid_json(ollama: Provider) -> None:
    # The first request may have to load the model into memory.
    answer = _live_call(ollama, timeout_s=90)
    assert answer.ok is True


def test_groq_whisper_transcribes_the_clip_in_vocab_live_audio(groq: Provider) -> None:
    value = os.environ.get("VOCAB_LIVE_AUDIO")
    if not value:
        pytest.skip("set VOCAB_LIVE_AUDIO to a short audio file to test Whisper")
    path = Path(value)
    if not path.is_file():
        pytest.skip(f"VOCAB_LIVE_AUDIO does not point to a file: {path}")
    clip = AudioClip(
        data=path.read_bytes(),
        filename=path.name,
        content_type=AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream"),
    )
    try:
        response = groq.transcribe(TranscriptionRequest(audio=clip, language="en", timeout_s=60))
    except ProviderError as exc:
        if exc.kind in (ErrorKind.RATE_LIMITED, ErrorKind.QUOTA_EXHAUSTED):
            pytest.skip(f"quota or rate limit reached ({exc.kind.value}): {exc.message}")
        pytest.fail(f"groq transcription: {exc.kind.value} (HTTP {exc.status_code}): {exc.message}")
    assert response.text.strip(), "Whisper returned no text for this clip"
