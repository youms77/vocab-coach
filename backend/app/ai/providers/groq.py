"""Groq adapter: text through the OpenAI-compatible API, and Whisper transcription (D-047).

Facts checked in the official documentation on 2026-10-16 (sources in D-046 / D-047):
- base URL `https://api.groq.com/openai/v1`; key in `Authorization: Bearer`;
- free plan, `openai/gpt-oss-20b`: 30 requests/minute, 1 000/day, 8 000 tokens/minute, 200 000/day;
  Whisper: 20 requests/minute, 2 000/day, 7 200 audio seconds/hour, 28 800/day; audio up to 25 MB;
- `json_schema` response format on a short list of models, `json_object` on the others (the prompt
  must then mention JSON); a `retry-after` header (seconds) on every 429.
The documentation does not say how a 429 body tells a per-minute limit from a per-day one: the
adapter reads the wording of the message ("per day", "(RPD)", "(TPD)", "(ASD)"). A wrong guess is
harmless: the gateway falls back on a long `retry_after` and sets the provider aside anyway.

Checked again on 2026-10-18 (D-171): the Whisper free limits above are unchanged (rate-limits page,
"Free Plan Limits"; 25 MB on the speech-to-text page). Transcriptions ask for `verbose_json`: the
API reference (`CreateTranscriptionResponseVerboseJson`) requires `language`, `duration` (typed as
a string, "the duration of the input audio") and `text`; each of `segments[]` requires `id`, `seek`,
`start`, `end`, `text` and `tokens`, `no_speech_prob` and `avg_logprob` being optional. It was never
called live before M6.a1, so the reading is tolerant: `duration` as a string or a number, malformed
segments ignored, only `text` required.
"""

import re
from pathlib import Path
from typing import Any

from app.ai.http import encode_multipart, post
from app.ai.providers.common import as_number, parse_retry_after, retry_after_from_message
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.ai.providers.schema import SchemaConversionError, schema_instruction, to_groq_schema
from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    SpeechSegment,
    TranscriptionDetails,
    TranscriptionRequest,
)

BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_TEXT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3"  # the more accurate of the two Whisper models

# Models documented for the `json_schema` response format; the others only get `json_object`.
STRUCTURED_OUTPUT_MODELS = frozenset(
    {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "meta-models/muse-spark-open"}
)
REASONING_MODEL_PREFIX = "openai/gpt-oss"
# Whether reasoning tokens count against `max_completion_tokens` is undocumented: assume they do.
REASONING_HEADROOM_TOKENS = 1024

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # free-plan limit (100 MB on the developer plan)
AUDIO_EXTENSIONS = frozenset({"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"})

