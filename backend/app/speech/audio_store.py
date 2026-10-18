"""Local storage of recordings (module F, D-169).

Recordings live under `<data_dir>/audio/` (`<data_dir>/audio-demo/` in demo mode, so no demo file
mixes with the owner's own and `demo seed` can empty the folder). The server names every file
`YYYY/MM/<uuid4 hex>.<ext>`, never with the client's name; `production_attempt.audio_path` holds
that path relative to the folder, and the served media type follows from the extension (no column).

Writing is atomic (a temporary file in the same folder, then `os.replace`), and done **before** the
database transaction: the caller deletes the file if the transaction fails. Reading checks the
stored path against the naming pattern and that it resolves inside the folder (no traversal).
"""

import contextlib
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.config import Settings, get_settings

AUDIO_DIR = "audio"
DEMO_AUDIO_DIR = "audio-demo"

# Accepted request media types (parameters such as `;codecs=opus` are ignored) -> extension.
ACCEPTED_TYPES: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
}
# Extension -> media type served on playback. Groq reads every one (`groq.AUDIO_EXTENSIONS`).
SERVED_TYPES: dict[str, str] = {
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
}

_STORED_PATH = re.compile(r"\d{4}/\d{2}/[0-9a-f]{32}\.(?:" + "|".join(SERVED_TYPES) + r")")


class InvalidAudioPath(ValueError):
    """A stored path that does not follow the naming pattern or leaves the audio folder."""


def media_type(content_type: str | None) -> str:
    """`audio/webm;codecs=opus` -> `audio/webm` (lower case, no parameters)."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def extension_for(content_type: str | None) -> str | None:
    """The file extension of an accepted media type, else None."""
    return ACCEPTED_TYPES.get(media_type(content_type))


def served_type(relative_path: str) -> str:
    return SERVED_TYPES.get(Path(relative_path).suffix.lstrip("."), "application/octet-stream")


class AudioStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def for_settings(cls, settings: Settings) -> "AudioStore":
        """The folder of the current mode: personal, or the demo's."""
        folder = DEMO_AUDIO_DIR if settings.demo else AUDIO_DIR
        return cls(settings.resolved_data_dir / folder)

    @classmethod
    def demo(cls, settings: Settings) -> "AudioStore":
        """The demo's folder whatever the mode (`demo seed` always builds the demo database)."""
        return cls(settings.resolved_data_dir / DEMO_AUDIO_DIR)

    def save(self, data: bytes, extension: str, *, at: datetime) -> str:
        """Write a new file atomically; returns its path relative to the folder."""
        if extension not in SERVED_TYPES:
            raise ValueError(f"unsupported audio extension {extension!r}")
        relative = f"{at:%Y}/{at:%m}/{uuid.uuid4().hex}.{extension}"
        final = self.root / relative
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.with_name(f".{final.name}.tmp")
        try:
            with open(temporary, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, final)
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
        return relative

    def resolve(self, relative_path: str) -> Path:
        """The absolute file of a stored path. Raises InvalidAudioPath."""
        if not _STORED_PATH.fullmatch(relative_path):
            raise InvalidAudioPath("not a recording path")
        root = self.root.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise InvalidAudioPath("outside the audio folder")
        return path

    def exists(self, relative_path: str | None) -> bool:
        if not relative_path:
            return False
        try:
            return self.resolve(relative_path).is_file()
        except InvalidAudioPath:
            return False

    def delete(self, relative_path: str) -> None:
        """Remove a file; quiet when it is already gone or still open (Windows)."""
        with contextlib.suppress(InvalidAudioPath, OSError):
            self.resolve(relative_path).unlink(missing_ok=True)

    def clear(self) -> None:
        """Empty the folder (the demo, after a new seed). A file another program holds open on
        Windows is left behind."""
        if self.root.is_dir():
            shutil.rmtree(self.root, ignore_errors=True)


def get_audio_store() -> AudioStore:
    """The store of the current settings (a FastAPI dependency; tests point `VOCAB_DATA_DIR` at a
    temporary folder)."""
    return AudioStore.for_settings(get_settings())
