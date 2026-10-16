"""The API key never leaves the adapter: not in an error, a repr, a log, the database, a trace.

Some services (and some libraries) copy the request back into their error message: URL, headers,
body. Here a hostile fake server does exactly that, with the key in every encoding, and we look for
the key everywhere it could end up.
"""

import json
import logging
import traceback
from collections.abc import Callable
from urllib.parse import quote, quote_plus

import pytest

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.types import ProviderError
from app.config import Settings
from app.db.models import AICallLog
from tests.ai.conftest import log_rows, ping, provider_request
from tests.ai.fake_server import FakeServer, Received, Reply

ServerFactory = Callable[..., FakeServer]
GatewayFactory = Callable[..., Gateway]

# Characters that are written differently once URL-encoded or form-encoded.
KEY = "gsk_test_a+b/c=d_0123456789"
VARIANTS = (KEY, quote(KEY, safe=""), quote_plus(KEY))


def _leaks(text: str) -> list[str]:
    return [variant for variant in VARIANTS if variant in text]


def _echo(status: int) -> Callable[[Received], Reply]:
    """A server that repeats the credential, in every encoding, in its error message."""

    def handler(received: Received) -> Reply:
        message = (
            f"bad credentials {received.headers.get('authorization')} sent to {received.path}; "
            f"raw={KEY} url={quote(KEY, safe='')} form={quote_plus(KEY)} "
            f"headers={json.dumps(received.headers)}"
        )
        return Reply(status=status, body={"error": {"message": message}})

    return handler


def _provider(server: FakeServer) -> GroqProvider:
    return GroqProvider(KEY, base_url=server.base_url)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 429, 498, 500, 503, 418])
def test_adapter_messages_never_contain_the_key(make_server: ServerFactory, status: int) -> None:
    server = make_server(handler=_echo(status))
    with pytest.raises(ProviderError) as caught:
        _provider(server).generate_json(provider_request())

    error = caught.value
    for text in (error.message, str(error), repr(error), repr(error.args)):
        assert _leaks(text) == [], (status, text)
    assert "***" in error.message  # the service's own text is kept, the key in it is masked


def test_the_hostile_server_really_does_repeat_the_key(make_server: ServerFactory) -> None:
    """Guard for the test above: without masking, the key would be in the answer."""
    from app.ai.http import post

    server = make_server(handler=_echo(401))
    # What the adapter has to hide: the raw answer does contain the key, in several encodings.
    raw = post(
        server.base_url + "/x", headers={"Authorization": f"Bearer {KEY}"}, body=b"{}", timeout_s=5
    ).body.decode()
    assert len(_leaks(raw)) >= 2


def test_the_key_is_only_ever_sent_in_the_authorization_header(make_server: ServerFactory) -> None:
    server = make_server(handler=_echo(401))
    with pytest.raises(ProviderError):
        _provider(server).generate_json(provider_request())
    [received] = server.requests
    assert received.headers["authorization"] == f"Bearer {KEY}"
    assert _leaks(received.path) == [] and _leaks(received.body.decode()) == []
    others = {k: v for k, v in received.headers.items() if k != "authorization"}
    assert _leaks(json.dumps(others)) == []


def test_gateway_result_log_and_database_stay_clean(
    make_server: ServerFactory,
    make_gateway: GatewayFactory,
    engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)  # everything, every logger
    groq = make_server(handler=_echo(401))
    ollama = make_server(Reply(status=404, body={"error": f"model {KEY} not found"}))
    gateway = make_gateway(_provider(groq), OllamaProvider(ollama.base_url), secrets=[KEY])

    result = ping(gateway)

    assert _leaks(result.detail or "") == []
    assert _leaks(caplog.text) == []
    for row in log_rows(engine):
        texts = [str(getattr(row, column.name)) for column in AICallLog.__table__.columns]
        assert _leaks(" | ".join(texts)) == []
    for status in gateway.status():
        assert _leaks(repr(status)) == []


def test_reprs_and_attributes_hide_the_key() -> None:
    provider = GroqProvider(KEY)
    for text in (repr(provider), str(provider), repr([provider]), repr({"groq": provider})):
        assert _leaks(text) == []
    settings = Settings(_env_file=None, groq_api_key=KEY)
    assert _leaks(repr(settings)) == [] and _leaks(str(settings)) == []
    built = build_providers(settings)
    assert _leaks(repr(built)) == []


def test_network_failures_say_nothing_about_the_address(make_server: ServerFactory) -> None:
    server = make_server(Reply(drop=True))
    with pytest.raises(ProviderError) as caught:
        _provider(server).generate_json(provider_request())
    error = caught.value
    port = server.base_url.rsplit(":", 1)[1]
    assert port not in error.message and "127.0.0.1" not in error.message
    assert error.__cause__ is None and error.__suppress_context__
    assert _leaks("".join(traceback.format_exception(error))) == []


