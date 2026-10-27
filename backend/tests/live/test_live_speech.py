"""A real shadowing through the service (M6.a1): Groq Whisper with `verbose_json` on your own clip.

    $env:VOCAB_RUN_LIVE = '1'; $env:VOCAB_LIVE_AUDIO = 'C:/path/to/clip.m4a'
    uv run pytest tests/live/test_live_speech.py -m live -v -s

`VOCAB_LIVE_TARGET` is the sentence you said (default: the sentence of the owner's scenario). One
request. It checks the real answer carries a duration (the shape read from the documentation,
D-171) and prints the comparison. A quota or a rate limit gives a skip, not a failure.
"""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.groq import GroqProvider
from app.ai.types import UnavailableReason
from app.cli_speech import FILE_TYPES, render_comparison
from app.db import migrate
from app.db.engine import create_db_engine
from app.services import speech
from app.speech.audio_store import AudioStore
from tests.conftest import sqlite_url

DEFAULT_TARGET = "We account for regional fixed effects in all specifications."


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_a_real_clip_is_transcribed_measured_and_compared(
    groq: GroqProvider, live_engine: Engine, tmp_path: Path
) -> None:
    value = os.environ.get("VOCAB_LIVE_AUDIO")
    if not value:
        pytest.skip("set VOCAB_LIVE_AUDIO to a short recording of yourself to test shadowing")
    clip = Path(value)
    if not clip.is_file():
        pytest.skip(f"VOCAB_LIVE_AUDIO does not point to a file: {clip}")
    content_type = FILE_TYPES.get(clip.suffix.lower())
    if content_type is None:
        pytest.skip(f"not an accepted recording: {clip.name}")
    target = os.environ.get("VOCAB_LIVE_TARGET") or DEFAULT_TARGET
    data = clip.read_bytes()
    factory = lambda: Session(live_engine, expire_on_commit=False)  # noqa: E731
    gateway = Gateway({"groq": groq}, session_factory=factory, provider_order=lambda: ["groq"])

    first = speech.transcribe_clip(gateway, data, speech.check_audio(data, content_type))
    if first.reason in (UnavailableReason.QUOTA, UnavailableReason.TIMEOUT):
        pytest.skip(f"Groq is unavailable for now ({first.reason.value}): {first.detail}")
    assert first.ok and first.data is not None, f"{first.status} {first.reason}: {first.detail}"
    assert first.data.duration_s is not None, "verbose_json gave no duration"
    print(f"\nduration {first.data.duration_s} s, {len(first.data.segments)} segment(s)")

    result = speech.record_shadowing(
        factory,
        gateway,
        AudioStore(tmp_path / "audio"),
        data=data,
        content_type=content_type,
        target_text=target,
        duration_s=None,
        transcription=first,
    )

    assert result.transcription.status in ("ok", "silence")
    assert result.audio_seconds == first.data.duration_s
    if result.transcription.comparison is not None:
        print(
            render_comparison(
                target, result.transcription.text or "", result.transcription.comparison
            )
        )
