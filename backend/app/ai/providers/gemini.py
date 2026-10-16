"""Gemini adapter: `generateContent` (v1beta), text only (D-055 to D-059).

Facts checked in the official documentation on 2026-10-16 (D-056):
- `POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`, the key in
  the `x-goog-api-key` header (never in the URL);
- default model `gemini-3.5-flash-lite` (stable, free of charge; on the free tier the content may
  be used to improve Google's products);
- structured output: `generationConfig.responseFormat.text = {mimeType: "APPLICATION_JSON",
  schema}`; the older `responseMimeType` + `responseJsonSchema` are marked deprecated;
- `maxOutputTokens` includes the thinking tokens; `thinkingLevel` exists on Gemini 3 and later and
  is an error on older models;
- the error body of `generateContent` is not documented (only the Interactions API's is): both
  shapes are read. To be confirmed by the owner's first real call.

The one risk is that the real service does not accept `responseFormat`: the JSON fields live in
one function (`json_generation_fields`), with the older fields as a fallback the adapter switches
to by itself after a 400 that names the rejected field.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.ai.http import HttpResponse, post
from app.ai.providers.common import as_int, parse_retry_after, strip_json_fence
from app.ai.providers.schema import SchemaConversionError, to_gemini_schema
from app.ai.redact import clean_message
from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    TranscriptionRequest,
)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.5-flash-lite"  # the cheapest stable model of the free tier

# `maxOutputTokens` includes the thinking tokens: leave room so a thought cannot eat the answer.
THINKING_HEADROOM_TOKENS = 512
# Models whose thinking level is documented, with the lowest level each accepts. `thinkingLevel`
# is an error on older models and its levels are undocumented for others (`gemini-3.1-flash-lite`),
# so any model not listed gets no `thinkingConfig` at all.
THINKING_LEVELS = {
    "gemini-3.5-flash-lite": "MINIMAL",
    "gemini-3.6-flash": "MINIMAL",
    "gemini-3.8-flash": "LOW",  # no "minimal" on this model
}

JSON_MODE_RESPONSE_FORMAT = "response_format"
JSON_MODE_LEGACY = "legacy"

MESSAGE_LIMIT = 300  # characters kept of a provider error message (the gateway cuts them again)
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # goes into the URL path

_API_KEY_REFUSED = re.compile(
    r"api key (?:not valid|is not valid|expired|invalid|was reported as leaked)"
    r"|invalid api key|reported as leaked",
    re.IGNORECASE,
)
_REGION_OR_TIER = re.compile(
    r"location is not supported|not available in your (?:country|region)|free tier",
    re.IGNORECASE,
)
_UNKNOWN_FIELD = re.compile(r"unknown name|cannot find field", re.IGNORECASE)
_RESPONSE_FORMAT_FIELD = re.compile(r"response_?format", re.IGNORECASE)
_DAILY_WORDING = re.compile(r"per day|perday|daily", re.IGNORECASE)
_RETRY_IN = re.compile(r"retry in ([0-9hms.]+)", re.IGNORECASE)
_FINISH_REASON = re.compile(r"^[A-Z_]{2,40}$")


def json_generation_fields(schema: Mapping[str, Any], mode: str) -> dict[str, Any]:
    """The `generationConfig` fields that ask for JSON matching `schema` (risk n° 1, D-058).

    This is the only place that knows how Gemini is asked for structured output; both forms are
    tested offline, neither has been exercised against the real service yet.
    """
    converted = to_gemini_schema(schema)
    if mode == JSON_MODE_LEGACY:
        return {"responseMimeType": "application/json", "responseJsonSchema": converted}
    return {"responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": converted}}}


class GeminiProvider:
    name = "gemini"
    capabilities = frozenset({Capability.TEXT})

    def __init__(
        self,
        api_key: str | None,
        model: str | None = None,
        *,
        base_url: str = BASE_URL,
        json_mode: str = JSON_MODE_RESPONSE_FORMAT,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        name = (model or "").strip().removeprefix("models/")
        self._model = name or DEFAULT_MODEL
        self._base_url = base_url.rstrip("/")
        self._json_mode = json_mode

    @classmethod
    def from_settings(cls, settings: Any) -> "GeminiProvider":
        key = settings.gemini_api_key
        return cls(key.get_secret_value() if key is not None else None, settings.gemini_model)

    def __repr__(self) -> str:  # never the key
        return f"GeminiProvider(model={self._model!r}, configured={self.is_configured()})"

    def is_configured(self) -> bool:
        return self._api_key is not None

    def model_for(self, capability: Capability) -> str:
        return self._model

    @property
    def json_mode(self) -> str:
        return self._json_mode

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
        raise ProviderError(ErrorKind.BAD_REQUEST, "Gemini does not transcribe speech here")

    # --- Request ----------------------------------------------------------------------------

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        if self._api_key is None:
            raise ProviderError(ErrorKind.AUTH, "no API key is configured for Gemini")
        if not _MODEL_NAME.match(self._model):
            raise ProviderError(
                ErrorKind.BAD_REQUEST, "VOCAB_GEMINI_MODEL is not a valid model name"
            )
        mode = self._json_mode
        try:
            json_fields = json_generation_fields(request.json_schema, mode)
        except SchemaConversionError as exc:
            raise ProviderError(
                ErrorKind.BAD_REQUEST, f"unsupported output schema: {exc}"
            ) from None
        response = post(
            f"{self._base_url}/models/{self._model}:generateContent",
            headers={
                "x-goog-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body=json.dumps(self._body(request, json_fields), ensure_ascii=False).encode("utf-8"),
            timeout_s=request.timeout_s,
        )
        if response.status != 200:
            raise self._error_after(response, mode)
        return self._parse(response)

    def _body(self, request: ProviderRequest, json_fields: Mapping[str, Any]) -> dict[str, Any]:
        config: dict[str, Any] = {
            "maxOutputTokens": request.max_output_tokens + THINKING_HEADROOM_TOKENS,
            **json_fields,
        }
        level = THINKING_LEVELS.get(self._model)
        if level is not None:
            config["thinkingConfig"] = {"thinkingLevel": level}
        return {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": config,
        }

    # --- Answers ----------------------------------------------------------------------------

    def _parse(self, response: HttpResponse) -> ProviderResponse:
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderError(
                ErrorKind.BAD_REQUEST, "the server did not answer like Gemini (not JSON)"
            )
        if "error" in data:
            raise ProviderError(ErrorKind.BAD_REQUEST, self._mask(_parse_error(data).message))
        candidates = data.get("candidates")
        candidate = candidates[0] if isinstance(candidates, list) and candidates else None
        if not isinstance(candidate, dict):
            raise ProviderError(ErrorKind.INVALID_OUTPUT, _no_candidate_message(data))
        finish = candidate.get("finishReason")
        if finish == "MAX_TOKENS":
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT, "the answer was cut off (the token limit was reached)"
            )
        if isinstance(finish, str) and finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            reason = finish if _FINISH_REASON.match(finish) else "unknown reason"
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT, f"the answer was stopped by the model ({reason})"
            )
        text = _answer_text(candidate)
        if not text.strip():
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the model returned an empty answer")
        usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
        answered = as_int(usage.get("candidatesTokenCount"))
        thought = as_int(usage.get("thoughtsTokenCount"))
        output = None if answered is None and thought is None else (answered or 0) + (thought or 0)
        version = data.get("modelVersion")
        return ProviderResponse(
            text=strip_json_fence(text),
            model=version if isinstance(version, str) and version else self._model,
            input_tokens=as_int(usage.get("promptTokenCount")),
            output_tokens=output,
        )

    # --- Errors (D-050, D-059) --------------------------------------------------------------

    def _error_after(self, response: HttpResponse, mode: str) -> ProviderError:
        """Translate the error and, when Google rejects the `responseFormat` field, remember to
        use the older JSON fields from the next request on (the gateway falls back this time)."""
        info = _parse_error(response.json())
        error = self._translate(response, info)
        if (
            response.status == 400
            and mode == JSON_MODE_RESPONSE_FORMAT
            and _UNKNOWN_FIELD.search(info.message)
            and _RESPONSE_FORMAT_FIELD.search(info.message)
        ):
            self._json_mode = JSON_MODE_LEGACY
            error = ProviderError(
                error.kind,
                f"{error.message} (the `responseFormat` field was refused: the next requests "
                "use `responseMimeType` and `responseJsonSchema`)",
                status_code=error.status_code,
            )
        return error

    def translate_error(self, response: HttpResponse) -> ProviderError:
        return self._translate(response, _parse_error(response.json()))

    def _translate(self, response: HttpResponse, info: "_ErrorInfo") -> ProviderError:
        status = response.status
        detail = self._mask(info.message) if info.message else f"HTTP {status}"
        header_delay = parse_retry_after(response.header("retry-after"))
        if status == 429:
            return self._rate_limit(info, detail, header_delay)
        if status == 402:  # prepaid credit depleted (Interactions `payment_required`)
            return ProviderError(ErrorKind.QUOTA_EXHAUSTED, detail, status_code=status)
        if status in (401, 403):
            return ProviderError(
                ErrorKind.AUTH,
                f"Gemini rejected the API key or the request is not permitted: {detail}",
                status_code=status,
            )
        if status == 400:
            return self._bad_request(info, detail)
        if status == 404:
            return ProviderError(
                ErrorKind.BAD_REQUEST,
                f"model or path not found on Gemini ({detail}); check VOCAB_GEMINI_MODEL",
                status_code=status,
            )
        if status in (408, 499) or status >= 500:
            return ProviderError(
                ErrorKind.TRANSIENT, detail, retry_after=header_delay, status_code=status
            )
        return ProviderError(ErrorKind.BAD_REQUEST, detail, status_code=status)

    def _rate_limit(
        self, info: "_ErrorInfo", detail: str, header_delay: float | None
    ) -> ProviderError:
        if info.is_daily:
            # `retryDelay` is short even for a daily quota (seconds, reported by users): a retry
            # would fail again, so it is ignored and the cooldown is the default hour (D-050).
            return ProviderError(ErrorKind.QUOTA_EXHAUSTED, detail, status_code=429)
        retry_after = info.retry_delay
        if retry_after is None:
            retry_after = header_delay
        if retry_after is None:
            match = _RETRY_IN.search(info.message)
            retry_after = parse_retry_after(match.group(1).rstrip(".")) if match else None
        return ProviderError(
            ErrorKind.RATE_LIMITED, detail, retry_after=retry_after, status_code=429
        )

    def _bad_request(self, info: "_ErrorInfo", detail: str) -> ProviderError:
        """A 400 can mean "invalid key" or "region not supported": read it before classifying."""
        refused = (
            "API_KEY_INVALID" in info.reasons
            or info.status in ("UNAUTHENTICATED", "PERMISSION_DENIED")
            or info.code_name == "authentication"
            or bool(_API_KEY_REFUSED.search(info.message))
        )
        if refused:
            return ProviderError(
                ErrorKind.AUTH, f"Gemini rejected the API key: {detail}", status_code=400
            )
        precondition = (
            info.status == "FAILED_PRECONDITION" or info.code_name == "failed_precondition"
        )
        if precondition and _REGION_OR_TIER.search(info.message):
            return ProviderError(
                ErrorKind.AUTH,
                "Gemini cannot be used with this key from here (region not supported, or the "
                f"free tier is not available in this country): {detail}",
                status_code=400,
            )
        return ProviderError(ErrorKind.BAD_REQUEST, detail, status_code=400)

    def _mask(self, text: str) -> str:
        return clean_message(text, [self._api_key] if self._api_key else [], MESSAGE_LIMIT)


@dataclass(frozen=True)
class _ErrorInfo:
    """What an error body says, whichever of the two documented shapes it has."""

    message: str = ""
    status: str | None = None  # classic gRPC-style name: RESOURCE_EXHAUSTED, INVALID_ARGUMENT...
    code_name: str | None = None  # Interactions-style snake_case code: quota_exceeded...
    reasons: tuple[str, ...] = ()  # ErrorInfo.reason: API_KEY_INVALID...
    quota_ids: tuple[str, ...] = field(default=())  # QuotaFailure.violations[].quotaId
    retry_delay: float | None = None  # RetryInfo.retryDelay, in seconds

    @property
    def is_daily(self) -> bool:
        if self.code_name == "quota_exceeded":
            return True
        return any(_DAILY_WORDING.search(quota) for quota in self.quota_ids) or bool(
            _DAILY_WORDING.search(self.message)
        )


def _parse_error(data: Any) -> _ErrorInfo:
    """Read `{"error": {...}}` in the classic shape (`code` is the HTTP status, `status` a name,
    `details[]` typed messages) and in the Interactions shape (`code` is a snake_case string)."""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return _ErrorInfo()
    message = error.get("message")
    code = error.get("code")
    status = error.get("status")
    reasons: list[str] = []
    quota_ids: list[str] = []
    retry_delay: float | None = None
    details = error.get("details")
    for item in details if isinstance(details, list) else []:
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        if isinstance(reason, str):
            reasons.append(reason)
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            limit = metadata.get("quota_limit")
            if isinstance(limit, str):
                quota_ids.append(limit)
        violations = item.get("violations")
        for violation in violations if isinstance(violations, list) else []:
            quota_id = violation.get("quotaId") if isinstance(violation, dict) else None
            if isinstance(quota_id, str):
                quota_ids.append(quota_id)
        if retry_delay is None and "retryDelay" in item:
            retry_delay = parse_retry_after(item.get("retryDelay"))
    return _ErrorInfo(
        message=message if isinstance(message, str) else "",
        status=status if isinstance(status, str) else None,
        code_name=code if isinstance(code, str) else None,
        reasons=tuple(reasons),
        quota_ids=tuple(quota_ids),
        retry_delay=retry_delay,
    )


def _answer_text(candidate: Mapping[str, Any]) -> str:
    """The answer parts joined, the model's thoughts (`thought: true`) left out."""
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    texts = [
        part["text"]
        for part in (parts if isinstance(parts, list) else [])
        if isinstance(part, dict)
        and isinstance(part.get("text"), str)
        and part.get("thought") is not True
    ]
    return "".join(texts)


def _no_candidate_message(data: Mapping[str, Any]) -> str:
    feedback = data.get("promptFeedback")
    reason = feedback.get("blockReason") if isinstance(feedback, dict) else None
    if isinstance(reason, str) and _FINISH_REASON.match(reason):
        return f"the prompt was blocked by Gemini ({reason})"
    return "Gemini returned no answer"