def test_a_bad_url_is_refused_without_a_request_and_without_echoing_it() -> None:
    provider = GroqProvider(KEY, base_url="file:///C:/secret.txt")
    with pytest.raises(ProviderError) as caught:
        provider.generate_json(provider_request())
    assert "secret.txt" not in caught.value.message


# --- Gemini: the key travels in `x-goog-api-key` (D-049, D-057) -------------------------------

GEMINI_KEY = "AIzaSy_a+b/c=d_0123456789"
GEMINI_VARIANTS = (GEMINI_KEY, quote(GEMINI_KEY, safe=""), quote_plus(GEMINI_KEY))


def _gemini_leaks(text: str) -> list[str]:
    return [variant for variant in GEMINI_VARIANTS if variant in text]


def _gemini_echo(status: int, *, classic: bool = True) -> Callable[[Received], Reply]:
    def handler(received: Received) -> Reply:
        message = (
            f"bad credentials {received.headers.get('x-goog-api-key')} sent to {received.path}; "
            f"raw={GEMINI_KEY} url={quote(GEMINI_KEY, safe='')} form={quote_plus(GEMINI_KEY)} "
            f"headers={json.dumps(received.headers)}"
        )
        error = (
            {"code": status, "status": "INVALID_ARGUMENT", "message": message}
            if classic
            else {"code": "invalid_request", "message": message}
        )
        return Reply(status=status, body={"error": error})

    return handler


def _gemini(server: FakeServer) -> GeminiProvider:
    return GeminiProvider(GEMINI_KEY, base_url=server.base_url + "/v1beta")


@pytest.mark.parametrize("classic", [True, False])
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503, 418])
def test_gemini_messages_never_contain_the_key(
    make_server: ServerFactory, status: int, classic: bool
) -> None:
    server = make_server(handler=_gemini_echo(status, classic=classic))
    with pytest.raises(ProviderError) as caught:
        _gemini(server).generate_json(provider_request())

    error = caught.value
    for text in (error.message, str(error), repr(error), repr(error.args)):
        assert _gemini_leaks(text) == [], (status, text)
    assert "***" in error.message


def test_gemini_key_is_only_ever_sent_in_its_header(make_server: ServerFactory) -> None:
    server = make_server(handler=_gemini_echo(400))
    with pytest.raises(ProviderError):
        _gemini(server).generate_json(provider_request())
    [received] = server.requests
    assert received.headers["x-goog-api-key"] == GEMINI_KEY
    assert _gemini_leaks(received.path) == [] and _gemini_leaks(received.body.decode()) == []
    others = {k: v for k, v in received.headers.items() if k != "x-goog-api-key"}
    assert _gemini_leaks(json.dumps(others)) == []
    assert "?" not in received.path  # no `?key=` query string, ever


def test_gemini_gateway_result_log_and_database_stay_clean(
    make_server: ServerFactory,
    make_gateway: GatewayFactory,
    engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    gemini = make_server(handler=_gemini_echo(400))
    groq = make_server(handler=_echo(401))
    gateway = make_gateway(_gemini(gemini), _provider(groq), secrets=[GEMINI_KEY, KEY])

    result = ping(gateway)

    assert _gemini_leaks(result.detail or "") == [] and _leaks(result.detail or "") == []
    assert _gemini_leaks(caplog.text) == [] and _leaks(caplog.text) == []
    for row in log_rows(engine):
        texts = " | ".join(str(getattr(row, column.name)) for column in AICallLog.__table__.columns)
        assert _gemini_leaks(texts) == [] and _leaks(texts) == []
    for status in gateway.status():
        assert _gemini_leaks(repr(status)) == []


def test_gemini_reprs_and_settings_hide_the_key() -> None:
    provider = GeminiProvider(GEMINI_KEY)
    for text in (repr(provider), str(provider), repr([provider]), repr({"gemini": provider})):
        assert _gemini_leaks(text) == []
    settings = Settings(_env_file=None, gemini_api_key=GEMINI_KEY)
    assert _gemini_leaks(repr(settings)) == [] and _gemini_leaks(str(settings)) == []
    assert _gemini_leaks(repr(build_providers(settings))) == []
    assert GEMINI_KEY in settings.secret_values()  # so that the gateway masks it too


def test_gemini_network_failures_say_nothing_about_the_address(make_server: ServerFactory) -> None:
    server = make_server(Reply(drop=True))
    with pytest.raises(ProviderError) as caught:
        _gemini(server).generate_json(provider_request())
    error = caught.value
    assert server.base_url.rsplit(":", 1)[1] not in error.message
    assert error.__cause__ is None and error.__suppress_context__
    assert _gemini_leaks("".join(traceback.format_exception(error))) == []


def test_gemini_bad_url_is_refused_without_echoing_it() -> None:
    with pytest.raises(ProviderError) as caught:
        GeminiProvider(GEMINI_KEY, base_url="file:///C:/secret.txt").generate_json(
            provider_request()
        )
    assert "secret.txt" not in caught.value.message
