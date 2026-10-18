"""Scripted provider for tests and `python -m app ai simulate`. Never touches the network."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.ai.types import (
    Capability,
    ErrorKind,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    TranscriptionDetails,
    TranscriptionRequest,
)


@dataclass
class Success:
    """A successful answer. `content` is serialised to JSON when it is not already a string;
    `transcription` plays a transcription's duration and segments."""

    content: Any = field(default_factory=lambda: {"ok": True, "echo": "ping"})
    input_tokens: int | None = 10
    output_tokens: int | None = 5
    model: str | None = None
    latency_s: float = 0.0
    transcription: TranscriptionDetails | None = None


@dataclass
class Failure:
    kind: ErrorKind
    message: str = "scripted failure"
    retry_after: float | None = None
    status_code: int | None = None
    latency_s: float = 0.0


Step = Success | Failure


class FakeProvider:
    """Plays a list of steps in order, one per request; the last step repeats when the script ends.

    Every request received is kept in `requests` (text calls) or `transcriptions` for assertions.
    `advance` (optional) is called with each step's latency, to move a fake clock.
    """

    def __init__(
        self,
        name: str,
        script: Iterable[Step] = (),
        *,
        capabilities: Iterable[Capability] = (Capability.TEXT,),
        configured: bool = True,
        model: str = "fake-model",
        advance: Callable[[float], None] | None = None,
    ) -> None:
        self.name = name
        self.capabilities = frozenset(capabilities)
        self.configured = configured
        self.model = model
        self.script: list[Step] = list(script)
        self.requests: list[ProviderRequest] = []
        self.transcriptions: list[TranscriptionRequest] = []
        self._advance = advance
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def is_configured(self) -> bool:
        return self.configured

    def model_for(self, capability: Capability) -> str:
        return self.model

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self._play()

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
        self.transcriptions.append(request)
        return self._play()

    def _play(self) -> ProviderResponse:
        step = self.script[min(self._calls, len(self.script) - 1)] if self.script else Success()
        self._calls += 1
        if self._advance is not None and step.latency_s:
            self._advance(step.latency_s)
        if isinstance(step, Failure):
            raise ProviderError(
                step.kind,
                step.message,
                retry_after=step.retry_after,
                status_code=step.status_code,
            )
        text = step.content if isinstance(step.content, str) else json.dumps(step.content)
        return ProviderResponse(
            text=text,
            model=step.model or self.model,
            input_tokens=step.input_tokens,
            output_tokens=step.output_tokens,
            transcription=step.transcription,
        )
