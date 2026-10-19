"""Free speaking in the services (app/services/speaking.py, M6.a2a) with the fake provider: a
transcription given by the caller, the dates of the errors, the speaking topics file."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult, AiStatus, Capability
from app.db.models import ErrorCategory, ErrorEvent, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from app.domain.speaking_topics import SpeakingTag
from app.services import speaking, speaking_topics
from app.services.library import ItemNotFound
from app.speech.audio_store import AudioStore
from tests.library_support import count
from tests.speaking_support import EXPECTED_CODES, PROMPT, SPEECH, speaking_output
from tests.speech_support import wav_bytes

RECORDED = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
WAV = wav_bytes(1.0)


@pytest.fixture
def store(tmp_path: Path) -> AudioStore:
    return AudioStore(tmp_path / "data" / "audio")


@pytest.fixture
def factory(engine: Engine) -> Callable[[], Session]:
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    return lambda: Session(engine, expire_on_commit=False)


def gateway_for(engine: Engine, provider: FakeProvider) -> Gateway:
    return Gateway(
        {provider.name: provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: [provider.name],
        sleep=lambda _: None,
    )


def given(text: str = SPEECH, duration_s: float | None = 42.0) -> AiResult[TranscriptionOutput]:
    """A transcription obtained before the recording is stored (the CLI without `--duration`)."""
    return AiResult(
        status=AiStatus.OK,
        data=TranscriptionOutput(text=text, duration_s=duration_s),
        provider="fake",
        model="whisper-large-v3",
    )


def test_a_given_transcription_is_stored_without_calling_the_recogniser(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    provider = FakeProvider("fake", [], capabilities=(Capability.TRANSCRIPTION,))
    result = speaking.record_speaking(
        factory,
        gateway_for(engine, provider),
        store,
        data=WAV,
        content_type="audio/wav",
        duration_s=None,  # taken from the given transcription
        prompt_text=PROMPT,
        transcription=given(),
        clock=lambda: RECORDED,
    )
    assert provider.calls == 0
    assert (result.transcription.status, result.audio_seconds) == ("ok", 42.0)
    with factory() as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.text == SPEECH and attempt.word_count == 55


def test_the_errors_are_dated_at_the_recording(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    provider = FakeProvider("fake", [Success(content=speaking_output())])
    gateway = gateway_for(engine, provider)
    production_id = speaking.record_speaking(
        factory,
        gateway,
        store,
        data=WAV,
        content_type="audio/wav",
        duration_s=None,
        transcription=given(),
        clock=lambda: RECORDED,
    ).production_id
    later = RECORDED + timedelta(days=2)  # corrected two days later, once back online
    result = speaking.correct_speaking(factory, gateway, production_id, clock=lambda: later)
    assert result.status == "ok"
    with factory() as session:
        errors = session.scalars(select(ErrorEvent).order_by(ErrorEvent.id)).all()
        codes = [session.get_one(ErrorCategory, e.category_id).code for e in errors]
        assert codes == EXPECTED_CODES
        assert {e.occurred_at.replace(tzinfo=UTC) for e in errors} == {RECORDED}
        attempt = session.get_one(ProductionAttempt, production_id)
        assert attempt.updated_at.replace(tzinfo=UTC) == later


def test_an_unknown_term_is_refused_before_the_file_is_written(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with pytest.raises(ItemNotFound):
        speaking.record_speaking(
            factory,
            gateway_for(engine, FakeProvider("fake")),
            store,
            data=WAV,
            content_type="audio/wav",
            duration_s=30.0,
            target_item_ids=[999],
        )
    assert not store.root.exists() or not any(store.root.rglob("*.wav"))
    with factory() as session:
        assert count(session, ProductionAttempt) == 0


def test_the_speaking_topics_file() -> None:
    topics = speaking_topics.load_topics()
    assert len(topics) >= 24
    assert {tag for topic in topics for tag in topic.tags} == set(SpeakingTag)
    interview = [t for t in topics if SpeakingTag.INTERVIEW in t.tags]
    presenting = [t for t in topics if SpeakingTag.PRESENTING in t.tags]
    assert len(interview) >= 5 and len(presenting) >= 5
    assert any("results" in t.en for t in presenting)
    assert all(t.en.strip() and t.fr.strip() and t.en != t.fr for t in topics)
