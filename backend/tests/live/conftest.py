"""Live tests: a real call to each configured provider, with the owner's own keys.

They are skipped unless `VOCAB_RUN_LIVE=1` **and** the provider is configured (key or server
address in the environment or in `.env`). They are deselected by default (`-m 'not live'` in
`pyproject.toml`), so `npm run check` and the CI never run them; the CI has no key anyway.

    VOCAB_RUN_LIVE=1 uv run pytest tests/live -m live -v

At most one request per provider. A quota or rate limit gives a skip, not a failure.
"""

import os
from pathlib import Path

import pytest

from app.ai.providers import build_providers
from app.ai.providers.azure_speech import AzureSpeechProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.config import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if Path(str(item.fspath)).parent.name == "live":
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    if os.environ.get("VOCAB_RUN_LIVE") != "1":
        pytest.skip("live tests are off: set VOCAB_RUN_LIVE=1 to call the real providers")
    return Settings()


@pytest.fixture(scope="session")
def gemini(live_settings: Settings) -> GeminiProvider:
    provider = build_providers(live_settings)["gemini"]
    if not provider.is_configured():
        pytest.skip("Gemini is not configured (VOCAB_GEMINI_API_KEY)")
    assert isinstance(provider, GeminiProvider)
    return provider


@pytest.fixture(scope="session")
def groq(live_settings: Settings) -> GroqProvider:
    provider = build_providers(live_settings)["groq"]
    if not provider.is_configured():
        pytest.skip("Groq is not configured (VOCAB_GROQ_API_KEY)")
    assert isinstance(provider, GroqProvider)
    return provider


@pytest.fixture(scope="session")
def azure(live_settings: Settings) -> AzureSpeechProvider:
    provider = build_providers(live_settings)["azure"]
    if not provider.is_configured():
        pytest.skip("Azure Speech is not configured (VOCAB_AZURE_SPEECH_KEY and _REGION)")
    assert isinstance(provider, AzureSpeechProvider)
    return provider


@pytest.fixture(scope="session")
def ollama(live_settings: Settings) -> OllamaProvider:
    provider = build_providers(live_settings)["ollama"]
    if not provider.is_configured():
        pytest.skip("Ollama is not configured (VOCAB_OLLAMA_BASE_URL)")
    assert isinstance(provider, OllamaProvider)
    return provider
