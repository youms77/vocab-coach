"""`transcribe` goes through the same core as `generate_json`, filtered by capability."""

from collections.abc import Callable

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import (
    AudioClip,
    Capability,
    ErrorKind,
    SpeechSegment,
    TranscriptionDetails,
    UnavailableReason,
)
from tests.ai.conftest import log_rows, ping

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]

AUDIO = AudioClip(data=b"RIFF....", filename="clip.webm", content_type="audio/webm")
STT = (Capability.TRANSCRIPTION,)


def test_transcription_returns_text_and_is_logged(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    stt = provider_factory(
        "stt", Success(content="we account for fixed effects", output_tokens=None), capabilities=STT
    )
    result = make_gateway(stt).transcribe(AUDIO, language="en")

    assert result.ok and result.data is not None
    assert result.data.text == "we account for fixed effects"
    assert stt.transcriptions[0].audio == AUDIO and stt.transcriptions[0].language == "en"
    [row] = log_rows(engine)
    assert (row.task, row.provider, row.prompt_version, row.success) == (
        "transcription",
        "stt",
        None,
        True,
    )


def test_providers_without_the_capability_are_ignored(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    text_only = provider_factory("text", Success())
    stt = provider_factory("stt", Success(content="hello"), capabilities=STT)
    gateway = make_gateway(text_only, stt)

    assert gateway.transcribe(AUDIO).provider == "stt"
    assert ping(gateway).provider == "text"  # and the reverse for text
    assert text_only.calls == 1 and stt.calls == 1

    only_text = make_gateway(text_only)
    result = only_text.transcribe(AUDIO)
    assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED


def test_transcription_retries_and_falls_back_like_text(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED), capabilities=STT)
    b = provider_factory("b", Success(content="ok then"), capabilities=STT)
    result = make_gateway(a, b).transcribe(AUDIO)

    assert result.ok and result.provider == "b"
    assert [(r.provider, r.fallback_from) for r in log_rows(engine)] == [("a", None), ("b", "a")]


def test_the_fake_provider_plays_a_duration_and_segments(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    details = TranscriptionDetails(
        duration_s=2.5, segments=(SpeechSegment(start=0.0, end=2.5, no_speech_prob=0.1),)
    )
    stt = provider_factory("stt", Success(content="hello", transcription=details), capabilities=STT)
    result = make_gateway(stt).transcribe(AUDIO)

    assert result.ok and result.data is not None
    assert result.data.duration_s == 2.5
    assert [s.model_dump() for s in result.data.segments] == [
        {"start": 0.0, "end": 2.5, "no_speech_prob": 0.1, "avg_logprob": None}
    ]


def test_without_details_the_output_has_text_only(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    stt = provider_factory("stt", Success(content="hello"), capabilities=STT)
    result = make_gateway(stt).transcribe(AUDIO)
    assert result.data is not None
    assert (result.data.duration_s, result.data.segments) == (None, [])
