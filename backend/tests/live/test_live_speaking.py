"""Real corrections of free speaking (M6.a2a). If one fails, the prompt is what gets fixed
(`app/ai/prompts/speaking_correction.v1.txt`, or the taxonomy descriptions it quotes), as D-132.

    $env:VOCAB_RUN_LIVE = '1'; uv run pytest tests/live/test_live_speaking.py -m live -v -s

- With Gemini only: the transcriptions of `content/examples/m6_speaking*.txt` are given to the
  service as if Whisper had written them (`record_speaking(transcription=...)`), then corrected for
  real. The first must give exactly its three expected codes, the second no error, and no wrong
  form may be a hesitation or a false start. Two requests (more if a repair is needed).
- With `VOCAB_LIVE_AUDIO` (a clip of 5 to 180 s, for example `m6_speaking.txt` read aloud): Groq
  transcribes it, then the AI corrects it. Only `ok` is required, since Whisper may smooth over
  the mistakes; the result is printed. `tests/live/test_live_speech.py` reads the same variable
  for a shadowing of at most 30 s: run the two files separately.

A quota or a rate limit gives a skip, not a failure.
"""

import os
import re
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.ai.providers.gemini import GeminiProvider
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult, AiStatus, UnavailableReason
from app.cli_speech import FILE_TYPES
from app.config import Settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.db.models import ErrorCategory, ErrorEvent, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from app.services import corrections, speaking, speech
from app.speech.audio_store import AudioStore
from tests.conftest import sqlite_url
from tests.speech_support import wav_bytes

EXAMPLES = Path(__file__).resolve().parents[3] / "content" / "examples"
PROMPT = "Describe where you study and for how long."
RECORDED = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
HESITATIONS = {"um", "uh", "er", "hmm"}


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def _skip_if_unavailable(result: corrections.CorrectionResult) -> None:
    if result.status == "unavailable":
        reason = result.reason.value if result.reason else "unknown"
        pytest.skip(f"AI unavailable ({reason}): quota, rate limit or network")


def _errors(engine: Engine, result: corrections.CorrectionResult) -> list[tuple[str, str]]:
    with Session(engine) as session:
        return [
            (code, wrong)
            for code, wrong in session.execute(
                select(ErrorCategory.code, ErrorEvent.erroneous_text)
                .join(ErrorEvent, ErrorEvent.category_id == ErrorCategory.id)
                .where(ErrorEvent.id.in_(result.error_ids))
                .order_by(ErrorEvent.id)
            )
        ]


def _given_and_corrected(
    gemini: GeminiProvider, engine: Engine, tmp_path: Path, file: Path
) -> corrections.CorrectionResult:
    text = file.read_text(encoding="utf-8").strip()
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    gateway = Gateway(
        {"gemini": gemini}, session_factory=factory, provider_order=lambda: ["gemini"]
    )
    recorded = speaking.record_speaking(
        factory,
        gateway,
        AudioStore(tmp_path / "audio"),
        data=wav_bytes(1.0),
        content_type="audio/wav",
        duration_s=40.0,
        prompt_text=PROMPT,
        transcription=AiResult(
            status=AiStatus.OK, data=TranscriptionOutput(text=text), provider="given"
        ),
        clock=lambda: RECORDED,
    )
    result = speaking.correct_speaking(factory, gateway, recorded.production_id)
    _skip_if_unavailable(result)
    return result


def _is_hesitation_or_false_start(wrong: str) -> bool:
    tokens = re.findall(r"[a-z']+", wrong.casefold())
    return bool(HESITATIONS & set(tokens)) or wrong.strip().casefold() in {"i present", "present"}


def test_the_example_speech_gives_exactly_the_three_expected_codes(
    gemini: GeminiProvider, live_engine: Engine, tmp_path: Path
) -> None:
    result = _given_and_corrected(gemini, live_engine, tmp_path, EXAMPLES / "m6_speaking.txt")
    assert result.status == "ok", result
    found = _errors(live_engine, result)
    print(f"\n{found}")
    assert sorted(code for code, _ in found) == [
        "grammar.preposition.by_for_since",
        "grammar.preposition.fixed_expression",
        "grammar.tense.past_simple_vs_present_perfect",
    ], found
    assert not [wrong for _, wrong in found if _is_hesitation_or_false_start(wrong)], found
    assert result.proposed_category_ids == []
    with Session(live_engine) as session:
        attempt = session.get_one(ProductionAttempt, result.attempt_id)
        structure = (attempt.ai_feedback or {})["output"]["structure"]
        assert structure is not None and structure["comment_en"], structure


def test_a_clean_speech_has_no_error(
    gemini: GeminiProvider, live_engine: Engine, tmp_path: Path
) -> None:
    result = _given_and_corrected(gemini, live_engine, tmp_path, EXAMPLES / "m6_speaking_clean.txt")
    assert result.status == "ok", result
    assert result.error_ids == [], _errors(live_engine, result)


def test_a_real_recording_is_transcribed_then_corrected(
    live_settings: Settings, live_engine: Engine, tmp_path: Path
) -> None:
    value = os.environ.get("VOCAB_LIVE_AUDIO")
    if not value:
        pytest.skip("set VOCAB_LIVE_AUDIO to a recording of 5 to 180 s to test free speaking")
    clip = Path(value)
    if not clip.is_file():
        pytest.skip(f"VOCAB_LIVE_AUDIO does not point to a file: {clip}")
    content_type = FILE_TYPES.get(clip.suffix.lower())
    if content_type is None:
        pytest.skip(f"not an accepted recording: {clip.name}")
    providers = build_providers(live_settings)
    if not providers["groq"].is_configured():
        pytest.skip("Groq is not configured (VOCAB_GROQ_API_KEY)")
    factory = lambda: Session(live_engine, expire_on_commit=False)  # noqa: E731
    gateway = Gateway(
        lambda: build_providers(live_settings),
        session_factory=factory,
        secrets=live_settings.secret_values,
    )
    recorded = _record_audio(gateway, factory, tmp_path, clip, content_type)
    heard = recorded.transcription
    if heard.status == "unavailable" and heard.reason in (
        UnavailableReason.QUOTA.value,
        UnavailableReason.TIMEOUT.value,
    ):
        pytest.skip(f"Groq is unavailable for now ({heard.reason})")
    assert heard.status == "ok", heard
    print(f"\nheard ({recorded.audio_seconds} s): {heard.text}")
    result = speaking.correct_speaking(factory, gateway, recorded.production_id)
    _skip_if_unavailable(result)
    assert result.status == "ok", result
    print(_errors(live_engine, result))


def _record_audio(
    gateway: Gateway,
    factory: speech.SessionFactory,
    tmp_path: Path,
    clip: Path,
    content_type: str,
) -> speech.SpeechResult:
    """Groq measures the clip first (as the CLI without `--duration`), then it is stored."""
    data = clip.read_bytes()
    first = speech.transcribe_clip(gateway, data, speech.check_audio(data, content_type))
    if first.reason in (UnavailableReason.QUOTA, UnavailableReason.TIMEOUT):
        pytest.skip(f"Groq is unavailable for now ({first.reason.value}): {first.detail}")
    assert first.ok and first.data is not None, f"{first.status} {first.reason}: {first.detail}"
    return speaking.record_speaking(
        factory,
        gateway,
        AudioStore(tmp_path / "audio"),
        data=data,
        content_type=content_type,
        duration_s=None,
        prompt_text=PROMPT,
        transcription=first,
    )
