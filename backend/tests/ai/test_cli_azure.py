"""`ai status` and `ai test` with Azure Speech (M6.c1, D-214)."""

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli_ai
from app.ai.providers.azure_speech import AzureSpeechProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.cli import main
from app.cli_ai import AiCommandError, run_ai_status, run_ai_test
from app.config import Settings
from app.db.models import AICallLog
from app.db.settings_store import set_setting
from tests.ai.fake_server import FakeServer, fixture_reply

KEY = "az0123456789abcdef0123456789abcd"


class Capture:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str = "") -> None:
        self.lines.append(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _providers(azure: FakeServer | None = None, region: str | None = "westeurope") -> dict:
    return {
        "gemini": GeminiProvider(None),
        "groq": GroqProvider(None),
        "ollama": OllamaProvider(None),
        "azure": AzureSpeechProvider(
            KEY if azure else None, region, base_url=azure.base_url if azure else None
        ),
    }


def _settings() -> Settings:
    return Settings(_env_file=None, azure_speech_key=KEY, azure_speech_region="westeurope")  # type: ignore[arg-type]


def test_status_reports_azure_apart_from_the_order(
    db_url: str, make_server: Callable[..., FakeServer]
) -> None:
    out = Capture()
    run_ai_status(db_url, _settings(), _providers(make_server()), out)
    assert "gemini > groq > ollama" in out.text
    assert (
        "Pronunciation assessment (azure, outside the order): configured, region westeurope"
        in out.text
    )
    assert "setting pronunciation_assessment = off" in out.text
    assert "model: pa-rest-v1" in out.text
    assert KEY not in out.text
    # Azure alone does not end the degraded mode of the text features.
    assert "Nothing is configured" in out.text


def test_status_says_when_azure_is_not_configured(db_url: str, engine: Engine) -> None:
    with Session(engine) as session:
        set_setting(session, "pronunciation_assessment", "azure")
        session.commit()
    out = Capture()
    run_ai_status(db_url, _settings(), _providers(region=None), out)
    assert "not configured, setting pronunciation_assessment = azure" in out.text


def test_azure_is_tested_with_one_second_of_silence_and_logged(
    db_url: str, engine: Engine, make_server: Callable[..., FakeServer]
) -> None:
    azure = make_server(fixture_reply("azure", "nomatch"))
    out = Capture()
    code = run_ai_test(db_url, _settings(), _providers(azure), provider="azure", out=out)
    assert code == cli_ai.EXIT_OK
    assert "azure: ok (pa-rest-v1" in out.text and KEY not in out.text
    [received] = azure.requests
    assert len(received.body) == 44 + 32000
    with Session(engine) as session:
        [row] = session.scalars(select(AICallLog))
    assert (row.provider, row.task) == ("azure", "pronunciation_assessment")


def test_a_rejected_key_gives_exit_1_without_the_key(
    db_url: str, make_server: Callable[..., FakeServer]
) -> None:
    azure = make_server(fixture_reply("azure", "error_401", status=401))
    out = Capture()
    code = run_ai_test(db_url, _settings(), _providers(azure), provider="azure", out=out)
    assert code == cli_ai.EXIT_FAILED
    assert "FAILED unavailable (auth)" in out.text and "HTTP 401" in out.text
    assert KEY not in out.text


def test_azure_is_not_part_of_the_default_run(
    db_url: str, make_server: Callable[..., FakeServer]
) -> None:
    azure = make_server(fixture_reply("azure", "nomatch"))
    groq = make_server(fixture_reply("groq", "chat_ok"))
    providers = _providers(azure)
    providers["groq"] = GroqProvider("gsk_test_0123456789abcdef", base_url=groq.base_url)
    assert run_ai_test(db_url, _settings(), providers, out=Capture()) == cli_ai.EXIT_OK
    assert azure.requests == []  # the free monthly hours are not spent by a default test


def test_an_unconfigured_azure_is_a_usage_error(db_url: str) -> None:
    with pytest.raises(AiCommandError, match="azure is not configured"):
        run_ai_test(db_url, _settings(), _providers(), provider="azure", out=Capture())


def test_main_accepts_azure_as_a_provider_choice(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["ai", "test", "--provider", "nope"])
    assert caught.value.code == 2
    assert "azure" in capsys.readouterr().err
