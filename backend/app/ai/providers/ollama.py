"""Ollama adapter: a local model server, native `/api/chat` API (D-048).

Native rather than the OpenAI-compatible `/v1`: only the native API documents the `format` field
(a JSON Schema), `options.num_predict` and the `{"error": "..."}` error body. `stream` defaults to
true in Ollama, so every request sets `stream: false`.

"Configured" means a base URL is set (`VOCAB_OLLAMA_BASE_URL`); there is no key. The first request
after a pause can be slow while the server loads the model, hence `min_request_timeout_s`.
"""

import json
from typing import Any
from urllib.parse import urlsplit

from app.ai.http import HttpResponse, post
from app.ai.providers.common import as_int, parse_retry_after, strip_json_fence
from app.ai.providers.schema import SchemaConversionError, schema_instruction, to_ollama_schema
from app.ai.redact import clean_message
from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    TranscriptionRequest,
)

DEFAULT_MODEL = "gemma3:4b"  # small, not a "thinking" model (those spend num_predict on reasoning)
MIN_REQUEST_TIMEOUT_S = 60.0  # loading a model into memory can take a while (D-048)
_MESSAGE_LIMIT = 300


class OllamaProvider:
    name = "ollama"
    capabilities = frozenset({Capability.TEXT})
    min_request_timeout_s = MIN_REQUEST_TIMEOUT_S

    def __init__(self, base_url: str | None, model: str | None = None) -> None:
        self._base_url = _normalize(base_url)
        self._model = (model or "").strip() or DEFAULT_MODEL

    @classmethod
    def from_settings(cls, settings: Any) -> "OllamaProvider":
        return cls(settings.ollama_base_url, settings.ollama_model)

    def __repr__(self) -> str:
        return f"OllamaProvider(model={self._model!r}, configured={self.is_configured()})"

    def is_configured(self) -> bool:
        return self._base_url is not None

    def model_for(self, capability: Capability) -> str:
        return self._model

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
        raise ProviderError(ErrorKind.BAD_REQUEST, "Ollama does not transcribe speech")

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        if self._base_url is None:
            raise ProviderError(ErrorKind.BAD_REQUEST, "Ollama is not configured")
        try:
            schema = to_ollama_schema(request.json_schema)
            instruction = schema_instruction(request.json_schema)
        except SchemaConversionError as exc:
            raise ProviderError(
                ErrorKind.BAD_REQUEST, f"unsupported output schema: {exc}"
            ) from None
        body = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": f"{request.system}\n\n{instruction}"},
                {"role": "user", "content": request.user},
            ],
            "format": schema,
            "options": {"num_predict": request.max_output_tokens, "temperature": 0},
        }
        response = post(
            f"{self._base_url}/api/chat",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            timeout_s=request.timeout_s,
        )
        if response.status != 200:
            raise self._error_for(response)
        return self._parse(response)

    # --- Answers ---------------------------------------------------------------------------

    def _parse(self, response: HttpResponse) -> ProviderResponse:
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderError(
                ErrorKind.BAD_REQUEST, "the server did not answer like Ollama (not JSON)"
            )
        if "error" in data:
            raise ProviderError(ErrorKind.BAD_REQUEST, _provider_message(data, "Ollama error"))
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        usage = {
            "input_tokens": as_int(data.get("prompt_eval_count")),
            "output_tokens": as_int(data.get("eval_count")),
        }
        model = data.get("model") if isinstance(data.get("model"), str) else self._model
        if data.get("done_reason") == "length":
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT, "the answer was cut off (the token limit was reached)"
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                "the model returned an empty answer (a reasoning model may have spent its "
                "token budget thinking)",
            )
        return ProviderResponse(text=strip_json_fence(content), model=model, **usage)

    def _error_for(self, response: HttpResponse) -> ProviderError:
        """Translate an HTTP error (D-050): the table in DECISIONS.md is the reference."""
        status = response.status
        data = response.json()
        detail = _provider_message(data, f"HTTP {status}")
        retry_after = parse_retry_after(response.header("retry-after"))
        if status == 404:
            lowered = detail.lower()
            if "model" in lowered and "not found" in lowered:
                detail = (
                    f"model {self._model!r} is not installed on the Ollama server: "
                    f"run `ollama pull {self._model}`"
                )
            else:
                detail = f"Ollama answered 404 ({detail}); is the base URL right?"
            kind = ErrorKind.BAD_REQUEST
        elif status == 429:
            kind = ErrorKind.RATE_LIMITED
        elif status in (401, 403):
            kind = ErrorKind.AUTH
        elif status == 408 or status >= 500:
            kind = ErrorKind.TRANSIENT
        else:
            kind = ErrorKind.BAD_REQUEST
        return ProviderError(kind, detail, retry_after=retry_after, status_code=status)


def _normalize(base_url: str | None) -> str | None:
    """The base URL without a trailing slash, or None when unset or not an http(s) URL."""
    if base_url is None:
        return None
    text = base_url.strip().rstrip("/")
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return text


def _provider_message(data: Any, fallback: str) -> str:
    """The server's own `{"error": "..."}` text, cut to a log-sized message."""
    text = data.get("error") if isinstance(data, dict) else None
    return clean_message(text, (), _MESSAGE_LIMIT) if isinstance(text, str) and text else fallback
