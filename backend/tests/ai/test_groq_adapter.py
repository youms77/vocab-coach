"""The Groq adapter against a fake server on the loopback interface (no real Groq call).

The fixtures come from the documentation and from public reports of real answers (see
`fixtures/README.md`); the 429 and 401 bodies in particular are not documented by Groq.
"""

from collections.abc import Callable

import pytest

from app.ai.providers.groq import (
    DEFAULT_TEXT_MODEL,
    DEFAULT_TRANSCRIPTION_MODEL,
    MAX_AUDIO_BYTES,
    REASONING_HEADROOM_TOKENS,
    GroqProvider,
)
from app.ai.types import (
    AudioClip,
    Capability,
    ErrorKind,
    ProviderError,
    SpeechSegment,
    TranscriptionDetails,
    TranscriptionRequest,
)
from tests.ai.conftest import provider_request
from tests.ai.fake_server import FakeServer, Reply, fixture_reply

ServerFactory = Callable[..., FakeServer]
KEY = "gsk_test_0123456789abcdef"


def _provider(server: FakeServer, **kwargs: str) -> GroqProvider:
    return GroqProvider(KEY, base_url=server.base_url + "/openai/v1", **kwargs)


def _error(provider: GroqProvider) -> ProviderError:
    with pytest.raises(ProviderError) as caught:
        provider.generate_json(provider_request())
    return caught.value


def _clip(data: bytes = b"RIFFfakewavdata", filename: str = "essai.wav") -> AudioClip:
    return AudioClip(data=data, filename=filename, content_type="audio/wav")


def _transcription(clip: AudioClip, language: str = "en") -> TranscriptionRequest:
    return TranscriptionRequest(audio=clip, language=language, timeout_s=5.0)


# --- Text request -----------------------------------------------------------------------------


