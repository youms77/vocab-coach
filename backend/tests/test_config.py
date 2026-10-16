import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_host_is_loopback() -> None:
    assert Settings(_env_file=None).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])  # noqa: S104
def test_non_loopback_host_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, host=host)


def test_host_can_be_set_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOCAB_HOST", "localhost")
    assert Settings(_env_file=None).host == "localhost"