_DAILY_LIMIT = re.compile(r"per day|\((?:RPD|TPD|ASD)\)", re.IGNORECASE)
_MINUTE_TOKEN_LIMIT = re.compile(r"\(TPM\)|tokens per minute", re.IGNORECASE)
_SCHEMA_FAILURE = re.compile(
    r"does not match the expected schema|failed to generate json", re.IGNORECASE
)


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    label = "Groq"
    capabilities = frozenset({Capability.TEXT, Capability.TRANSCRIPTION})

    def __init__(
        self,
        api_key: str | None,
        text_model: str | None = None,
        transcription_model: str | None = None,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            text_model=(text_model or "").strip() or DEFAULT_TEXT_MODEL,
        )
        self._transcription_model = (transcription_model or "").strip() or (
            DEFAULT_TRANSCRIPTION_MODEL
        )

    @classmethod
    def from_settings(cls, settings: Any) -> "GroqProvider":
        key = settings.groq_api_key
        return cls(
            key.get_secret_value() if key is not None else None,
            settings.groq_text_model,
            settings.groq_transcription_model,
        )

    def model_for(self, capability: Capability) -> str:
        if capability is Capability.TRANSCRIPTION:
            return self._transcription_model
        return self._text_model

    # --- Text -------------------------------------------------------------------------------

    def _structured(self) -> bool:
        return self._text_model in STRUCTURED_OUTPUT_MODELS

    def response_format(self, schema: Any) -> dict[str, Any]:
        if not self._structured():
            return {"type": "json_object"}
        try:
            converted = to_groq_schema(schema)
        except SchemaConversionError as exc:
            raise ProviderError(
                ErrorKind.BAD_REQUEST, f"unsupported output schema: {exc}"
            ) from None
        # Best-effort mode (`strict: false`): optional fields stay allowed, Pydantic has the last
        # word.
        return {
            "type": "json_schema",
            "json_schema": {"name": "output", "strict": False, "schema": converted},
        }

    def system_text(self, request: ProviderRequest) -> str:
        if self._structured():
            return request.system
        # JSON object mode does not know the schema, and Groq wants JSON mentioned in the prompt.
        try:
            return f"{request.system}\n\n{schema_instruction(request.json_schema)}"
        except SchemaConversionError as exc:
            raise ProviderError(
                ErrorKind.BAD_REQUEST, f"unsupported output schema: {exc}"
            ) from None

    def _reasoning(self) -> bool:
        return self._text_model.startswith(REASONING_MODEL_PREFIX)

    def extra_body(self) -> dict[str, Any]:
        if self._reasoning():
            return {"reasoning_effort": "low", "include_reasoning": False}
        return {}

    def token_headroom(self) -> int:
        return REASONING_HEADROOM_TOKENS if self._reasoning() else 0

    # --- Speech to text ---------------------------------------------------------------------

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
        clip = request.audio
        self.check_audio(clip.data, clip.filename)  # before any network call
        body, content_type = encode_multipart(
            {
                "model": self._transcription_model,
                "language": request.language,
                "response_format": "verbose_json",
                "temperature": "0",
            },
            file_field="file",
            filename=clip.filename,
            content_type=clip.content_type,
            data=clip.data,
        )
        response = post(
            f"{self._base_url}/audio/transcriptions",
            headers=self._headers(content_type),
            body=body,
            timeout_s=request.timeout_s,
        )
        if response.status != 200:
            raise self.translate_error(response)
        data = response.json()
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str):
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the transcription answer has no text")
        # An empty text is a valid answer (silence); the caller decides what to tell the user.
        return ProviderResponse(
            text=text.strip(),
            model=self._transcription_model,
            transcription=_details(data),
        )

    @staticmethod
    def check_audio(data: bytes, filename: str) -> None:
        """Refuse a clip Groq would refuse, without spending a request."""
        if not data:
            raise ProviderError(ErrorKind.BAD_REQUEST, "the audio clip is empty")
        if len(data) > MAX_AUDIO_BYTES:
            raise ProviderError(
                ErrorKind.BAD_REQUEST,
                f"the audio clip is {len(data) / 1024 / 1024:.1f} MB; Groq accepts at most "
                f"{MAX_AUDIO_BYTES // 1024 // 1024} MB on the free plan",
            )
        extension = Path(filename).suffix.lstrip(".").lower()
        if extension not in AUDIO_EXTENSIONS:
            raise ProviderError(
                ErrorKind.BAD_REQUEST,
                f"unsupported audio format {extension or '(no extension)'!r}; Groq reads "
                f"{', '.join(sorted(AUDIO_EXTENSIONS))}",
            )

    # --- Errors (D-050) ---------------------------------------------------------------------

    def translate_error(self, response: Any) -> ProviderError:
        status = response.status
        detail = self.error_detail(response)
        raw = detail if not detail.startswith("HTTP ") else ""
        if status == 429:
            return self._rate_limit(response, raw, detail)
        if status == 400 and (
            _SCHEMA_FAILURE.search(raw) or _error_code(response) == "json_validate_failed"
        ):
            # Fixed text on purpose: the error body quotes the model's rejected output.
            return ProviderError(
                ErrorKind.INVALID_OUTPUT,
                "Groq could not produce JSON that matches the schema",
                status_code=status,
            )
        if status == 404:
            return ProviderError(
                ErrorKind.BAD_REQUEST,
                f"model not found on Groq ({detail}); check VOCAB_GROQ_TEXT_MODEL and "
                "VOCAB_GROQ_TRANSCRIPTION_MODEL",
                status_code=status,
            )
        if status == 413:
            return ProviderError(
                ErrorKind.BAD_REQUEST,
                f"request too large for this model's limits ({detail})",
                status_code=status,
            )
        if status == 498:  # flex tier at capacity
            return ProviderError(ErrorKind.TRANSIENT, detail, status_code=status)
        return super().translate_error(response)

    def _rate_limit(self, response: Any, raw: str, detail: str) -> ProviderError:
        retry_after = parse_retry_after(response.header("retry-after"))
        if retry_after is None:
            retry_after = retry_after_from_message(raw)
        if retry_after is None and _MINUTE_TOKEN_LIMIT.search(raw):
            retry_after = parse_retry_after(response.header("x-ratelimit-reset-tokens"))
        daily = bool(_DAILY_LIMIT.search(raw))
        kind = ErrorKind.QUOTA_EXHAUSTED if daily else ErrorKind.RATE_LIMITED
        return ProviderError(kind, detail, retry_after=retry_after, status_code=429)


def _details(data: dict[str, Any]) -> TranscriptionDetails:
    duration = as_number(data.get("duration"))
    raw_segments = data.get("segments")
    segments = tuple(
        SpeechSegment(
            start=as_number(raw.get("start")),
            end=as_number(raw.get("end")),
            no_speech_prob=as_number(raw.get("no_speech_prob")),
            avg_logprob=as_number(raw.get("avg_logprob")),
        )
        for raw in (raw_segments if isinstance(raw_segments, list) else [])
        if isinstance(raw, dict)
    )
    return TranscriptionDetails(
        duration_s=duration if duration is not None and duration >= 0 else None,
        segments=segments,
    )


def _error_code(response: Any) -> str | None:
    data = response.json()
    error = data.get("error") if isinstance(data, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None
