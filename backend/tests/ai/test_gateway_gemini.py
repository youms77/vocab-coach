"""The gateway with the real Gemini adapter (and Groq as its fallback) over fake servers.

Gemini's `retryDelay` values reported by users are 14 to 57 seconds (D-046): these tests pin what
the policy does with such delays (D-060), with the errors travelling through real HTTP.
"""

from collections.abc import Callable
from datetime import timedelta

import pytest

from app.ai.gateway import Gateway
from app.ai.policy import MAX_WAIT_S
from app.ai.providers.gemini import JSON_MODE_LEGACY, GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.types import AiStatus
from tests.ai.conftest import FakeClock, log_rows, ping
from tests.ai.fake_server import FakeServer, Reply, fixture_reply

ServerFactory = Callable[..., FakeServer]
GatewayFactory = Callable[..., Gateway]
GEMINI_KEY = "AIzaSyTest_0123456789abcdefghij"
GROQ_KEY = "gsk_test_0123456789abcdefghij"


def _gemini(server: FakeServer, **kwargs: str) -> GeminiProvider:
    return GeminiProvider(GEMINI_KEY, base_url=server.base_url + "/v1beta", **kwargs)


def _groq(server: FakeServer) -> GroqProvider:
    return GroqProvider(GROQ_KEY, base_url=server.base_url)


def _gateway(make_gateway: GatewayFactory, gemini: GeminiProvider, groq: GroqProvider) -> Gateway:
    return make_gateway(gemini, groq, secrets=[GEMINI_KEY, GROQ_KEY])


def test_a_per_minute_429_with_a_short_delay_is_waited_for(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    gemini = make_server(
        fixture_reply("gemini", "error_429_minute", status=429),
        fixture_reply("gemini", "generate_ok"),
    )
    groq = make_server(fixture_reply("groq", "chat_ok"))

    result = ping(_gateway(make_gateway, _gemini(gemini), _groq(groq)))

    assert result.ok and result.provider == "gemini" and result.attempts == 2
    assert result.model == "gemini-3.5-flash-lite"
    assert (result.input_tokens, result.output_tokens) == (88, 11)
    assert clock.sleeps == [14.0]  # RetryInfo.retryDelay
    assert groq.requests == []
    first, second = log_rows(engine)
    assert (first.error_code, first.http_status) == ("rate_limited", 429)
    assert (second.success, second.attempt) == (True, 2)


def test_a_per_minute_429_with_a_long_delay_falls_back_at_once_and_comes_back_after_it(
    make_server: ServerFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    gemini = make_server(fixture_reply("gemini", "error_429_minute_long", status=429))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))

    result = ping(gateway)

    assert result.provider == "groq" and clock.sleeps == []  # 51 s > MAX_WAIT_S: no sleeping
    assert gateway.status()[0].cooldown_until == clock.now() + timedelta(seconds=51)
    assert ping(gateway).provider == "groq" and len(gemini.requests) == 1  # set aside

    clock.advance(52)
    ping(gateway)
    assert len(gemini.requests) == 2  # the window is over: Gemini is tried first again


@pytest.mark.parametrize(("delay", "waits"), [(14, True), (20, True), (21, False), (57, False)])
def test_what_the_policy_does_with_the_delays_reported_for_gemini(
    make_server: ServerFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
    delay: int,
    waits: bool,
) -> None:
    body = fixture_reply("gemini", "error_429_minute", status=429).body.replace("14s", f"{delay}s")
    gemini = make_server(
        Reply(status=429, body=body),
        fixture_reply("gemini", "generate_ok"),
    )
    groq = make_server(fixture_reply("groq", "chat_ok"))

    result = ping(_gateway(make_gateway, _gemini(gemini), _groq(groq)))

    assert MAX_WAIT_S == 20.0
    assert (result.provider, clock.sleeps) == (
        ("gemini", [float(delay)]) if waits else ("groq", [])
    )


def test_a_daily_quota_ignores_the_short_delay_and_cools_down_for_an_hour(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, clock: FakeClock
) -> None:
    gemini = make_server(fixture_reply("gemini", "error_429_day", status=429))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))

    result = ping(gateway)

    assert result.provider == "groq" and clock.sleeps == []  # no retry after "14s"
    rows = log_rows(engine)
    assert [(r.provider, r.error_code) for r in rows] == [
        ("gemini", "quota_exhausted"),
        ("groq", None),
    ]
    assert gateway.status()[0].cooldown_until == clock.now() + timedelta(hours=1)
    assert ping(gateway).provider == "groq" and len(gemini.requests) == 1

    clock.advance(3601)
    ping(gateway)
    assert len(gemini.requests) == 2  # probed again once the hour is over


