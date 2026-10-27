"""A real pronunciation assessment (M6.c1): Azure AI Speech, F0 tier, on your own clip.

    $env:VOCAB_RUN_LIVE = '1'; $env:VOCAB_LIVE_AZURE_AUDIO = 'C:/path/to/clip.wav'
    uv run pytest tests/live/test_live_azure.py -m live -v -s

The clip must be a WAV (PCM, 16 kHz, mono) or an OGG Opus take of at most 30 s; `VOCAB_LIVE_TARGET`
is the sentence you said (default: the sentence of the owner's scenario). Needs
`VOCAB_AZURE_SPEECH_KEY` and `VOCAB_AZURE_SPEECH_REGION` (environment or `.env`).
**One request**: it spends a few seconds of the 5 free hours of the month. It is the proof of
what the documentation leaves open (D-211): the real answer shape, whether F0 includes
pronunciation assessment, and the body of a quota error. A quota or a rate limit gives a skip,
not a failure.
"""

import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.azure_speech import AzureSpeechProvider
from app.ai.types import AudioClip, UnavailableReason
from app.cli_speech import render_assessment
from app.db import migrate
from app.db.engine import create_db_engine
from app.domain import pronunciation as pa
from app.speech.audio_store import served_type
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


def test_a_real_clip_is_scored_word_by_word(
    azure: AzureSpeechProvider, live_engine: Engine
) -> None:
    value = os.environ.get("VOCAB_LIVE_AZURE_AUDIO")
    if not value:
        pytest.skip(
            "set VOCAB_LIVE_AZURE_AUDIO to a WAV 16 kHz mono (or OGG Opus) take of yourself"
        )
    clip = Path(value)
    if not clip.is_file():
        pytest.skip(f"VOCAB_LIVE_AZURE_AUDIO does not point to a file: {clip}")
    data = clip.read_bytes()
    problem = pa.audio_problem(data, clip.suffix)
    if problem is not None:
        pytest.skip(f"{clip.name} is not a clip Azure reads: {problem}")
    target = os.environ.get("VOCAB_LIVE_TARGET") or DEFAULT_TARGET
    gateway = Gateway(
        {"azure": azure},
        session_factory=lambda: Session(live_engine, expire_on_commit=False),
        provider_order=lambda: [],
    )
    result = gateway.assess_pronunciation(
        AudioClip(data=data, filename=clip.name, content_type=served_type(clip.name)),
        reference_text=target,
    )
    if result.reason in (UnavailableReason.QUOTA, UnavailableReason.TIMEOUT):
        pytest.skip(f"Azure is unavailable for now ({result.reason.value}): {result.detail}")
    assert result.ok and result.data is not None, (
        f"{result.status} {result.reason}: {result.detail}"
    )
    output = result.data
    document = pa.scores_document(
        output.model_dump(mode="json"), "azure", result.model or "", datetime.now(UTC)
    )
    print("\n" + render_assessment(document))
    print(f"\nduration {output.duration_s} s, {len(output.words)} word(s), model {result.model}")
    if output.status == "ok":
        assert output.words, "a scored take has words"
        assert output.pronunciation is not None, "no overall score in the answer"
        assert any(w.phonemes for w in output.words), "no phoneme detail in the answer"
