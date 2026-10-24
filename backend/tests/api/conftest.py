"""Fixtures of the API tests.

Nothing here may touch the owner's real `.env`, database or network:

- the `.env` path is redirected to a temporary folder *before* any `Settings` is built, and every
  `VOCAB_*` variable of the process is removed (otherwise the "set in the environment" rule would
  block key edits);
- the database is the migrated test copy;
- the providers are the real adapters pointed at fake servers on the loopback (D-054);
- the network guard of the AI tests (D-045) is reused.
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.ai.providers import Provider
from app.ai.providers.azure_speech import AzureSpeechProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.api.clock import get_now
from app.config import Settings, get_settings
from app.db.engine import get_engine, get_session
from app.main import create_app
from tests.ai.conftest import (  # noqa: F401  (fixtures re-exported for this directory)
    FakeClock,
    FixedRng,
    clock,
    make_server,
    no_network,
)
from tests.ai.fake_server import FakeServer, fixture_reply


@dataclass
class ApiEnv:
    client: TestClient
    gateway: Gateway
    engine: Engine
    env_path: Path
    servers: dict[str, FakeServer]
    clock: FakeClock

    def env_text(self) -> str:
        return self.env_path.read_text(encoding="utf-8") if self.env_path.exists() else ""


@pytest.fixture(autouse=True)
def isolated_settings(
    tmp_path: Path, db_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    env_path = tmp_path / "config" / ".env"
    env_path.parent.mkdir()
    monkeypatch.setitem(Settings.model_config, "env_file", env_path)
    for name in [name for name in os.environ if name.upper().startswith("VOCAB_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("VOCAB_DATABASE_URL", db_url)
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    yield env_path
    get_settings.cache_clear()


def _secret(value: object) -> str | None:
    return value.get_secret_value() if value is not None else None  # type: ignore[attr-defined]


@pytest.fixture
def servers(make_server: Callable[..., FakeServer]) -> dict[str, FakeServer]:  # noqa: F811
    return {
        "gemini": make_server(fixture_reply("gemini", "generate_ok")),
        "groq": make_server(fixture_reply("groq", "chat_ok")),
        "ollama": make_server(fixture_reply("ollama", "chat_ok")),
        "azure": make_server(fixture_reply("azure", "success_flat")),
    }


@pytest.fixture
def env(
    engine: Engine,
    isolated_settings: Path,
    servers: dict[str, FakeServer],
    clock: FakeClock,  # noqa: F811
) -> Iterator[ApiEnv]:
    def build() -> dict[str, Provider]:
        settings = get_settings()
        return {
            "gemini": GeminiProvider(
                _secret(settings.gemini_api_key),
                settings.gemini_model,
                base_url=servers["gemini"].base_url + "/v1beta",
            ),
            "groq": GroqProvider(
                _secret(settings.groq_api_key),
                settings.groq_text_model,
                settings.groq_transcription_model,
                base_url=servers["groq"].base_url,
            ),
            "ollama": OllamaProvider.from_settings(settings),
            "azure": AzureSpeechProvider(
                _secret(settings.azure_speech_key),
                settings.azure_speech_region,
                base_url=servers["azure"].base_url,
            ),
        }

    gateway = Gateway(
        build,
        session_factory=lambda: Session(engine, expire_on_commit=False),
        secrets=lambda: get_settings().secret_values(),
        clock=clock.now,
        sleep=clock.sleep,
        rng=FixedRng(),
    )

    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_gateway] = lambda: gateway
    app.dependency_overrides[get_now] = clock.now  # routes and gateway share one day
    client = TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}")
    yield ApiEnv(client, gateway, engine, isolated_settings, servers, clock)
    client.close()


@dataclass
class FakeAiEnv:
    """The API with one scripted `FakeProvider` instead of the real adapters."""

    client: TestClient
    provider: Any
    engine: Engine
    clock: FakeClock
    db_url: str
    gateway: Gateway

    def script(self, *steps: Any) -> None:
        """Replace the provider's script (and restart it)."""
        self.provider.script = list(steps)
        self.provider._calls = 0  # noqa: SLF001

    def use(self, provider: Any) -> None:
        """Answer with another provider (a subclass that spies on the call, for instance)."""
        self.provider = provider
        self.gateway._providers = {"fake": provider}  # noqa: SLF001


@pytest.fixture
def fake_env(engine: Engine, db_url: str, clock: FakeClock) -> Iterator[FakeAiEnv]:  # noqa: F811
    from app.ai.providers.fake import FakeProvider
    from app.db.taxonomy import sync_taxonomy

    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    provider = FakeProvider("fake", [], advance=clock.advance)
    gateway = Gateway(
        {"fake": provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: ["fake"],
        clock=clock.now,
        sleep=clock.sleep,
        rng=FixedRng(),
    )

    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_gateway] = lambda: gateway
    app.dependency_overrides[get_now] = clock.now
    with TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}") as client:
        yield FakeAiEnv(client, provider, engine, clock, db_url, gateway)
