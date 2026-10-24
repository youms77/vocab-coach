"""The Azure Speech adapter against a fake server on the loopback interface (no Azure call).

The fixtures are built from Microsoft's documentation; the error bodies are not documented, so the
"quota" heuristic is a guess (D-211, D-213).
"""

import base64
import json
from collections.abc import Callable

import pytest

from app.ai.providers.azure_speech import (
    MODEL,
    PATH,
    AzureSpeechProvider,
    default_base_url,
)
from app.ai.types import (
    AudioClip,
    Capability,
    ErrorKind,
    PronunciationRequest,
    ProviderError,
)
from tests.ai.conftest import provider_request
from tests.ai.fake_server import FakeServer, Reply, fixture_reply
from tests.audio_support import WEBM, ogg, wav

ServerFactory = Callable[..., FakeServer]
KEY = "az_test_0123456789abcdef0123456789"


def _provider(server: FakeServer | None = None, region: str | None = "westeurope"):
    return AzureSpeechProvider(KEY, region, base_url=server.base_url if server else None)


def _request(
    data: bytes | None = None, filename: str = "take.wav", text: str = "I think about it."
) -> PronunciationRequest:
    clip = AudioClip(data=wav() if data is None else data, filename=filename, content_type="x/y")
    return PronunciationRequest(audio=clip, reference_text=text, language="en-US", timeout_s=5.0)


def _error(provider: AzureSpeechProvider, request: PronunciationRequest | None = None):
    with pytest.raises(ProviderError) as caught:
        provider.assess_pronunciation(request or _request())
    return caught.value


# --- Configuration and URL --------------------------------------------------------------------


def test_configured_needs_key_and_region_and_repr_hides_the_key() -> None:
    assert _provider().is_configured()
    assert not AzureSpeechProvider(KEY, None).is_configured()
    assert not AzureSpeechProvider(None, "westeurope").is_configured()
    assert not AzureSpeechProvider("  ", "westeurope").is_configured()
    assert KEY not in repr(_provider())
    assert _provider().capabilities == {Capability.PRONUNCIATION_ASSESSMENT}
    assert _provider().model_for(Capability.PRONUNCIATION_ASSESSMENT) == MODEL


def test_the_default_url_is_built_from_the_region() -> None:
    assert default_base_url("westeurope") == "https://westeurope.stt.speech.microsoft.com"
    assert _provider()._url("en-US") == (
        "https://westeurope.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1?language=en-US&format=detailed"
    )


@pytest.mark.parametrize("region", ["a", "west europe", "evil.com/x", "w@h", "x" * 41, "a?b"])
def test_an_invalid_region_is_refused_before_any_request(region: str) -> None:
    error = _error(AzureSpeechProvider(KEY, region))
    assert error.kind is ErrorKind.BAD_REQUEST and "not a valid region" in error.message


def test_the_region_is_lower_cased() -> None:
    assert AzureSpeechProvider(KEY, "WestEurope").region == "westeurope"


def test_an_invalid_language_is_refused() -> None:
    with pytest.raises(ProviderError) as caught:
        _provider()._url("en-US&x=1")
    assert caught.value.kind is ErrorKind.BAD_REQUEST


# --- The request -------------------------------------------------------------------------------


def test_the_request_has_the_documented_shape(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    data = wav(2.0)
    _provider(server).assess_pronunciation(_request(data, text="I think about it, Zoë."))

    [received] = server.requests
    assert received.method == "POST"
    assert received.path == f"{PATH}?language=en-US&format=detailed"
    assert received.headers["ocp-apim-subscription-key"] == KEY
    assert KEY not in received.path
    assert received.headers["content-type"] == "audio/wav; codecs=audio/pcm; samplerate=16000"
    assert received.body == data
    header = json.loads(base64.b64decode(received.headers["pronunciation-assessment"]))
    assert header == {
        "ReferenceText": "I think about it, Zoë.",
        "GradingSystem": "HundredMark",
        "Granularity": "Phoneme",
        "Dimension": "Comprehensive",
        "EnableMiscue": "True",
        "PhonemeAlphabet": "IPA",
    }


def test_an_ogg_opus_clip_is_sent_as_ogg(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    _provider(server).assess_pronunciation(_request(ogg(3.0), filename="take.ogg"))
    assert server.requests[0].headers["content-type"] == "audio/ogg; codecs=opus"


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (WEBM, "take.webm"),
        (b"ID3" + b"\x00" * 30, "take.mp3"),
        (wav(rate=44100), "take.wav"),
        (wav(), "take.webm"),  # the name must agree with the content
        (b"", "take.wav"),
    ],
    ids=["webm", "mp3", "wav44k", "wrong-name", "empty"],
)
def test_a_format_azure_refuses_costs_no_request(
    data: bytes, filename: str, make_server: ServerFactory
) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    error = _error(_provider(server), _request(data, filename))
    assert error.kind is ErrorKind.BAD_REQUEST and "WAV" in error.message
    assert server.requests == []


