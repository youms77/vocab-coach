"""Chat-completions client for OpenAI-compatible services (D-047).

Groq is the only user today; a later provider (OpenRouter, a local gateway...) is a small subclass
that sets its name, base URL and default model and overrides the few hooks below. Ollama does not
use it: its native API documents what the OpenAI-compatible one does not (D-048).

The key goes in the `Authorization` header only. Every message that leaves an adapter is built from
the service's own `error.message` or from fixed text, then passes through `mask_secrets`.
"""

import json
from collections.abc import Mapping
from typing import Any

from app.ai.http import HttpResponse, post
from app.ai.providers.common import as_int, parse_retry_after, strip_json_fence
from app.ai.redact import clean_message
from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)

MESSAGE_LIMIT = 300  # characters kept of a provider error message (the gateway cuts them again)


class OpenAICompatibleProvider:
    name: str = "openai-compatible"
    capabilities: frozenset[Capability] = frozenset({Capability.TEXT})
    # Shown in messages ("Groq rejected the API key"); defaults to the provider name.
    label: str = ""

    def __init__(self, api_key: str | None, *, base_url: str, text_model: str) -> None:
        self._api_key = (api_key or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._text_model = text_model

    def __repr__(self) -> str:  # never the key
        return (
            f"{type(self).__name__}(model={self._text_model!r}, configured={self.is_configured()})"
        )

    @property
    def _label(self) -> str:
        return self.label or self.name

    def is_configured(self) -> bool:
        return self._api_key is not None

    def model_for(self, capability: Capability) -> str:
        return self._text_model

    # --- Hooks for subclasses ---------------------------------------------------------------

    def response_format(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """The `response_format` field: the service's way of asking for JSON."""
        return {"type": "json_object"}

    def system_text(self, request: ProviderRequest) -> str:
        return request.system

    def extra_body(self) -> dict[str, Any]:
        """Further model-specific fields (reasoning controls...)."""
        return {}

    def token_headroom(self) -> int:
        """Tokens added to the task's output limit for hidden reasoning that counts against it."""
        return 0

    # --- Request ----------------------------------------------------------------------------

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        body = {
            "model": self._text_model,
            "messages": [
                {"role": "system", "content": self.system_text(request)},
                {"role": "user", "content": request.user},
            ],
            "temperature": 0,
            "max_completion_tokens": request.max_output_tokens + self.token_headroom(),
            "response_format": self.response_format(request.json_schema),
            **self.extra_body(),
        }
        response = post(
            f"{self._base_url}/chat/completions",
            headers=self._headers("application/json"),
            body=_dumps(body),
            timeout_s=request.timeout_s,
        )
        if response.status != 200:
            raise self.translate_error(response)
        return self.parse_completion(response)

    def _headers(self, content_type: str) -> dict[str, str]:
        if self._api_key is None:
            raise ProviderError(ErrorKind.AUTH, f"no API key is configured for {self._label}")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
        }

    # --- Answers ----------------------------------------------------------------------------

    def parse_completion(self, response: HttpResponse) -> ProviderResponse:
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError(
                ErrorKind.BAD_REQUEST, f"the answer of {self._label} has no completion"
            )
        choice = choices[0]
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        model = data.get("model") if isinstance(data.get("model"), str) else self._text_model
        finish = choice.get("finish_reason")
        if finish == "length":
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT, "the answer was cut off (the token limit was reached)"
            )
        if finish == "content_filter":
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT, "the answer was blocked by a content filter"
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the model returned an empty answer")
        return ProviderResponse(
            text=strip_json_fence(content),
            model=model,
            input_tokens=as_int(usage.get("prompt_tokens")),
            output_tokens=as_int(usage.get("completion_tokens")),
        )

    def translate_error(self, response: HttpResponse) -> ProviderError:
        """Generic mapping of an HTTP error status (D-050); subclasses refine it."""
        status = response.status
        detail = self.error_detail(response)
        retry_after = parse_retry_after(response.header("retry-after"))
        if status in (401, 403):
            kind = ErrorKind.AUTH
            detail = f"{self._label} rejected the API key or the request is not permitted: {detail}"
        elif status == 429:
            kind = ErrorKind.RATE_LIMITED
        elif status == 408 or status >= 500:
            kind = ErrorKind.TRANSIENT
        else:
            kind = ErrorKind.BAD_REQUEST
        return ProviderError(kind, detail, retry_after=retry_after, status_code=status)

    def error_detail(self, response: HttpResponse) -> str:
        """The service's `error.message`, masked and cut; `HTTP <status>` when there is none."""
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        text = error.get("message") if isinstance(error, dict) else None
        if not isinstance(text, str) or not text.strip():
            return f"HTTP {response.status}"
        return self.mask(text)

    def mask(self, text: str) -> str:
        secrets = [self._api_key] if self._api_key else []
        return clean_message(text, secrets, MESSAGE_LIMIT)


def _dumps(body: Mapping[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")
