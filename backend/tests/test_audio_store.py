"""Local storage of recordings (app/speech/audio_store.py)."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ai.providers.groq import AUDIO_EXTENSIONS
from app.config import Settings
from app.speech.audio_store import (
    ACCEPTED_TYPES,
    AUDIO_DIR,
    DEMO_AUDIO_DIR,
    SERVED_TYPES,
    AudioStore,
    InvalidAudioPath,
    extension_for,
    media_type,
    served_type,
)

AT = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
STORED = re.compile(r"2026/10/[0-9a-f]{32}\.wav")


@pytest.fixture
def store(tmp_path: Path) -> AudioStore:
    return AudioStore(tmp_path / "audio")


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [
        ("audio/webm", "webm"),
        ("audio/webm;codecs=opus", "webm"),
        ("Audio/WEBM; codecs=opus", "webm"),
        ("audio/ogg", "ogg"),
        ("audio/mp4", "m4a"),
        ("audio/x-m4a", "m4a"),
        ("audio/wav", "wav"),
        ("audio/x-wav", "wav"),
        ("audio/mpeg", "mp3"),
        ("audio/flac", None),
        ("video/webm", None),
        ("application/json", None),
        ("", None),
        (None, None),
    ],
)
def test_accepted_media_types(content_type: str | None, extension: str | None) -> None:
    assert extension_for(content_type) == extension


def test_media_type_drops_parameters() -> None:
    assert media_type(" audio/ogg ; codecs=opus") == "audio/ogg"


def test_groq_reads_every_accepted_format() -> None:
    assert set(ACCEPTED_TYPES.values()) == set(SERVED_TYPES) <= AUDIO_EXTENSIONS


@pytest.mark.parametrize(
    ("path", "served"),
    [("2026/10/x.webm", "audio/webm"), ("x.m4a", "audio/mp4"), ("x.mp3", "audio/mpeg")],
)
def test_the_served_type_follows_the_extension(path: str, served: str) -> None:
    assert served_type(path) == served


def test_save_writes_a_server_named_file(store: AudioStore) -> None:
    relative = store.save(b"RIFF-data", "wav", at=AT)

    assert STORED.fullmatch(relative), relative
    path = store.root / relative
    assert path.read_bytes() == b"RIFF-data"
    assert [p.name for p in path.parent.iterdir()] == [path.name]  # no temporary file left
    assert store.save(b"RIFF-data", "wav", at=AT) != relative  # a new name every time


def test_names_come_from_the_injected_factory(tmp_path: Path) -> None:
    names = iter(["0" * 32, "ab" * 16])
    store = AudioStore(tmp_path / "audio", names=lambda: next(names))

    assert store.save(b"RIFF", "wav", at=AT) == "2026/10/" + "0" * 32 + ".wav"
    assert store.save(b"RIFF", "wav", at=AT) == "2026/10/" + "ab" * 16 + ".wav"


@pytest.mark.parametrize("name", ["", "ABCDEF" + "0" * 26, "0" * 31, "../" + "0" * 29, "g" * 32])
def test_a_name_outside_the_pattern_is_refused(tmp_path: Path, name: str) -> None:
    store = AudioStore(tmp_path / "audio", names=lambda: name)
    with pytest.raises(ValueError, match="32 hexadecimal"):
        store.save(b"RIFF", "wav", at=AT)
    assert not store.root.exists()


def test_save_refuses_an_unknown_extension(store: AudioStore) -> None:
    with pytest.raises(ValueError, match="unsupported audio extension"):
        store.save(b"x", "exe", at=AT)
    assert not store.root.exists()


def test_a_failed_write_leaves_no_temporary_file(
    store: AudioStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(source: object, target: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr("app.speech.audio_store.os.replace", broken_replace)
    with pytest.raises(PermissionError):
        store.save(b"RIFF", "wav", at=AT)
    assert [p for p in store.root.rglob("*") if p.is_file()] == []


def test_resolve_stays_in_the_folder(store: AudioStore) -> None:
    relative = store.save(b"RIFF", "wav", at=AT)
    path = store.resolve(relative)
    assert path.is_file() and path.is_relative_to(store.root.resolve())


@pytest.mark.parametrize(
    "path",
    [
        "../vocab-coach.sqlite3",
        "2026/10/../../../.env",
        "2026/10/" + "a" * 32 + ".exe",
        "2026/10/" + "A" * 32 + ".wav",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "2026\\10\\" + "a" * 32 + ".wav",
        "",
        "2026/10/" + "a" * 32 + ".wav/../../x",
    ],
)
def test_resolve_refuses_paths_outside_the_pattern(store: AudioStore, path: str) -> None:
    with pytest.raises(InvalidAudioPath):
        store.resolve(path)
    assert not store.exists(path)


def test_exists_and_delete(store: AudioStore) -> None:
    relative = store.save(b"RIFF", "wav", at=AT)
    assert store.exists(relative)
    store.delete(relative)
    assert not store.exists(relative)
    store.delete(relative)  # already gone: quiet
    store.delete("../not-a-recording")  # refused path: quiet, nothing touched
    assert not store.exists(None)


def test_demo_recordings_have_their_own_folder(tmp_path: Path) -> None:
    personal = AudioStore.for_settings(Settings(data_dir=tmp_path))
    demo = AudioStore.for_settings(Settings(data_dir=tmp_path, demo=True))
    assert personal.root == tmp_path.resolve() / AUDIO_DIR == tmp_path.resolve() / "audio"
    assert demo.root == tmp_path.resolve() / DEMO_AUDIO_DIR == tmp_path.resolve() / "audio-demo"
