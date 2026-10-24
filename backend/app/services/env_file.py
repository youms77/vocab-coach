"""Edit the five AI variables of the repository-level `.env` file (D-062, D-214).

The settings page (M2.c2) writes keys through the API. Only a closed list of variables can be
changed; everything else in the file (comments, other variables, order, line endings) is kept as it
is. A value never appears in an error message or a log.

A variable that exists in the process environment wins over `.env` (pydantic-settings): editing the
file would then change nothing, so the edit is refused (`set_in_environment`).

The functions that work on a text (`set_variable`) are pure and tested alone; `update_credential`
does the file work under a module lock, held from the read until the caller has reloaded the
settings and the gateway (two edits can never overwrite each other).
"""

import os
import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.ai.providers.ollama import _normalize as normalize_base_url
from app.config import Settings

# provider -> environment variable. The only variables this module ever writes.
EDITABLE = {
    "gemini": "VOCAB_GEMINI_API_KEY",
    "groq": "VOCAB_GROQ_API_KEY",
    "ollama": "VOCAB_OLLAMA_BASE_URL",
    "azure": "VOCAB_AZURE_SPEECH_KEY",
}
# Azure also needs a region (the host of its API): the fifth variable, written with the key in one
# atomic write.
REGION_VARIABLES = {"azure": "VOCAB_AZURE_SPEECH_REGION"}

REGION_PATTERN = re.compile(r"^[a-z0-9]{2,40}$")  # as the adapter's check (D-057, D-213)
KEY_MIN_LENGTH = 8
VALUE_MAX_LENGTH = 512
WRITE_ATTEMPTS = 3
WRITE_RETRY_DELAY_S = 0.1
HEADER = (
    "# Created by vocab-coach (settings page). Every variable is described in .env.example.\n"
    "# This file stays on your computer: Git ignores it.\n"
)
# Characters that would change the meaning of an unquoted .env value (comment, quote, expansion).
_FORBIDDEN = set("\"'`#=$")

_LOCK = threading.Lock()


