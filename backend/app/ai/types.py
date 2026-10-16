"""Shared types of the AI gateway: requests, responses, errors and results. Pure Python."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class Capability(StrEnum):
    TEXT = "text"
    TRANSCRIPTION = "transcription"


class ErrorKind(StrEnum):
    """What went wrong with one provider request (`policy.py` decides what follows)."""

    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TRANSIENT = "transient"  # 5xx, request timeout
    NETWORK = "network"
    AUTH = "auth"
    BAD_REQUEST = "bad_request"  # includes blocked content
    INVALID_OUTPUT = "invalid_output"  # unreadable JSON or rejected by the Pydantic schema


class AiStatus(StrEnum):
    OK = "ok"
    INCOMPLETE = "incomplete"  # output still invalid after the repair attempt ("to complete")
    UNAVAILABLE = "unavailable"


class UnavailableReason(StrEnum):
    NO_PROVIDER_CONFIGURED = "no_provider_configured"
    NETWORK = "network"
    QUOTA = "quota"
    AUTH = "auth"
    TIMEOUT = "timeout"  # the total time budget ran out
    ALL_FAILED = "all_failed"


class ProviderError(Exception):
    """Every library error is translated to this by the adapters. The gateway masks `message`."""

    def __init__(
        self,
        kind: ErrorKind,
        message: str = "",
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after
        self.status_code = status_code


# --- Programming errors: raised before any call, never returned as a result -------------------


class GatewayUsageError(ValueError):
    """The caller used the gateway wrongly (a bug, not an expected failure)."""


class UnknownTask(GatewayUsageError):
    pass


class InputTooLong(GatewayUsageError):
    pass


class SchemaMismatch(GatewayUsageError):
    pass


class UnknownProvider(GatewayUsageError):
    pass


class PromptError(GatewayUsageError):
    """Invalid prompt file, or inputs that do not match the prompt's placeholders."""


# --- Provider interface -----------------------------------------------------------------------


@dataclass(frozen=True)
class AudioClip:
    data: bytes
    filename: str = "audio.webm"
    content_type: str = "audio/webm"


@dataclass(frozen=True)
class ProviderRequest:
    system: str
    user: str
    # JSON Schema of the expected output: adapters use it for native JSON modes or in the prompt.
    json_schema: dict[str, object]
    timeout_s: float
    max_output_tokens: int


@dataclass(frozen=True)
class TranscriptionRequest:
    audio: AudioClip
    language: str
    timeout_s: float


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


# --- Results ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class AiResult[T: BaseModel]:
    status: AiStatus
    data: T | None = None
    reason: UnavailableReason | None = None
    detail: str | None = None  # masked and truncated: validation message or last error
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 0  # provider requests made for this call
    call_id: int | None = None  # `ai_call_log.id` of the last request (None if not logged)

    @property
    def ok(self) -> bool:
        return self.status is AiStatus.OK


@dataclass(frozen=True)
class ProviderStatus:
    """Health snapshot of one provider. Never contains a key."""

    name: str
    capabilities: frozenset[Capability]
    configured: bool
    enabled: bool  # listed in the `ai_provider_order` setting
    available: bool  # configured, enabled, not cooling down, not marked as misconfigured
    cooldown_until: datetime | None
    misconfigured: bool
    last_error: ErrorKind | None
