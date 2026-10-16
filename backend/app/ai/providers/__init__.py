"""AI providers. The gateway retries, falls back and logs; a provider only makes one request."""

from typing import Protocol

from app.ai.types import Capability, ProviderRequest, ProviderResponse, TranscriptionRequest


class Provider(Protocol):
    """One AI service. It neither retries nor logs, and translates every library error into
    `ProviderError(kind, retry_after, status_code, message)`."""

    name: str
    capabilities: frozenset[Capability]

    def is_configured(self) -> bool: ...

    def model_for(self, capability: Capability) -> str:
        """Model used for `capability` (logged even when the request fails)."""
        ...

    def generate_json(self, request: ProviderRequest) -> ProviderResponse: ...

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse: ...


def build_providers() -> dict[str, Provider]:
    """The real providers, built from the settings. None yet: Gemini, Groq and Ollama arrive in
    M2.b, so until then every call is `unavailable(no_provider_configured)` (degraded mode)."""
    return {}