@pytest.mark.parametrize("data", [wav(30.5), ogg(31.0)], ids=["wav", "ogg"])
def test_audio_over_thirty_seconds_costs_no_request(
    data: bytes, make_server: ServerFactory
) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    name = "take.wav" if data[:4] == b"RIFF" else "take.ogg"
    error = _error(_provider(server), _request(data, name))
    assert error.kind is ErrorKind.BAD_REQUEST and "30 s" in error.message
    assert server.requests == []


def test_thirty_seconds_exactly_is_accepted(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    _provider(server).assess_pronunciation(_request(wav(30.0)))
    assert len(server.requests) == 1


def test_an_empty_reference_text_costs_no_request(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    assert _error(_provider(server), _request(text="  ")).kind is ErrorKind.BAD_REQUEST
    assert server.requests == []


def test_other_capabilities_are_refused() -> None:
    provider = _provider()
    with pytest.raises(ProviderError) as text:
        provider.generate_json(provider_request())
    assert text.value.kind is ErrorKind.BAD_REQUEST
    with pytest.raises(ProviderError) as speech:
        provider.transcribe(None)  # type: ignore[arg-type]
    assert speech.value.kind is ErrorKind.BAD_REQUEST


# --- Answers ------------------------------------------------------------------------------------


def _assess(make_server: ServerFactory, fixture: str):
    server = make_server(fixture_reply("azure", fixture))
    response = _provider(server).assess_pronunciation(_request())
    assert response.assessment is not None
    return response.assessment


@pytest.mark.parametrize("fixture", ["success_flat", "success_nested"])
def test_both_documented_shapes_give_the_same_result(
    fixture: str, make_server: ServerFactory
) -> None:
    out = _assess(make_server, fixture)
    assert out.status == "ok"
    assert (out.accuracy, out.fluency, out.completeness, out.pronunciation) == (
        78.0,
        84.0,
        66.0,
        74.5,
    )
    assert out.duration_s == 1.8
    think, about, it = out.words
    assert (think.word, think.accuracy, think.error_type) == ("think", 52.0, "Mispronunciation")
    assert (think.offset_ms, think.duration_ms) == (500, 450)
    assert [(p.phoneme, p.accuracy) for p in think.phonemes] == [
        ("θ", 18.0),
        ("ɪ", 91.0),
        ("ŋ", 77.0),
        ("k", 88.0),
    ]
    assert about.error_type == "None" and it.error_type == "Omission" and it.phonemes == []


def test_a_response_carries_the_model_and_no_text(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", "success_flat"))
    response = _provider(server).assess_pronunciation(_request())
    assert response.model == MODEL and response.text == ""


def test_hostile_values_are_tolerated(make_server: ServerFactory) -> None:
    out = _assess(make_server, "success_odd")
    assert out.status == "ok"
    assert out.accuracy == 80.0  # a numeric string is read
    assert out.fluency is None  # out of 0-100
    assert out.completeness is None and out.pronunciation is None  # null, boolean
    assert out.duration_s == 1.2
    assert [w.word for w in out.words] == ["ok", "fine"]  # junk entries skipped
    ok, fine = out.words
    assert ok.accuracy is None and ok.error_type is None and ok.offset_ms is None
    assert [(p.phoneme, p.accuracy) for p in ok.phonemes] == [("o", 50.0)]
    assert fine.error_type == "UnexpectedBreak"  # unknown values are kept as is


@pytest.mark.parametrize("fixture", ["nomatch", "initial_silence", "babble"])
def test_a_recognition_without_speech_is_a_silence_result(
    fixture: str, make_server: ServerFactory
) -> None:
    out = _assess(make_server, fixture)
    assert out.status == "silence"
    assert out.pronunciation is None and out.words == []


@pytest.mark.parametrize(
    ("fixture", "kind"),
    [
        ("status_error", ErrorKind.TRANSIENT),
        ("success_no_nbest", ErrorKind.INVALID_OUTPUT),
        ("status_unknown", ErrorKind.INVALID_OUTPUT),
    ],
)
def test_unusable_answers(fixture: str, kind: ErrorKind, make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("azure", fixture))
    assert _error(_provider(server)).kind is kind


@pytest.mark.parametrize(
    "body", [b"not json at all", b"[1, 2]", b'"text"', b""], ids=["text", "list", "string", "empty"]
)
def test_garbage_is_invalid_output(body: bytes, make_server: ServerFactory) -> None:
    server = make_server(Reply(status=200, body=body))
    assert _error(_provider(server)).kind is ErrorKind.INVALID_OUTPUT


# --- Errors (column "Azure" of the D-050 table) ---------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "status", "kind"),
    [
        ("error_401", 401, ErrorKind.AUTH),
        ("error_403", 403, ErrorKind.AUTH),
        ("error_403_quota", 403, ErrorKind.QUOTA_EXHAUSTED),
        ("error_429_quota", 429, ErrorKind.QUOTA_EXHAUSTED),
        ("error_429", 429, ErrorKind.RATE_LIMITED),
        ("error_500", 500, ErrorKind.TRANSIENT),
        ("error_500", 503, ErrorKind.TRANSIENT),
        ("error_500", 408, ErrorKind.TRANSIENT),
        ("error_400", 400, ErrorKind.BAD_REQUEST),
        ("error_400", 302, ErrorKind.BAD_REQUEST),
    ],
)
def test_http_errors(
    fixture: str, status: int, kind: ErrorKind, make_server: ServerFactory
) -> None:
    server = make_server(fixture_reply("azure", fixture, status=status))
    error = _error(_provider(server))
    assert error.kind is kind and error.status_code == status


def test_retry_after_is_read_on_a_429(make_server: ServerFactory) -> None:
    server = make_server(
        fixture_reply("azure", "error_429", status=429, headers={"Retry-After": "7"})
    )
    assert _error(_provider(server)).retry_after == 7.0


def test_a_plain_text_error_body_is_used_and_an_empty_one_gives_the_status(
    make_server: ServerFactory,
) -> None:
    server = make_server(Reply(status=400, body=b"Bad audio"), Reply(status=502, body=b""))
    provider = _provider(server)
    assert "Bad audio" in _error(provider).message
    assert _error(provider).message == "HTTP 502"


def test_a_hostile_server_that_echoes_the_key_leaks_nothing(make_server: ServerFactory) -> None:
    def echo(received) -> Reply:
        key = received.headers["ocp-apim-subscription-key"]
        return Reply(status=401, body={"error": {"message": f"bad key {key} again {key}"}})

    server = make_server(handler=echo)
    provider = _provider(server)
    error = _error(provider)
    assert KEY not in error.message and "***" in error.message
    assert KEY not in repr(provider) and KEY not in str(error)


# --- Settings ----------------------------------------------------------------------------


def test_settings_read_the_variables_mask_the_key_and_treat_empty_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.providers import build_providers
    from app.config import Settings

    settings = Settings(_env_file=None, azure_speech_key=KEY, azure_speech_region="westeurope")  # type: ignore[arg-type]
    assert KEY in settings.secret_values() and KEY not in repr(settings)
    provider = build_providers(settings)["azure"]
    assert provider.is_configured() and KEY not in repr(provider)
    empty = Settings(_env_file=None, azure_speech_key="  ", azure_speech_region="")  # type: ignore[arg-type]
    assert empty.azure_speech_key is None and empty.azure_speech_region is None
    monkeypatch.setenv("VOCAB_AZURE_SPEECH_KEY", KEY)
    monkeypatch.setenv("VOCAB_AZURE_SPEECH_REGION", "swedencentral")
    from_env = Settings(_env_file=None)
    assert from_env.azure_speech_region == "swedencentral"
    assert from_env.azure_speech_key is not None
