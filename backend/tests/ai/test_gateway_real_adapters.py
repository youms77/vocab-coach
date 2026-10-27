"""The gateway with the real Groq and Ollama adapters, against fake servers on the loopback.

Same policy as with the fake provider (retry, fallback, cooldown, repair, journal), but the errors
now travel through real HTTP: status codes, headers and bodies are translated by the adapters.
The fake clock only moves with the gateway's own waits, so nothing here sleeps for real except the
timeout tests (a few tenths of a second).
"""

import socket
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.ai.gateway import Gateway
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.tasks import TaskSpec
from app.ai.types import AiStatus, AudioClip, UnavailableReason
from tests.ai.conftest import FakeClock, log_rows, ping
from tests.ai.fake_server import FakeServer, Reply, fixture_reply

ServerFactory = Callable[..., FakeServer]
GatewayFactory = Callable[..., Gateway]
KEY = "gsk_test_0123456789abcdefghij"


def _groq(server: FakeServer) -> GroqProvider:
    return GroqProvider(KEY, base_url=server.base_url)


def _ollama(server: FakeServer) -> OllamaProvider:
    return OllamaProvider(server.base_url)


def _groq_text(content: str) -> Reply:
    body = {
        "model": "openai/gpt-oss-20b",
        "choices": [{"index": 0, "message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 9},
    }
    return Reply(body=body)


def test_429_per_minute_then_success(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    groq = make_server(
        fixture_reply("groq", "error_429_tpm", status=429, headers={"retry-after": "2"}),
        fixture_reply("groq", "chat_ok"),
    )
    result = ping(make_gateway(_groq(groq), secrets=[KEY]))

    assert result.ok and result.provider == "groq" and result.attempts == 2
    assert result.model == "openai/gpt-oss-20b" and (result.input_tokens, result.output_tokens) == (
        96,
        14,
    )
    assert clock.sleeps == [2.0]  # the Retry-After header, not the 2.625 s of the message
    first, second = log_rows(engine)
    assert (first.success, first.error_code, first.http_status) == (False, "rate_limited", 429)
    assert (second.success, second.attempt, second.input_tokens) == (True, 2, 96)


def test_daily_quota_falls_back_then_the_provider_is_skipped_until_the_cooldown_ends(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    groq = make_server(fixture_reply("groq", "error_429_rpd", status=429))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(_groq(groq), _ollama(ollama), secrets=[KEY])

    first = ping(gateway)

    assert first.ok and first.provider == "ollama" and first.attempts == 2
    rows = log_rows(engine)
    assert [(r.provider, r.error_code, r.http_status, r.fallback_from) for r in rows] == [
        ("groq", "quota_exhausted", 429, None),
        ("ollama", None, None, "groq"),
    ]
    [status_groq, _] = gateway.status()
    # The service said "try again in 7m12.5s": the cooldown is exactly that, not a blind hour.
    assert status_groq.cooldown_until == clock.now() + timedelta(seconds=432.5)

    assert ping(gateway).provider == "ollama"
    assert len(groq.requests) == 1  # skipped while cooling down

    clock.advance(433)
    ping(gateway)
    assert len(groq.requests) == 2  # probed again


def test_a_daily_quota_without_a_delay_cools_down_for_an_hour(
    make_server: ServerFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    body = {"error": {"message": "Rate limit reached on requests per day (RPD)."}}
    groq = make_server(Reply(status=429, body=body))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(_groq(groq), _ollama(ollama))
    ping(gateway)
    [status_groq, _] = gateway.status()
    assert status_groq.cooldown_until == clock.now() + timedelta(hours=1)


def test_invalid_key_is_ignored_until_reload(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(
        fixture_reply("groq", "error_401", status=401), fixture_reply("groq", "chat_ok")
    )
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(_groq(groq), _ollama(ollama), secrets=[KEY])

    first = ping(gateway)
    assert first.provider == "ollama"
    [status_groq, _] = gateway.status()
    assert status_groq.misconfigured and not status_groq.available

    assert ping(gateway).provider == "ollama"
    assert len(groq.requests) == 1  # not asked again: the key is known to be wrong

    gateway.reload()  # the owner fixed the key
    third = ping(gateway)
    assert third.provider == "groq" and len(groq.requests) == 2
    assert not gateway.status()[0].misconfigured


def test_invalid_json_is_repaired_once_then_incomplete_without_fallback(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine
) -> None:
    groq = make_server(_groq_text("this is not json"))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))

    result = ping(make_gateway(_groq(groq), _ollama(ollama)))

    assert result.status is AiStatus.INCOMPLETE and result.provider == "groq"
    assert result.attempts == 2 and len(groq.requests) == 2
    assert ollama.requests == []  # an invalid answer never triggers a fallback (D-039)
    repair = groq.requests[1].json()["messages"][1]["content"]
    assert "Your previous answer was rejected" in repair
    assert [r.error_code for r in log_rows(engine)] == ["invalid_output", "invalid_output"]


def test_schema_violation_is_repaired_without_quoting_the_output(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(
        _groq_text('{"ok": "maybe", "echo": "ping"}'), fixture_reply("groq", "chat_ok")
    )

    result = ping(make_gateway(_groq(groq)))

    assert result.ok and result.attempts == 2
    repair = groq.requests[1].json()["messages"][1]["content"]
    assert "ok:" in repair and "maybe" not in repair  # the location of the problem, not its value


def test_the_provider_native_schema_error_is_repaired_too(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(
        fixture_reply("groq", "error_400_schema", status=400), fixture_reply("groq", "chat_ok")
    )
    result = ping(make_gateway(_groq(groq)))
    assert result.ok and result.attempts == 2


def test_request_timeout_retries_then_falls_back(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    quick = TaskSpec(
        name="connection_test",
        prompt_version=1,
        output_schema=ConnectionTestOutput,
        max_input_chars=200,
        max_output_tokens=100,
        timeout_s=0.2,
    )
    groq = make_server(Reply(body="{}", delay_s=1.0))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))

    result = ping(make_gateway(_groq(groq), _ollama(ollama), tasks={"connection_test": quick}))

    assert result.ok and result.provider == "ollama"
    assert clock.sleeps == [1.0, 2.0]  # three timed-out attempts on Groq, backoff in between
    rows = log_rows(engine)
    assert [(r.provider, r.error_code) for r in rows[:3]] == [("groq", "transient")] * 3
    assert rows[3].provider == "ollama" and rows[3].fallback_from == "groq"


def test_a_provider_that_always_rate_limits_is_set_aside_for_a_minute(
    make_server: ServerFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    groq = make_server(
        fixture_reply("groq", "error_429_tpm", status=429, headers={"retry-after": "1"})
    )
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(_groq(groq), _ollama(ollama))

    first = ping(gateway)
    assert first.provider == "ollama" and len(groq.requests) == 3
    assert clock.sleeps == [1.0, 1.0]
    assert gateway.status()[0].cooldown_until == clock.now() + timedelta(seconds=60)

    ping(gateway)
    assert len(groq.requests) == 3  # the next call does not pay for three more 429s

    clock.advance(61)
    ping(gateway)
    assert len(groq.requests) == 6


def test_ollama_that_is_not_running_is_a_network_failure(
    make_gateway: GatewayFactory, engine
) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    gateway = make_gateway(OllamaProvider(f"http://127.0.0.1:{port}"))

    result = ping(gateway)

    assert result.status is AiStatus.UNAVAILABLE and result.reason is UnavailableReason.NETWORK
    assert result.provider == "ollama" and result.model == "gemma3:4b"
    [row] = log_rows(engine)
    assert (row.error_code, row.http_status, row.success) == ("network", None, False)
    assert str(port) not in (row.error_message or "")


def test_every_provider_failing_is_all_failed_with_the_last_message(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(fixture_reply("groq", "error_401", status=401))
    ollama = make_server(fixture_reply("ollama", "error_model_not_found", status=404))

    result = ping(make_gateway(_groq(groq), _ollama(ollama), secrets=[KEY]))

    assert result.status is AiStatus.UNAVAILABLE and result.reason is UnavailableReason.ALL_FAILED
    assert result.provider == "ollama" and "ollama pull" in (result.detail or "")


def test_pin_provider_uses_only_the_requested_one(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(fixture_reply("groq", "chat_ok"))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    result = ping(make_gateway(_groq(groq), _ollama(ollama)), pin_provider="ollama")
    assert result.provider == "ollama" and groq.requests == []


def test_an_unconfigured_real_provider_is_skipped_silently(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine
) -> None:
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(GroqProvider(None), _ollama(ollama))
    assert ping(gateway).provider == "ollama"
    assert [r.provider for r in log_rows(engine)] == ["ollama"]  # nothing logged for Groq
    assert [s.configured for s in gateway.status()] == [False, True]


# --- Transcription through the gateway --------------------------------------------------------


def test_transcription_goes_to_groq_and_is_journalled(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine
) -> None:
    groq = make_server(fixture_reply("groq", "transcription_ok"))
    ollama = make_server(fixture_reply("ollama", "chat_ok"))
    gateway = make_gateway(_groq(groq), _ollama(ollama))  # Ollama cannot transcribe

    result = gateway.transcribe(
        AudioClip(data=b"RIFFxxxx", filename="a.wav", content_type="audio/wav")
    )

    assert result.ok and result.data is not None
    assert result.data.text == "Hello, this is a short test of my English."
    assert (result.provider, result.model) == ("groq", "whisper-large-v3")
    [row] = log_rows(engine)
    assert (row.task, row.prompt_version, row.model) == ("transcription", None, "whisper-large-v3")
    assert ollama.requests == []


def test_the_duration_and_segments_reach_the_transcription_output(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    groq = make_server(fixture_reply("groq", "transcription_verbose_hallucination"))
    clip = AudioClip(data=b"RIFFxxxx", filename="a.wav", content_type="audio/wav")

    result = make_gateway(_groq(groq)).transcribe(clip)

    assert result.ok and result.data is not None
    assert result.data.duration_s == 1.8
    [segment] = result.data.segments
    assert (segment.start, segment.end) == (0.0, 1.8)
    assert (segment.no_speech_prob, segment.avg_logprob) == (0.9214, -1.3127)


def test_oversized_audio_is_refused_without_a_request(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine
) -> None:
    groq = make_server(fixture_reply("groq", "transcription_ok"))
    clip = AudioClip(
        data=b"\x00" * (25 * 1024 * 1024 + 1), filename="long.wav", content_type="audio/wav"
    )

    result = make_gateway(_groq(groq)).transcribe(clip)

    assert result.status is AiStatus.UNAVAILABLE and result.reason is UnavailableReason.ALL_FAILED
    assert "25.0 MB" in (result.detail or "")
    assert groq.requests == []
    [row] = log_rows(engine)
    assert (row.error_code, row.http_status) == ("bad_request", None)


@pytest.mark.parametrize("language", ["en", "fr"])
def test_the_language_is_sent_to_whisper(
    make_server: ServerFactory, make_gateway: GatewayFactory, language: str
) -> None:
    groq = make_server(fixture_reply("groq", "transcription_ok"))
    clip = AudioClip(data=b"RIFFxxxx", filename="a.wav", content_type="audio/wav")
    make_gateway(_groq(groq)).transcribe(clip, language=language)
    assert f'name="language"\r\n\r\n{language}\r\n'.encode() in groq.requests[0].body