def test_three_short_rate_limits_set_gemini_aside_for_a_minute(
    make_server: ServerFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    gemini = make_server(fixture_reply("gemini", "error_429_minute", status=429))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))

    assert ping(gateway).provider == "groq"
    assert len(gemini.requests) == 3 and clock.sleeps == [14.0, 14.0]  # 28 s of the 90 s budget
    assert gateway.status()[0].cooldown_until == clock.now() + timedelta(seconds=60)


def test_a_refused_key_is_ignored_until_reload(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    gemini = make_server(
        fixture_reply("gemini", "error_400_api_key_invalid", status=400),
        fixture_reply("gemini", "generate_ok"),
    )
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))

    assert ping(gateway).provider == "groq"
    status = gateway.status()[0]
    assert status.misconfigured and not status.available
    assert ping(gateway).provider == "groq" and len(gemini.requests) == 1

    gateway.reload()  # the owner fixed the key
    assert ping(gateway).provider == "gemini" and len(gemini.requests) == 2


@pytest.mark.parametrize("fixture", ["error_400_location", "error_400_free_tier"])
def test_a_region_or_free_tier_refusal_falls_back_and_is_reported_as_auth(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, fixture: str
) -> None:
    gemini = make_server(fixture_reply("gemini", fixture, status=400))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))

    assert ping(gateway).provider == "groq"
    [row, _] = log_rows(engine)
    assert (row.error_code, row.http_status) == ("auth", 400)
    assert gateway.status()[0].misconfigured


@pytest.mark.parametrize("fixture", ["generate_max_tokens", "generate_safety", "generate_empty"])
def test_an_unusable_answer_is_repaired_once_then_incomplete_without_fallback(
    make_server: ServerFactory, make_gateway: GatewayFactory, engine, fixture: str
) -> None:
    gemini = make_server(fixture_reply("gemini", fixture))
    groq = make_server(fixture_reply("groq", "chat_ok"))

    result = ping(_gateway(make_gateway, _gemini(gemini), _groq(groq)))

    assert result.status is AiStatus.INCOMPLETE and result.provider == "gemini"
    assert result.attempts == 2 and len(gemini.requests) == 2
    assert groq.requests == []  # blocked or truncated content never moves to another provider
    assert [r.error_code for r in log_rows(engine)] == ["invalid_output", "invalid_output"]
    repair = gemini.requests[1].json()["contents"][0]["parts"][0]["text"]
    assert "Your previous answer was rejected" in repair


def test_a_server_error_is_retried_then_falls_back(
    make_server: ServerFactory, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    gemini = make_server(fixture_reply("gemini", "error_503", status=503))
    groq = make_server(fixture_reply("groq", "chat_ok"))

    result = ping(_gateway(make_gateway, _gemini(gemini), _groq(groq)))

    assert result.provider == "groq" and len(gemini.requests) == 3
    assert clock.sleeps == [1.0, 2.0]  # the usual backoff


def test_a_refused_response_format_field_costs_one_fallback_then_the_older_fields_work(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    gemini = make_server(
        fixture_reply("gemini", "error_400_unknown_field", status=400),
        fixture_reply("gemini", "generate_ok"),
    )
    groq = make_server(fixture_reply("groq", "chat_ok"))
    provider = _gemini(gemini)
    gateway = _gateway(make_gateway, provider, _groq(groq))

    first = ping(gateway)
    assert first.provider == "groq" and provider.json_mode == JSON_MODE_LEGACY

    second = ping(gateway)  # a 400 is no cooldown: Gemini is tried again, with the older fields
    assert second.provider == "gemini" and second.ok
    assert "responseMimeType" in gemini.requests[1].json()["generationConfig"]


def test_pin_provider_reaches_gemini_alone(
    make_server: ServerFactory, make_gateway: GatewayFactory
) -> None:
    gemini = make_server(fixture_reply("gemini", "generate_ok"))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    gateway = _gateway(make_gateway, _gemini(gemini), _groq(groq))
    result = ping(gateway, pin_provider="gemini")
    assert result.provider == "gemini" and groq.requests == []
