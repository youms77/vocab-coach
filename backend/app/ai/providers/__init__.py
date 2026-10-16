"""AI providers. The gateway retries, falls back and logs; a provider only makes one request."""

from typing import Protocol

from app.ai.types import Capability, ProviderRequest, ProviderResponse, TranscriptionRequest
from app.config import Settings, get_settings


class Provider(Protocol):
    """One AI service. It neither retries nor logs, and translates every library error into
    `ProviderError(kind, retry_after, status_code, message)`.

    A provider may also define `min_request_timeout_s: float` (read with `getattr`, default 0): the
    shortest request timeout it needs, for a local model that has to load first (Ollama). The
    gateway still caps every request by what is left of its time budget.
    """

    name: str
    capabilities: frozenset[Capability]

    def is_configured(self) -> bool: ...

    def model_for(self, capability: Capability) -> str:
        """Model used for `capability` (logged even when the request fails)."""
        ...

    def generate_json(self, request: ProviderRequest) -> ProviderResponse: ...

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse: ...


def build_providers(settings: Settings | None = None) -> dict[str, Provider]:
    """The real providers, built from the settings, configured or not (D-040): `pin_provider` and
    `status()` must know every one of them. Gemini joins in M2.b2; until then it is not built, and
    the gateway skips a name it does not know."""
    from app.ai.providers.groq import GroqProvider
    from app.ai.providers.ollama import OllamaProvider

    settings = settings or get_settings()
    return {
        "groq": GroqProvider.from_settings(settings),
        "ollama": OllamaProvider.from_settings(settings),
    }
