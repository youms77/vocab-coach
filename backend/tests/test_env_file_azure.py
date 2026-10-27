"""Azure in the `.env` editor: a key and a region in one write (M6.c1, D-214)."""

from pathlib import Path

import pytest

from app.config import Settings
from app.services import env_file
from app.services.env_file import EnvFileError, update_credential

KEY = "AIzaSyTest_0123456789abcdefghij"
AZURE_KEY = "az0123456789abcdef0123456789abcd"


@pytest.fixture
def dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env"
    monkeypatch.setitem(Settings.model_config, "env_file", path)
    for name in [*env_file.EDITABLE.values(), *env_file.REGION_VARIABLES.values()]:
        monkeypatch.delenv(name, raising=False)
    return path


def test_the_editable_variables_are_five() -> None:
    names = {*env_file.EDITABLE.values(), *env_file.REGION_VARIABLES.values()}
    assert names == {
        "VOCAB_GEMINI_API_KEY",
        "VOCAB_GROQ_API_KEY",
        "VOCAB_OLLAMA_BASE_URL",
        "VOCAB_AZURE_SPEECH_KEY",
        "VOCAB_AZURE_SPEECH_REGION",
    }


def test_azure_key_and_region_are_written_together(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")
    writes: list[str] = []
    real = env_file._write_atomically

    def spy(path: Path, text: str) -> None:
        writes.append(text)
        real(path, text)

    monkeypatch.setattr(env_file, "_write_atomically", spy)
    assert update_credential("azure", AZURE_KEY, region="WestEurope").changed is True
    assert len(writes) == 1  # one atomic write, not two
    assert dotenv.read_text("utf-8") == (
        f"A=1\nVOCAB_AZURE_SPEECH_KEY={AZURE_KEY}\nVOCAB_AZURE_SPEECH_REGION=westeurope\n"
    )


def test_azure_key_alone_keeps_the_stored_region(dotenv: Path) -> None:
    update_credential("azure", AZURE_KEY, region="westeurope")
    update_credential("azure", AZURE_KEY + "2")
    text = dotenv.read_text("utf-8")
    assert "VOCAB_AZURE_SPEECH_REGION=westeurope" in text
    assert f"VOCAB_AZURE_SPEECH_KEY={AZURE_KEY}2" in text


def test_removing_azure_clears_key_and_region(dotenv: Path) -> None:
    update_credential("azure", AZURE_KEY, region="westeurope")
    update_credential("gemini", KEY)
    assert update_credential("azure", None).changed is True
    text = dotenv.read_text("utf-8")
    assert "VOCAB_AZURE_SPEECH_KEY=\n" in text and "VOCAB_AZURE_SPEECH_REGION=\n" in text
    assert KEY in text and AZURE_KEY not in text
    assert update_credential("azure", None).changed is False


@pytest.mark.parametrize("region", ["", "a", "west europe", "x" * 41, "eu/1", "a=b", "café"])
def test_an_invalid_region_changes_nothing(dotenv: Path, region: str) -> None:
    with pytest.raises(EnvFileError) as caught:
        update_credential("azure", AZURE_KEY, region=region)
    assert caught.value.code == "invalid_region"
    assert not dotenv.exists()


def test_a_region_is_refused_for_other_providers(dotenv: Path) -> None:
    with pytest.raises(EnvFileError) as caught:
        update_credential("gemini", KEY, region="westeurope")
    assert caught.value.code == "invalid_credential" and not dotenv.exists()


@pytest.mark.parametrize("variable", ["VOCAB_AZURE_SPEECH_KEY", "VOCAB_AZURE_SPEECH_REGION"])
def test_either_variable_in_the_environment_blocks_the_edit(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "")
    for value, region in ((AZURE_KEY, "westeurope"), (None, None)):
        with pytest.raises(EnvFileError) as caught:
            update_credential("azure", value, region=region)
        assert caught.value.code == "set_in_environment"
    assert not dotenv.exists()


def test_azure_errors_never_contain_the_values(dotenv: Path) -> None:
    with pytest.raises(EnvFileError) as caught:
        update_credential("azure", AZURE_KEY, region="bad region")
    assert AZURE_KEY not in caught.value.message and "bad region" not in caught.value.message
