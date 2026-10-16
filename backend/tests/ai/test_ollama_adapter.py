"""The Ollama adapter against a fake server on the loopback interface (no real Ollama)."""

import socket
from collections.abc import Callable

import pytest

from app.ai.providers.ollama import DEFAULT_MODEL, MIN_REQUEST_TIMEOUT_S, OllamaProvider
from app.ai.types import Capability, ErrorKind, ProviderError, TranscriptionRequest
from tests.ai.conftest import provider_request
from tests.ai.fake_server import FakeServer, Reply, fixture_reply

ServerFactory = Callable[..., FakeServer]


def _provider(server: FakeServer, model: str | None = None) -> OllamaProvider:
    return OllamaProvider(server.base_url, model)


def _error(provider: OllamaProvider, **kwargs: float) -> ProviderError:
    with pytest.raises(ProviderError) as caught:
        provider.generate_json(provider_request(**kwargs))
    return caught.value


# --- Request ----------------------------------------------------------------------------------


def test_request_is_a_non_streaming_native_chat_call(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_ok"))
    _provider(server).generate_json(provider_request(max_output_tokens=123, user="bonjour"))

    [received] = server.requests
    body = received.json()
    assert received.path == "/api/chat"
    assert body["stream"] is False  # Ollama streams by default
    assert body["model"] == DEFAULT_MODEL
    assert body["options"] == {"num_predict": 123, "temperature": 0}
    system, user = body["messages"]
    assert (system["role"], user["role"]) == ("system", "user")
    assert "connectivity probe" in system["content"]
    assert "matches this JSON Schema" in system["content"]  # the schema is also in the prompt
    assert "bonjour" in user["content"]
    # The schema sent as `format` is the simplified one: no titles, no defaults, closed objects.
    assert body["format"]["type"] == "object"
    assert body["format"]["required"] == ["ok", "echo"]
    assert body["format"]["additionalProperties"] is False
    assert "title" not in body["format"]
    assert received.headers["content-type"] == "application/json"
    assert received.headers["user-agent"].startswith("vocab-coach/")
    assert "authorization" not in received.headers  # no key at all


def test_non_ascii_text_travels_as_utf8(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_ok"))
    _provider(server).generate_json(provider_request(user="déjà vu — café ☕"))
    assert "déjà vu — café ☕" in server.requests[0].json()["messages"][1]["content"]


def test_model_override_and_default(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_ok"))
    provider = _provider(server, model="llama3.2:3b")
    provider.generate_json(provider_request())
    assert server.requests[0].json()["model"] == "llama3.2:3b"
    assert provider.model_for(Capability.TEXT) == "llama3.2:3b"
    assert OllamaProvider(server.base_url, "  ").model_for(Capability.TEXT) == DEFAULT_MODEL
    assert OllamaProvider(server.base_url).model_for(Capability.TEXT) == DEFAULT_MODEL


# --- Configuration ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", [None, "", "   ", "localhost:11434", "file:///etc/passwd", "ftp://x"]
)
def test_not_configured_without_a_usable_http_url(url: str | None) -> None:
    assert OllamaProvider(url).is_configured() is False


def test_configured_with_an_http_url_and_trailing_slash_is_ignored(
    make_server: ServerFactory,
) -> None:
    server = make_server(fixture_reply("ollama", "chat_ok"))
    provider = OllamaProvider(server.base_url + "/")
    assert provider.is_configured()
    provider.generate_json(provider_request())
    assert server.requests[0].path == "/api/chat"


def test_capabilities_and_timeout_floor() -> None:
    provider = OllamaProvider("http://127.0.0.1:11434")
    assert provider.capabilities == frozenset({Capability.TEXT})
    assert provider.min_request_timeout_s == MIN_REQUEST_TIMEOUT_S == 60.0
    with pytest.raises(ProviderError) as caught:
        provider.transcribe(TranscriptionRequest(audio=None, language="en", timeout_s=1))  # type: ignore[arg-type]
    assert caught.value.kind is ErrorKind.BAD_REQUEST


def test_repr_does_not_show_the_url() -> None:
    assert "11434" not in repr(OllamaProvider("http://user:secret@127.0.0.1:11434"))
    assert "secret" not in repr(OllamaProvider("http://user:secret@127.0.0.1:11434"))


def test_unconfigured_provider_refuses_to_call() -> None:
    assert _error(OllamaProvider(None)).kind is ErrorKind.BAD_REQUEST


# --- Valid answers ----------------------------------------------------------------------------


def test_valid_answer_with_tokens(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_ok"))
    response = _provider(server).generate_json(provider_request())
    assert response.text == '{"ok": true, "echo": "ping"}'
    assert response.model == "gemma3:4b"
    assert (response.input_tokens, response.output_tokens) == (57, 12)


def test_json_fence_is_removed(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_fenced"))
    response = _provider(server).generate_json(provider_request())
    assert response.text == '{"ok": true, "echo": "ping"}'


# --- Error translation (D-050) ----------------------------------------------------------------


def test_missing_model_tells_how_to_pull_it(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "error_model_not_found", status=404))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and error.status_code == 404
    assert "ollama pull gemma3:4b" in error.message


def test_other_404_points_at_the_base_url(make_server: ServerFactory) -> None:
    server = make_server(Reply(status=404, body="404 page not found"))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.BAD_REQUEST and "base URL" in error.message


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ErrorKind.BAD_REQUEST),
        (401, ErrorKind.AUTH),
        (403, ErrorKind.AUTH),
        (408, ErrorKind.TRANSIENT),
        (500, ErrorKind.TRANSIENT),
        (502, ErrorKind.TRANSIENT),
        (503, ErrorKind.TRANSIENT),
        (418, ErrorKind.BAD_REQUEST),
    ],
)
def test_status_classes(make_server: ServerFactory, status: int, kind: ErrorKind) -> None:
    server = make_server(fixture_reply("ollama", "error_generic", status=status))
    error = _error(_provider(server))
    assert (error.kind, error.status_code) == (kind, status)
    assert error.message == "the model failed to generate a response"


