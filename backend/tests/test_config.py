from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings


def test_default_host_is_loopback() -> None:
    assert Settings(_env_file=None).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])  # noqa: S104
def test_non_loopback_host_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, host=host)


def test_host_can_be_set_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOCAB_HOST", "localhost")
    assert Settings(_env_file=None).host == "localhost"


def test_default_database_is_absolute_and_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VOCAB_DATABASE_URL", raising=False)
    monkeypatch.delenv("VOCAB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    expected = (REPO_ROOT / "data" / "vocab-coach.sqlite3").resolve().as_posix()
    assert Settings(_env_file=None).resolved_database_url == f"sqlite:///{expected}"


def test_relative_data_dir_is_taken_from_repository_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, data_dir=Path("my-data"))
    assert settings.resolved_data_dir == (REPO_ROOT / "my-data").resolve()


def test_database_url_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOCAB_DATABASE_URL", "sqlite:///C:/elsewhere/x.sqlite3")
    assert Settings(_env_file=None).resolved_database_url == "sqlite:///C:/elsewhere/x.sqlite3"