def test_default_request_uses_the_structured_json_schema_mode(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_ok"))
    _provider(server).generate_json(provider_request(max_output_tokens=100, user="bonjour"))

    [received] = server.requests
    body = received.json()
    assert received.path == "/openai/v1/chat/completions"
    assert body["model"] == DEFAULT_TEXT_MODEL == "openai/gpt-oss-20b"
    assert body["temperature"] == 0
    assert body["max_completion_tokens"] == 100 + REASONING_HEADROOM_TOKENS
    assert body["reasoning_effort"] == "low" and body["include_reasoning"] is False
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is False  # best-effort: optional fields stay allowed
    assert fmt["json_schema"]["name"] == "output"
    schema = fmt["json_schema"]["schema"]
    assert schema["required"] == ["ok", "echo"] and schema["additionalProperties"] is False
    assert "title" not in schema
    system, user = body["messages"]
    assert system["content"].startswith("You are a connectivity probe")
    assert "JSON Schema" not in system["content"]  # native mode: no schema in the prompt
    assert "bonjour" in user["content"]


def test_key_is_only_in_the_authorization_header(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_ok"))
    _provider(server).generate_json(provider_request())

    [received] = server.requests
    assert received.headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in received.path
    assert KEY.encode() not in received.body
    assert received.headers["content-type"] == "application/json"
    assert received.headers["user-agent"].startswith("vocab-coach/")


def test_models_without_json_schema_support_get_json_object_mode(
    make_server: ServerFactory,
) -> None:
    server = make_server(fixture_reply("groq", "chat_fenced"))
    provider = _provider(server, text_model="llama-3.1-8b-instant")
    provider.generate_json(provider_request(max_output_tokens=100))

    body = server.requests[0].json()
    assert body["model"] == "llama-3.1-8b-instant"
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON" in body["messages"][0]["content"]  # Groq wants JSON mentioned in the prompt
    assert "matches this JSON Schema" in body["messages"][0]["content"]
    assert body["max_completion_tokens"] == 100  # no reasoning headroom
    assert "reasoning_effort" not in body and "include_reasoning" not in body


def test_models_per_capability(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_ok"))
    default = _provider(server)
    assert default.model_for(Capability.TEXT) == DEFAULT_TEXT_MODEL
    assert default.model_for(Capability.TRANSCRIPTION) == DEFAULT_TRANSCRIPTION_MODEL
    custom = _provider(
        server, text_model="openai/gpt-oss-120b", transcription_model="whisper-large-v3-turbo"
    )
    assert custom.model_for(Capability.TEXT) == "openai/gpt-oss-120b"
    assert custom.model_for(Capability.TRANSCRIPTION) == "whisper-large-v3-turbo"
    blank = GroqProvider(KEY, text_model=" ", transcription_model="")
    assert blank.model_for(Capability.TEXT) == DEFAULT_TEXT_MODEL
    assert default.capabilities == frozenset({Capability.TEXT, Capability.TRANSCRIPTION})


# --- Configuration ----------------------------------------------------------------------------


@pytest.mark.parametrize("key", [None, "", "   "])
def test_not_configured_without_a_key(key: str | None) -> None:
    assert GroqProvider(key).is_configured() is False


def test_calling_without_a_key_fails_before_any_request(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_ok"))
    provider = GroqProvider(None, base_url=server.base_url)
    with pytest.raises(ProviderError) as caught:
        provider.generate_json(provider_request())
    assert caught.value.kind is ErrorKind.AUTH
    assert server.requests == []


def test_repr_hides_the_key() -> None:
    provider = GroqProvider(KEY)
    assert KEY not in repr(provider) and KEY not in str(provider)
    assert "configured=True" in repr(provider)
    assert not hasattr(provider, "api_key")


# --- Valid answers ----------------------------------------------------------------------------


def test_valid_answer_with_tokens(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_ok"))
    response = _provider(server).generate_json(provider_request())
    assert response.text == '{"ok":true,"echo":"ping"}'
    assert response.model == "openai/gpt-oss-20b"
    assert (response.input_tokens, response.output_tokens) == (96, 14)


def test_json_fence_is_removed(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "chat_fenced"))
    response = _provider(server, text_model="llama-3.1-8b-instant").generate_json(
        provider_request()
    )
    assert response.text == '{"ok": true, "echo": "ping"}'
    assert response.model == "llama-3.1-8b-instant"


@pytest.mark.parametrize(
    ("fixture", "fragment"),
    [
        ("chat_truncated", "cut off"),
        ("chat_empty", "empty"),
        ("chat_filtered", "blocked"),
    ],
)
def test_unusable_answers_are_invalid_output(
    make_server: ServerFactory, fixture: str, fragment: str
) -> None:
    server = make_server(fixture_reply("groq", fixture))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.INVALID_OUTPUT and fragment in error.message


def test_an_answer_without_choices_is_a_bad_request(make_server: ServerFactory) -> None:
    server = make_server(Reply(body={"id": "x", "choices": []}))
    assert _error(_provider(server)).kind is ErrorKind.BAD_REQUEST


# --- Error translation (D-050) ----------------------------------------------------------------


def test_429_per_minute_uses_the_retry_after_header(make_server: ServerFactory) -> None:
    server = make_server(
        fixture_reply("groq", "error_429_tpm", status=429, headers={"retry-after": "2"})
    )
    error = _error(_provider(server))
    assert error.kind is ErrorKind.RATE_LIMITED and error.status_code == 429
    assert error.retry_after == 2.0  # the header wins over "2.625s" in the message
    assert "tokens per minute" in error.message


def test_429_without_header_reads_the_delay_in_the_message(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_429_tpm", status=429))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.RATE_LIMITED and error.retry_after == pytest.approx(2.625)


def test_429_falls_back_on_the_token_reset_header(make_server: ServerFactory) -> None:
    server = make_server(
        Reply(
            status=429,
            body={"error": {"message": "Rate limit reached on tokens per minute (TPM)."}},
            headers={"x-ratelimit-reset-tokens": "7.66s"},
        )
    )
    assert _error(_provider(server)).retry_after == pytest.approx(7.66)


@pytest.mark.parametrize(
    ("fixture", "retry_after"),
    [
        ("error_429_rpd", 432.5),
        ("error_429_tpd", 3903.0),
        ("error_429_asd", 2710.0),
    ],
)
def test_429_per_day_is_a_quota_error(
    make_server: ServerFactory, fixture: str, retry_after: float
) -> None:
    server = make_server(fixture_reply("groq", fixture, status=429))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.QUOTA_EXHAUSTED and error.status_code == 429
    assert error.retry_after == pytest.approx(retry_after)


def test_unlabelled_429_is_the_least_penalising_kind(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_429_unlabelled", status=429))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.RATE_LIMITED and error.retry_after is None


@pytest.mark.parametrize("status", [401, 403])
def test_key_rejected_is_auth_and_the_message_names_the_provider(
    make_server: ServerFactory, status: int
) -> None:
    server = make_server(fixture_reply("groq", "error_401", status=status))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.AUTH and error.status_code == status
    assert "Groq" in error.message and "Invalid API Key" in error.message
    assert KEY not in error.message


def test_schema_failure_is_invalid_output_without_the_model_output(
    make_server: ServerFactory,
) -> None:
    server = make_server(fixture_reply("groq", "error_400_schema", status=400))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.INVALID_OUTPUT and error.status_code == 400
    assert "maybe" not in error.message and "failed_generation" not in error.message


def test_other_400_is_a_bad_request_with_the_service_message(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_400_other", status=400))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and "reasoning_effort" in error.message


def test_unknown_model_points_at_the_environment_variables(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_404_model", status=404))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and "VOCAB_GROQ_TEXT_MODEL" in error.message


def test_request_too_large_is_a_bad_request(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_413", status=413))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and error.status_code == 413
    assert "too large" in error.message


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (500, ErrorKind.TRANSIENT),
        (502, ErrorKind.TRANSIENT),
        (503, ErrorKind.TRANSIENT),
        (498, ErrorKind.TRANSIENT),  # flex tier at capacity
        (408, ErrorKind.TRANSIENT),
        (418, ErrorKind.BAD_REQUEST),
    ],
)
def test_status_classes(make_server: ServerFactory, status: int, kind: ErrorKind) -> None:
    server = make_server(fixture_reply("groq", "error_503", status=status))
    error = _error(_provider(server))
    assert (error.kind, error.status_code) == (kind, status)


def test_an_error_without_a_json_body_still_translates(make_server: ServerFactory) -> None:
    server = make_server(Reply(status=502, body="<html>Bad gateway</html>"))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.TRANSIENT and error.message == "HTTP 502"


def test_timeout_is_transient(make_server: ServerFactory) -> None:
    server = make_server(Reply(body="{}", delay_s=1.0))
    with pytest.raises(ProviderError) as caught:
        _provider(server).generate_json(provider_request(timeout_s=0.2))
    assert caught.value.kind is ErrorKind.TRANSIENT


def test_a_redirect_is_not_followed(make_server: ServerFactory) -> None:
    """The key must never be forwarded to another host: a redirect is just an error answer."""
    target = make_server(fixture_reply("groq", "chat_ok"))
    server = make_server(Reply(status=307, headers={"Location": target.base_url + "/elsewhere"}))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and error.status_code == 307
    assert target.requests == []


# --- Whisper ----------------------------------------------------------------------------------


def test_transcription_request_is_a_multipart_upload(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    clip = _clip(b"RIFF\x00\x01binary-audio-bytes", "mon essai (1).wav")

    response = _provider(server).transcribe(_transcription(clip, language="en"))

    [received] = server.requests
    assert received.path == "/openai/v1/audio/transcriptions"
    assert received.headers["authorization"] == f"Bearer {KEY}"
    content_type = received.headers["content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    body = received.body
    assert b'name="model"\r\n\r\nwhisper-large-v3\r\n' in body
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'name="response_format"\r\n\r\nverbose_json\r\n' in body
    assert b'name="prompt"' not in body  # never a target sentence (D-172)
    assert b'name="file"; filename="mon_essai__1_.wav"' in body  # a safe file name
    assert b"Content-Type: audio/wav\r\n\r\nRIFF\x00\x01binary-audio-bytes\r\n" in body
    boundary = content_type.split("boundary=")[1].encode()
    assert body.endswith(b"--" + boundary + b"--\r\n")
    assert KEY.encode() not in body
    assert response.text == "Hello, this is a short test of my English."  # stripped
    assert response.model == "whisper-large-v3"
    assert response.input_tokens is None and response.output_tokens is None


def test_verbose_json_gives_the_duration_and_the_segments(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_verbose_ok"))
    response = _provider(server).transcribe(_transcription(_clip()))

    assert response.text == "We account for regional fixed effects in all specifications."
    assert response.transcription == TranscriptionDetails(
        duration_s=3.52,
        segments=(SpeechSegment(start=0.0, end=3.52, no_speech_prob=0.0123, avg_logprob=-0.2134),),
    )


def test_a_hallucination_over_silence_keeps_its_probabilities(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_verbose_hallucination"))
    response = _provider(server).transcribe(_transcription(_clip()))

    assert response.text == "Thank you."
    assert response.transcription is not None
    [segment] = response.transcription.segments
    assert (segment.no_speech_prob, segment.avg_logprob) == (0.9214, -1.3127)


def test_the_plain_json_format_is_still_read(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    response = _provider(server).transcribe(_transcription(_clip()))
    assert response.transcription == TranscriptionDetails(duration_s=None, segments=())


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        ("3.52", 3.52),
        (" 12 ", 12.0),
        (4.25, 4.25),
        (7, 7.0),
        ("0", 0.0),
        ("-1.5", None),
        ("NaN", None),
        ("inf", None),
        ("three", None),
        (True, None),
        (None, None),
        ([1.0], None),
    ],
)
def test_the_duration_is_read_as_a_string_or_a_number(
    make_server: ServerFactory, duration: object, expected: float | None
) -> None:
    server = make_server(Reply(body={"text": "hello", "duration": duration}))
    response = _provider(server).transcribe(_transcription(_clip()))
    assert response.transcription is not None
    assert response.transcription.duration_s == expected


def test_malformed_segments_are_ignored(make_server: ServerFactory) -> None:
    segments = [
        "not a segment",
        {"start": "0.5", "end": 2, "no_speech_prob": "high", "avg_logprob": -0.4},
        42,
        {},
    ]
    server = make_server(Reply(body={"text": "hello", "duration": "2", "segments": segments}))
    response = _provider(server).transcribe(_transcription(_clip()))

    assert response.transcription is not None
    assert response.transcription.segments == (
        SpeechSegment(start=0.5, end=2.0, no_speech_prob=None, avg_logprob=-0.4),
        SpeechSegment(),
    )


def test_segments_that_are_not_a_list_are_ignored(make_server: ServerFactory) -> None:
    server = make_server(Reply(body={"text": "hello", "segments": {"id": 0}}))
    response = _provider(server).transcribe(_transcription(_clip()))
    assert response.transcription is not None and response.transcription.segments == ()


def test_silence_is_an_empty_but_valid_transcription(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_silence"))
    assert _provider(server).transcribe(_transcription(_clip())).text == ""


def test_transcription_without_text_is_invalid_output(make_server: ServerFactory) -> None:
    server = make_server(Reply(body={"x_groq": {"id": "req"}}))
    with pytest.raises(ProviderError) as caught:
        _provider(server).transcribe(_transcription(_clip()))
    assert caught.value.kind is ErrorKind.INVALID_OUTPUT


def test_oversized_audio_is_refused_before_any_request(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    big = _clip(b"\x00" * (MAX_AUDIO_BYTES + 1))

    with pytest.raises(ProviderError) as caught:
        _provider(server).transcribe(_transcription(big))

    assert caught.value.kind is ErrorKind.BAD_REQUEST
    assert "25.0 MB" in caught.value.message and "at most 25 MB" in caught.value.message
    assert server.requests == []  # nothing was sent


def test_audio_of_exactly_the_limit_is_accepted(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    _provider(server).transcribe(_transcription(_clip(b"\x00" * MAX_AUDIO_BYTES)))
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("data", "filename", "fragment"),
    [
        (b"", "a.wav", "empty"),
        (b"data", "notes.txt", "unsupported audio format 'txt'"),
        (b"data", "recording", "no extension"),
    ],
)
def test_clips_groq_would_refuse_are_refused_locally(
    make_server: ServerFactory, data: bytes, filename: str, fragment: str
) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    with pytest.raises(ProviderError) as caught:
        _provider(server).transcribe(_transcription(_clip(data, filename)))
    assert caught.value.kind is ErrorKind.BAD_REQUEST and fragment in caught.value.message
    assert server.requests == []


@pytest.mark.parametrize(
    "extension", ["flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"]
)
def test_every_documented_audio_format_is_accepted(
    make_server: ServerFactory, extension: str
) -> None:
    server = make_server(fixture_reply("groq", "transcription_ok"))
    _provider(server).transcribe(_transcription(_clip(b"data", f"clip.{extension.upper()}")))
    assert len(server.requests) == 1


def test_transcription_quota_error(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("groq", "error_429_asd", status=429))
    with pytest.raises(ProviderError) as caught:
        _provider(server).transcribe(_transcription(_clip()))
    assert caught.value.kind is ErrorKind.QUOTA_EXHAUSTED