def test_429_keeps_retry_after(make_server: ServerFactory) -> None:
    server = make_server(
        fixture_reply("ollama", "error_generic", status=429, headers={"Retry-After": "7"})
    )
    error = _error(_provider(server))
    assert error.kind is ErrorKind.RATE_LIMITED and error.retry_after == 7.0


def test_truncated_answer_is_invalid_output(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_truncated"))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.INVALID_OUTPUT and "cut off" in error.message


def test_empty_answer_is_invalid_output(make_server: ServerFactory) -> None:
    server = make_server(fixture_reply("ollama", "chat_empty_thinking"))
    error = _error(_provider(server))
    assert error.kind is ErrorKind.INVALID_OUTPUT and "empty" in error.message


def test_a_server_that_is_not_ollama_is_a_bad_request(make_server: ServerFactory) -> None:
    server = make_server(Reply(body="<html>hello</html>"))
    assert _error(_provider(server)).kind is ErrorKind.BAD_REQUEST


def test_connection_refused_is_a_network_error() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]  # nothing listens here once the socket is closed
    error = _error(OllamaProvider(f"http://127.0.0.1:{port}"))
    assert error.kind is ErrorKind.NETWORK and "refused" in error.message
    assert str(port) not in error.message  # no address in messages


def test_timeout_is_transient(make_server: ServerFactory) -> None:
    server = make_server(Reply(body="{}", delay_s=1.0))
    error = _error(_provider(server), timeout_s=0.2)
    assert error.kind is ErrorKind.TRANSIENT and "timed out" in error.message


def test_a_dropped_connection_is_a_network_error(make_server: ServerFactory) -> None:
    server = make_server(Reply(drop=True))
    assert _error(_provider(server)).kind is ErrorKind.NETWORK
