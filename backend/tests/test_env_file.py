"""Editing the AI variables of `.env` (D-062): pure text edits, validation and the file work."""

import os
import threading
from pathlib import Path

import pytest

from app.config import Settings
from app.services import env_file
from app.services.env_file import (
    EnvFileError,
    clean_value,
    ensure_not_in_environment,
    set_variable,
    update_credential,
)

KEY = "AIzaSyExampleExampleExample1234567"
NAME = "VOCAB_GEMINI_API_KEY"


@pytest.fixture
def dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `.env` in a temporary folder, and no credential in the process environment."""
    path = tmp_path / ".env"
    monkeypatch.setitem(Settings.model_config, "env_file", path)
    for name in [*env_file.EDITABLE.values(), *env_file.REGION_VARIABLES.values()]:
        monkeypatch.delenv(name, raising=False)
    return path


# --- set_variable (pure) ------------------------------------------------------------------------


def test_replaces_the_line_and_keeps_everything_else() -> None:
    text = f"# my keys\nVOCAB_PORT=8000\n{NAME}=old\n\n# end\n"
    assert set_variable(text, NAME, KEY) == f"# my keys\nVOCAB_PORT=8000\n{NAME}={KEY}\n\n# end\n"


def test_keeps_crlf_line_endings() -> None:
    text = f"# c\r\n{NAME}=old\r\nVOCAB_PORT=8000\r\n"
    assert set_variable(text, NAME, KEY) == f"# c\r\n{NAME}={KEY}\r\nVOCAB_PORT=8000\r\n"
    assert set_variable("# c\r\nVOCAB_PORT=1\r\n", NAME, KEY).endswith(f"{NAME}={KEY}\r\n")


def test_appends_at_the_end_with_the_detected_line_ending() -> None:
    assert set_variable("A=1\n", NAME, KEY) == f"A=1\n{NAME}={KEY}\n"
    assert set_variable("A=1\r\n", NAME, KEY) == f"A=1\r\n{NAME}={KEY}\r\n"


def test_appends_to_a_file_without_final_newline() -> None:
    assert set_variable("A=1", NAME, KEY) == f"A=1\n{NAME}={KEY}"


def test_commented_line_is_left_intact_and_a_real_line_is_added() -> None:
    text = f"# {NAME}=\nA=1\n"
    result = set_variable(text, NAME, KEY)
    assert result == f"# {NAME}=\nA=1\n{NAME}={KEY}\n"


def test_name_match_ignores_case_and_export() -> None:
    assert set_variable(f"export {NAME.lower()} = old\n", NAME, KEY) == f"{NAME}={KEY}\n"


def test_does_not_touch_a_longer_variable_name() -> None:
    text = f"{NAME}_EXTRA=keep\n"
    assert set_variable(text, NAME, KEY) == f"{NAME}_EXTRA=keep\n{NAME}={KEY}\n"


def test_removal_blanks_the_value() -> None:
    assert set_variable(f"A=1\n{NAME}={KEY}\n", NAME, "") == f"A=1\n{NAME}=\n"


def test_removing_an_absent_key_changes_nothing() -> None:
    assert set_variable("A=1\n", NAME, "") == "A=1\n"
    assert set_variable("", NAME, "") == ""


def test_empty_text_gets_a_two_line_header() -> None:
    result = set_variable("", NAME, KEY)
    lines = result.splitlines()
    assert lines[0].startswith("# ") and lines[1].startswith("# ")
    assert ".env.example" in lines[0]
    assert lines[2] == f"{NAME}={KEY}"


def test_every_duplicate_line_is_replaced() -> None:
    assert set_variable(f"{NAME}=a\n{NAME}=b\n", NAME, KEY) == f"{NAME}={KEY}\n{NAME}={KEY}\n"


# --- Validation ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "short",
        "x" * 513,
        "has space in it 1234",
        "line\nbreak12345",
        "line\rbreak12345",
        "with#hash123456",
        "with=equal123456",
        'with"quote123456',
        "with'quote123456",
        "with$dollar12345",
        "tab\tinside12345",
        "bell\x07inside1234",
    ],
)
def test_bad_keys_are_refused(bad: str) -> None:
    with pytest.raises(EnvFileError) as caught:
        clean_value("gemini", bad)
    assert caught.value.code == "invalid_credential"
    assert bad.strip() not in caught.value.message  # the value never comes back in the message


def test_key_is_trimmed() -> None:
    assert clean_value("groq", f"  {KEY}\n") == KEY


@pytest.mark.parametrize("bad", ["", "ftp://127.0.0.1", "127.0.0.1:11434", "http://", "http://a b"])
def test_bad_ollama_addresses_are_refused(bad: str) -> None:
    with pytest.raises(EnvFileError) as caught:
        clean_value("ollama", bad)
    assert caught.value.code == "invalid_credential"


def test_ollama_address_is_normalized() -> None:
    assert clean_value("ollama", " http://127.0.0.1:11434/ ") == "http://127.0.0.1:11434"
    assert clean_value("ollama", "https://host.example/ollama") == "https://host.example/ollama"


# --- Environment variable priority --------------------------------------------------------------


def test_environment_variable_blocks_the_edit_even_when_empty(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setenv(NAME, "")
    with pytest.raises(EnvFileError) as caught:
        update_credential("gemini", KEY)
    assert caught.value.code == "set_in_environment"
    assert dotenv.read_text(encoding="utf-8") == "A=1\n"


def test_environment_check_ignores_case(monkeypatch: pytest.MonkeyPatch) -> None:
    # os.environ is case-insensitive on Windows; the check must not depend on it.
    monkeypatch.setattr(os, "environ", {"vocab_gemini_api_key": "x"})
    with pytest.raises(EnvFileError):
        ensure_not_in_environment(NAME)


# --- update_credential --------------------------------------------------------------------------


def test_creates_the_file_when_absent(dotenv: Path) -> None:
    assert update_credential("gemini", KEY).changed is True
    assert dotenv.read_text(encoding="utf-8").endswith(f"{NAME}={KEY}\n")


def test_removal_without_a_file_creates_nothing(dotenv: Path) -> None:
    assert update_credential("gemini", None).changed is False
    assert not dotenv.exists()


def test_set_then_remove_round_trip(dotenv: Path) -> None:
    dotenv.write_bytes(b"# keep me\r\nVOCAB_PORT=8000\r\n")
    update_credential("groq", KEY)
    assert (
        dotenv.read_bytes()
        == f"# keep me\r\nVOCAB_PORT=8000\r\nVOCAB_GROQ_API_KEY={KEY}\r\n".encode()
    )
    update_credential("groq", None)
    assert dotenv.read_bytes() == b"# keep me\r\nVOCAB_PORT=8000\r\nVOCAB_GROQ_API_KEY=\r\n"


def test_identical_content_is_not_rewritten(dotenv: Path) -> None:
    dotenv.write_text(f"{NAME}={KEY}\n", encoding="utf-8")
    before = dotenv.stat().st_mtime_ns
    calls: list[int] = []
    assert update_credential("gemini", KEY, after_write=lambda: calls.append(1)).changed is False
    assert dotenv.stat().st_mtime_ns == before
    assert calls == []


def test_bom_is_removed_on_write(dotenv: Path) -> None:
    dotenv.write_bytes(b"\xef\xbb\xbfA=1\n")
    update_credential("gemini", KEY)
    assert dotenv.read_bytes().startswith(b"A=1\n")


def test_after_write_runs_once_after_a_change(dotenv: Path) -> None:
    calls: list[str] = []
    update_credential("gemini", KEY, after_write=lambda: calls.append(dotenv.read_text("utf-8")))
    assert len(calls) == 1 and KEY in calls[0]  # the file is already written when it runs


def test_invalid_value_leaves_the_file_alone(dotenv: Path) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")
    with pytest.raises(EnvFileError):
        update_credential("gemini", "bad key with spaces")
    assert dotenv.read_text(encoding="utf-8") == "A=1\n"


def test_two_threads_writing_two_keys_keep_both(dotenv: Path) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(provider: str, value: str) -> None:
        try:
            barrier.wait(timeout=5)
            for _ in range(20):
                update_credential(provider, value)
                update_credential(provider, value + "X")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=write, args=("gemini", "g" * 20)),
        threading.Thread(target=write, args=("groq", "q" * 20)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors
    text = dotenv.read_text(encoding="utf-8")
    assert f"VOCAB_GEMINI_API_KEY={'g' * 20}X\n" in text
    assert f"VOCAB_GROQ_API_KEY={'q' * 20}X\n" in text
    assert text.startswith("A=1\n")


def test_failed_replace_keeps_the_original_and_leaves_no_temporary(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk on fire")

    monkeypatch.setattr(env_file.os, "replace", broken_replace)
    with pytest.raises(EnvFileError) as caught:
        update_credential("gemini", KEY)
    assert caught.value.code == "env_file_write_failed"
    assert KEY not in caught.value.message
    assert dotenv.read_text(encoding="utf-8") == "A=1\n"
    assert [p.name for p in dotenv.parent.iterdir()] == [".env"]


def test_locked_file_is_retried_then_reported(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("A=1\n", encoding="utf-8")
    attempts: list[int] = []
    sleeps: list[float] = []

    def locked(src: object, dst: object) -> None:
        attempts.append(1)
        raise PermissionError("in use")

    monkeypatch.setattr(env_file.os, "replace", locked)
    monkeypatch.setattr(env_file.time, "sleep", sleeps.append)
    with pytest.raises(EnvFileError) as caught:
        update_credential("gemini", KEY)
    assert caught.value.code == "env_file_locked"
    assert len(attempts) == env_file.WRITE_ATTEMPTS
    assert len(sleeps) == env_file.WRITE_ATTEMPTS - 1
    assert [p.name for p in dotenv.parent.iterdir()] == [".env"]


def test_lock_released_after_a_failure(dotenv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env_file.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(EnvFileError):
        update_credential("gemini", KEY)
    monkeypatch.undo()
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    for name in env_file.EDITABLE.values():
        monkeypatch.delenv(name, raising=False)
    assert update_credential("gemini", KEY).changed is True


def test_env_file_path_follows_the_settings_configuration(dotenv: Path) -> None:
    assert env_file.env_file_path() == dotenv