class EnvFileError(Exception):
    """A credential cannot be saved. `code` is stable (the API returns it); the message is safe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def env_file_path() -> Path:
    """The `.env` the settings read: the only source of truth is `Settings.model_config`."""
    path = Settings.model_config.get("env_file")
    if not isinstance(path, str | os.PathLike):
        raise EnvFileError("env_file_write_failed", "No .env file location is configured.")
    return Path(path)


# --- Validation -------------------------------------------------------------------------------


def clean_value(provider: str, raw: str) -> str:
    """The value to store, or EnvFileError("invalid_credential")."""
    value = raw.strip()
    if provider == "ollama":
        if not 1 <= len(value) <= VALUE_MAX_LENGTH:
            raise _invalid("The Ollama address must be between 1 and 512 characters.")
        _check_characters(value, "address", allow_equal=True)
        normalized = normalize_base_url(value)
        if normalized is None:
            raise _invalid("The Ollama address must be an http:// or https:// URL with a host.")
        return normalized
    if not KEY_MIN_LENGTH <= len(value) <= VALUE_MAX_LENGTH:
        raise _invalid(
            f"The key must be between {KEY_MIN_LENGTH} and {VALUE_MAX_LENGTH} characters."
        )
    _check_characters(value, "key", allow_equal=False)
    return value


def clean_region(raw: str) -> str:
    """The region to store (lower case), or EnvFileError("invalid_region")."""
    value = raw.strip().lower()
    if not REGION_PATTERN.match(value):
        raise EnvFileError(
            "invalid_region",
            "The region must be 2 to 40 lower-case letters or digits, like westeurope.",
        )
    return value


def _check_characters(value: str, what: str, *, allow_equal: bool) -> None:
    forbidden = _FORBIDDEN - {"="} if allow_equal else _FORBIDDEN
    if not value.isprintable() or any(c.isspace() or c in forbidden for c in value):
        raise _invalid(
            f"The {what} contains a character that cannot be saved "
            "(space, line break, quote, #, $ or =)."
        )


def _invalid(message: str) -> EnvFileError:
    return EnvFileError("invalid_credential", message)


def ensure_not_in_environment(name: str) -> None:
    """Refuse to edit a variable that the process environment already defines (even empty)."""
    wanted = name.upper()
    if any(key.upper() == wanted for key in os.environ):
        raise EnvFileError(
            "set_in_environment",
            "This setting comes from an environment variable, which takes priority over the "
            ".env file. Remove the environment variable, then try again.",
        )


# --- Text editing (pure) ------------------------------------------------------------------------


def set_variable(text: str, name: str, value: str) -> str:
    """`text` with every active `NAME=...` line replaced by `NAME=value`, or the line appended.

    Comments, other lines, their order and the line endings (CRLF or LF) are kept. Names are
    matched without regard to case, like pydantic-settings does. An empty `value` removes the key
    (`NAME=`); removing a key that is not there leaves the text unchanged.
    """
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=", re.IGNORECASE)
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    found = False
    for index, line in enumerate(lines):
        if pattern.match(line):
            found = True
            ending = line[len(line.rstrip("\r\n")) :]
            lines[index] = f"{name}={value}{ending}"
    if found:
        return "".join(lines)
    if not value:
        return text
    if not text:
        return f"{HEADER}{name}={value}\n"
    if text.endswith(("\n", "\r")):
        return f"{text}{name}={value}{eol}"
    return f"{text}{eol}{name}={value}"


# --- File work ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvUpdate:
    changed: bool


def update_credential(
    provider: str,
    value: str | None,
    *,
    region: str | None = None,
    after_write: Callable[[], None] | None = None,
) -> EnvUpdate:
    """Save (or, with `value=None`, remove) the provider's credential in `.env`.

    For a provider that also has a region variable (Azure), `region` is saved with the key in the
    same write, and removing the key removes the region too. `region` is refused for any other
    provider (`invalid_credential`). Every variable to change must be free of the process
    environment (`set_in_environment`) before anything is written.

    `after_write` runs under the same lock when the file changed, so the caller can reload the
    settings and the gateway before another edit starts. Nothing is written when the content would
    be identical.
    """
    region_variable = REGION_VARIABLES.get(provider)
    if region is not None and region_variable is None:
        raise _invalid("This provider has no region.")
    changes = {EDITABLE[provider]: "" if value is None else clean_value(provider, value)}
    if region_variable is not None:
        if value is None:
            changes[region_variable] = ""
        elif region is not None:
            changes[region_variable] = clean_region(region)
    for name in changes:
        ensure_not_in_environment(name)
    path = env_file_path()
    with _LOCK:
        original = _read(path) or ""
        updated = original
        for name, stored in changes.items():
            updated = set_variable(updated, name, stored)
        if updated == original:
            return EnvUpdate(changed=False)
        _write_atomically(path, updated)
        if after_write is not None:
            after_write()
    return EnvUpdate(changed=True)


def _read(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except PermissionError:
        raise EnvFileError(
            "env_file_locked", "The .env file cannot be read: another program is using it."
        ) from None
    except OSError:
        raise EnvFileError("env_file_write_failed", "The .env file could not be read.") from None
    return data.decode("utf-8-sig", errors="replace")


def _write_atomically(path: Path, text: str) -> None:
    """Temporary file in the same folder, flushed, then `os.replace` (atomic, also on Windows)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    except OSError:
        raise EnvFileError("env_file_write_failed", "The .env file could not be written.") from None
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        _replace_with_retries(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _replace_with_retries(temp: Path, path: Path) -> None:
    """On Windows, `os.replace` fails with PermissionError while another program has the file open
    (an editor, an antivirus scan): a few short retries, then a clear message."""
    for attempt in range(WRITE_ATTEMPTS):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == WRITE_ATTEMPTS - 1:
                raise EnvFileError(
                    "env_file_locked",
                    "The .env file is in use by another program. Close it, then try again.",
                ) from None
            time.sleep(WRITE_RETRY_DELAY_S)
        except OSError:
            raise EnvFileError(
                "env_file_write_failed", "The .env file could not be written."
            ) from None
