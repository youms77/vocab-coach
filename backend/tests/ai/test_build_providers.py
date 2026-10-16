"""`build_providers` and the Gemini settings (D-052, D-057)."""

import pytest

from app.ai.providers import build_providers
from app.ai.providers.gemini import DEFAULT_MODEL, GeminiProvider
from app.ai.types import Capability
from app.config import Settings
from app.domain.settings_defaults import KNOWN_AI_PROVIDERS

KEY = "AIzaSyTest_0123456789abcdefghij"


def test_every_known_provider_is_built_configured_or_not() -> None:
    providers = build_providers(Settings(_env_file=None))
    assert set(providers) == set(KNOWN_AI_PROVIDERS) == {"gemini", "groq", "ollama"}
    assert not any(provider.is_configured() for provider in providers.values())
    gemini = providers["gemini"]
    assert isinstance(gemini, GeminiProvider) and gemini.capabilities == {Capability.TEXT}
    assert gemini.model_for(Capability.TEXT) == DEFAULT_MODEL


def test_a_gemini_key_and_model_from_the_settings() -> None:
    settings = Settings(_env_file=None, gemini_api_key=KEY, gemini_model="gemini-3.8-flash")  # type: ignore[arg-type]
    gemini = build_providers(settings)["gemini"]
    assert gemini.is_configured() and gemini.model_for(Capability.TEXT) == "gemini-3.8-flash"


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_gemini_model_means_the_default(value: str) -> None:
    settings = Settings(_env_file=None, gemini_api_key=KEY, gemini_model=value)  # type: ignore[arg-type]
    assert settings.gemini_model is None
    assert build_providers(settings)["gemini"].model_for(Capability.TEXT) == DEFAULT_MODEL


def test_the_gemini_model_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOCAB_GEMINI_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("VOCAB_GEMINI_API_KEY", KEY)
    settings = Settings(_env_file=None)
    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.secret_values() == [KEY]
