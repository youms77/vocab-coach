"""Shadowing, transcription and comparison with the fake provider (app/services/speech.py)."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas import TranscriptionOutput
from app.ai.types import (
    AiResult,
    AiStatus,
    Capability,
    ErrorKind,
    ProviderResponse,
    TranscriptionRequest,
)
from app.db.event_log import record_event
from app.db.models import (
    EventLog,
    ProductionAttempt,
    ProductionTarget,
    PronunciationResult,
    StudySession,
)
from app.domain.enums import Modality, ProductionKind
from app.domain.events import EventType, ProductionTranscribed
from app.domain.speech_compare import VERSION
from app.services import speech
from app.services.library import ItemNotFound
from app.services.productions import ProductionNotFound, create_writing
from app.services.study_sessions import SessionClosed, SessionNotFound
from app.speech.audio_store import AudioStore
from tests.factories import add_item
from tests.library_support import count, events
from tests.speech_support import HEARD, TARGET, heard, wav_bytes

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
STT = (Capability.TRANSCRIPTION,)
WAV = wav_bytes(2.0)


@pytest.fixture
def store(tmp_path: Path) -> AudioStore:
    return AudioStore(tmp_path / "data" / "audio")


@pytest.fixture
def factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


def gateway_for(engine: Engine, provider: FakeProvider) -> Gateway:
    return Gateway(
        {provider.name: provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: [provider.name],
        sleep=lambda _: None,
    )


def fake(*script: Success | Failure, configured: bool = True) -> FakeProvider:
    return FakeProvider("fake", script, capabilities=STT, configured=configured)


def files(store: AudioStore) -> list[Path]:
    return [p for p in store.root.rglob("*") if p.is_file()] if store.root.exists() else []


def shadow(
    factory: Callable[[], Session],
    gateway: Gateway,
    store: AudioStore,
    **changes: object,
) -> speech.SpeechResult:
    arguments: dict[str, object] = {
        "data": WAV,
        "content_type": "audio/wav",
        "target_text": TARGET,
        "duration_s": 2.0,
        "clock": lambda: NOW,
    } | changes
    return speech.record_shadowing(factory, gateway, store, **arguments)  # type: ignore[arg-type]


# --- Success -------------------------------------------------------------------------------------


def test_a_transcribed_shadowing_is_stored_and_compared(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with Session(engine) as session:
        item_id = add_item(session, "account for").id
        session.commit()
    provider = fake(heard())

    result = shadow(factory, gateway_for(engine, provider), store, item_id=item_id)

    assert result.transcription.status == "ok"
    assert result.transcription.text == HEARD
    assert result.audio_seconds == 3.4  # the provider's measure replaces the recorder's 2.0
    comparison = result.transcription.comparison
    assert comparison is not None
    assert [(u.position, u.word, u.heard) for u in comparison.unrecognized] == [(4, "fixed", "fix")]
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None
        assert (attempt.kind, attempt.modality) == (ProductionKind.SHADOWING, Modality.ORAL)
        assert (attempt.prompt_text, attempt.text, attempt.word_count) == (TARGET, HEARD, 0)
        assert attempt.audio_seconds == 3.4
        assert attempt.ai_call_id is None  # reserved for a correction (M6.a2)
        assert (store.root / attempt.audio_path).read_bytes() == WAV  # type: ignore[operator]
        [target] = session.scalars(select(ProductionTarget)).all()
        assert (target.lexical_item_id, target.used) == (item_id, None)
        [row] = session.scalars(select(PronunciationResult)).all()
        assert (row.target_text, row.transcript, row.provider) == (TARGET, HEARD, "fake")
        assert row.unrecognized_words == [{"position": 4, "word": "fixed", "heard": "fix"}]
        assert row.scores is None
        [recorded] = events(session, "production.recorded")
        assert {k: v for k, v in recorded.items() if v is not None} == {
            "production_attempt_id": attempt.id,
            "kind": "shadowing",
            "modality": "oral",
            "word_count": 0,
            "audio_seconds": 2.0,
            "origin": "shadowing",
        }
        [transcribed] = events(session, "production.transcribed")
        assert transcribed["status"] == "ok" and transcribed["heard_word_count"] == 9
        assert (transcribed["provider"], transcribed["model"]) == ("fake", "whisper-large-v3")
        assert transcribed["audio_seconds"] == 3.4 and transcribed["ai_call_id"] >= 1
        [checked] = events(session, "pronunciation.checked")
        assert checked == {
            "production_attempt_id": attempt.id,
            "target_word_count": 9,
            "recognized_count": 8,
            "unrecognized_count": 1,
            "word_accuracy": 0.8889,
            "comparator_version": VERSION,
            "provider": "fake",
        }
        versions = session.scalars(
            select(EventLog.payload_version).where(
                EventLog.event_type == EventType.PRODUCTION_RECORDED.value
            )
        ).all()
        assert versions == [5]
        assert speech.transcription_state(session, attempt) == "ok"
        assert speech.comparison_of(session, attempt) == comparison
        assert count(session, EventLog) == 3  # no error event: recognition is not a judge


def test_the_target_sentence_is_never_sent_to_the_provider(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    provider = fake(heard())
    result = shadow(factory, gateway_for(engine, provider), store)

    [request] = provider.transcriptions
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.audio_path
    assert request.audio.filename == Path(attempt.audio_path).name  # the generated name
    assert (request.audio.content_type, request.audio.data) == ("audio/wav", WAV)
    assert request.language == "en"
    assert set(vars(request)) == {"audio", "language", "timeout_s"}  # no prompt field
    for word in ("account", "regional", "specifications"):
        assert word not in repr(request).replace(repr(WAV), "")


def test_without_a_provider_duration_the_recorder_duration_stays(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    result = shadow(factory, gateway_for(engine, fake(heard(duration_s=None))), store)
    assert result.audio_seconds == 2.0
    with Session(engine) as session:
        [transcribed] = events(session, "production.transcribed")
        assert transcribed["audio_seconds"] == 2.0


def test_a_discovery_shadowing_without_a_term(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    shadow(factory, gateway_for(engine, fake(heard())), store, origin="discovery")
    with Session(engine) as session:
        [recorded] = events(session, "production.recorded")
        assert recorded["origin"] == "discovery"
        assert count(session, ProductionTarget) == 0


def test_a_study_session_is_kept(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with Session(engine) as session:
        study = StudySession(started_at=NOW - timedelta(minutes=5))
        session.add(study)
        session.commit()
        study_id = study.id
    result = shadow(factory, gateway_for(engine, fake(heard())), store, study_session_id=study_id)
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.study_session_id == study_id
        rows = session.scalars(select(EventLog.study_session_id)).all()
        assert rows == [study_id] * 3


# --- Degraded mode and retry ---------------------------------------------------------------------


def test_without_a_provider_the_recording_stays_and_can_be_transcribed_later(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    result = shadow(factory, gateway_for(engine, fake(configured=False)), store)

    assert result.transcription == speech.TranscriptionOutcome(
        "unavailable", reason="no_provider_configured"
    )
    assert result.audio_seconds == 2.0
    assert len(files(store)) == 1
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.text == ""
        assert count(session, PronunciationResult) == 0
        assert events(session, "production.transcribed") == []
        assert speech.transcription_state(session, attempt) == "pending"
        assert speech.comparison_of(session, attempt) is None

    provider = fake(heard())
    again = speech.transcribe_production(
        factory, gateway_for(engine, provider), store, result.production_id, clock=lambda: NOW
    )

    assert again.transcription.status == "ok" and again.audio_seconds == 3.4
    assert provider.transcriptions[0].audio.data == WAV
    with Session(engine) as session:
        assert count(session, PronunciationResult) == 1
        assert len(events(session, "production.transcribed")) == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (Failure(ErrorKind.QUOTA_EXHAUSTED), "quota"),
        (Failure(ErrorKind.NETWORK), "network"),
        (Failure(ErrorKind.INVALID_OUTPUT), "incomplete"),
    ],
)
def test_ai_failures_are_results(
    engine: Engine,
    factory: Callable[[], Session],
    store: AudioStore,
    failure: Failure,
    reason: str,
) -> None:
    result = shadow(factory, gateway_for(engine, fake(failure)), store)
    assert result.transcription == speech.TranscriptionOutcome("unavailable", reason=reason)
    with Session(engine) as session:
        assert count(session, ProductionAttempt) == 1 and count(session, PronunciationResult) == 0


def test_a_second_transcription_is_refused(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    gateway = gateway_for(engine, fake(heard()))
    result = shadow(factory, gateway, store)
    with pytest.raises(speech.AlreadyTranscribed) as caught:
        speech.transcribe_production(factory, gateway, store, result.production_id)
    assert (caught.value.status, caught.value.code) == (409, "already_transcribed")


def test_a_transcription_written_during_the_call_wins(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    production_id = shadow(
        factory, gateway_for(engine, fake(configured=False)), store
    ).production_id

    class Racing(FakeProvider):
        def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
            with Session(engine) as other:  # another tab finished first
                record_event(
                    other,
                    ProductionTranscribed(
                        production_attempt_id=production_id,
                        kind=ProductionKind.SHADOWING,
                        provider="fake",
                        model="m",
                        status="ok",
                        heard_word_count=1,
                    ),
                    occurred_at=NOW,
                )
                other.commit()
            return super().transcribe(request)

    racing = Racing("fake", [heard()], capabilities=STT)
    with pytest.raises(speech.AlreadyTranscribed):
        speech.transcribe_production(factory, gateway_for(engine, racing), store, production_id)
    with Session(engine) as session:
        assert count(session, PronunciationResult) == 0


def test_no_write_transaction_is_open_during_the_call(
    engine: Engine, factory: Callable[[], Session], store: AudioStore, db_url: str
) -> None:
    path = db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    class Probing(FakeProvider):
        def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")  # 'database is locked' if a writer is open
                other.rollback()
            probes.append("free")
            return super().transcribe(request)

    gateway = gateway_for(
        engine, Probing("fake", [Failure(ErrorKind.NETWORK), heard()], capabilities=STT)
    )
    production_id = shadow(factory, gateway, store).production_id
    speech.transcribe_production(factory, gateway, store, production_id)
    assert probes == ["free", "free"]


# --- Silence -------------------------------------------------------------------------------------


def test_an_empty_transcription_is_silence(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    result = shadow(factory, gateway_for(engine, fake(heard("", segments=()))), store)
    assert result.transcription == speech.TranscriptionOutcome("silence")
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.text == ""
        assert count(session, PronunciationResult) == 0
        assert events(session, "pronunciation.checked") == []
        [transcribed] = events(session, "production.transcribed")
        assert (transcribed["status"], transcribed["heard_word_count"]) == ("silence", 0)
        assert speech.transcription_state(session, attempt) == "silence"


def test_a_hallucination_over_silence_is_silence(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    answer = heard("Thank you.", duration_s=1.8, segments=((0.92, -1.31),))
    result = shadow(factory, gateway_for(engine, fake(answer)), store)
    assert result.transcription.status == "silence"
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, result.production_id)
        assert attempt is not None and attempt.text == ""  # the invented text is not kept


def test_a_confident_short_answer_is_not_silence(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    answer = heard("We account", segments=((0.7, -0.4),))
    assert shadow(factory, gateway_for(engine, fake(answer)), store).transcription.status == "ok"


# --- Refusals ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "error", "status"),
    [
        ({"content_type": "audio/flac"}, speech.UnsupportedAudio, 415),
        ({"content_type": None}, speech.UnsupportedAudio, 415),
        ({"data": b""}, speech.AudioEmpty, 422),
        ({"data": b"\x00" * (10 * 1024 * 1024 + 1)}, speech.AudioTooLarge, 413),
        ({"duration_s": 0.4}, speech.AudioTooShort, 422),
        ({"duration_s": 30.5}, speech.AudioTooLong, 422),
        ({"duration_s": float("nan")}, speech.AudioTooShort, 422),
        ({"duration_s": None}, speech.DurationRequired, 422),
        ({"target_text": "   "}, speech.InvalidTarget, 422),
        ({"target_text": "... !"}, speech.InvalidTarget, 422),
        ({"target_text": "word " * 81}, speech.InvalidTarget, 422),
        ({"item_id": 999}, ItemNotFound, 404),
        ({"study_session_id": 999}, SessionNotFound, 404),
    ],
)
def test_refusals_store_nothing(
    engine: Engine,
    factory: Callable[[], Session],
    store: AudioStore,
    changes: dict[str, object],
    error: type[Exception],
    status: int,
) -> None:
    provider = fake(heard())
    with pytest.raises(error) as caught:
        shadow(factory, gateway_for(engine, provider), store, **changes)
    assert caught.value.status == status  # type: ignore[attr-defined]
    assert files(store) == []
    assert provider.transcriptions == []
    with Session(engine) as session:
        assert count(session, ProductionAttempt) == 0 and count(session, EventLog) == 0


def test_the_size_limit_is_inclusive(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    result = shadow(
        factory, gateway_for(engine, fake(heard())), store, data=b"\x00" * (10 * 1024 * 1024)
    )
    assert result.transcription.status == "ok"


def test_the_duration_errors_carry_the_bounds(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with pytest.raises(speech.AudioTooShort) as caught:
        shadow(factory, gateway_for(engine, fake()), store, duration_s=0.1)
    assert caught.value.extra == {"min_s": 0.5, "max_s": 30.0}


def test_a_closed_study_session_is_refused(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with Session(engine) as session:
        study = StudySession(started_at=NOW - timedelta(hours=1), ended_at=NOW)
        session.add(study)
        session.commit()
        study_id = study.id
    with pytest.raises(SessionClosed):
        shadow(factory, gateway_for(engine, fake()), store, study_session_id=study_id)
    assert files(store) == []


def test_the_file_is_deleted_when_the_transaction_fails(
    engine: Engine,
    factory: Callable[[], Session],
    store: AudioStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(speech, "record_event", broken)
    with pytest.raises(RuntimeError, match="disk full"):
        shadow(factory, gateway_for(engine, fake(heard())), store)
    assert files(store) == []
    with Session(engine) as session:
        assert count(session, ProductionAttempt) == 0


# --- A transcription obtained first (the CLI without --duration) ---------------------------------


def test_a_transcription_obtained_first_is_stored_without_a_second_call(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    provider = fake(heard(duration_s=4.2))
    gateway = gateway_for(engine, provider)
    first = speech.transcribe_clip(gateway, WAV, "wav")
    assert first.ok and provider.transcriptions[0].audio.filename == "recording.wav"

    result = shadow(factory, gateway, store, duration_s=None, transcription=first)

    assert provider.calls == 1
    assert result.transcription.status == "ok" and result.audio_seconds == 4.2
    with Session(engine) as session:
        [recorded] = events(session, "production.recorded")
        assert recorded["audio_seconds"] == 4.2


def test_a_transcription_without_duration_does_not_replace_it(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    gateway = gateway_for(engine, fake(heard(duration_s=None)))
    first = speech.transcribe_clip(gateway, WAV, "wav")
    with pytest.raises(speech.DurationRequired):
        shadow(factory, gateway, store, duration_s=None, transcription=first)
    assert files(store) == []


def test_a_failed_first_transcription_needs_a_duration(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    failed: AiResult = AiResult(status=AiStatus.UNAVAILABLE)
    with pytest.raises(speech.DurationRequired):
        shadow(factory, gateway_for(engine, fake()), store, duration_s=None, transcription=failed)


# --- Retry refusals ------------------------------------------------------------------------------


def test_transcribing_a_written_production_is_refused(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with Session(engine) as session:
        attempt = create_writing(
            session, text="A text.", prompt=None, target_item_ids=[], study_session_id=None, at=NOW
        )
        session.commit()
        attempt_id = attempt.id
    with pytest.raises(speech.NoAudio) as caught:
        speech.transcribe_production(factory, gateway_for(engine, fake()), store, attempt_id)
    assert (caught.value.status, caught.value.code) == (422, "no_audio")


def test_a_missing_file_cannot_be_transcribed(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    production_id = shadow(
        factory, gateway_for(engine, fake(configured=False)), store
    ).production_id
    for path in files(store):
        path.unlink()
    provider = fake(heard())
    with pytest.raises(speech.NoAudio):
        speech.transcribe_production(factory, gateway_for(engine, provider), store, production_id)
    assert provider.transcriptions == []


def test_an_unknown_production(
    engine: Engine, factory: Callable[[], Session], store: AudioStore
) -> None:
    with pytest.raises(ProductionNotFound):
        speech.transcribe_production(factory, gateway_for(engine, fake()), store, 42)


# --- In the caller's transaction (the demo, D-189) -----------------------------------------------


def given(text: str = HEARD, duration_s: float | None = 3.4) -> AiResult[TranscriptionOutput]:
    return AiResult(
        status=AiStatus.OK,
        data=TranscriptionOutput(text=text, duration_s=duration_s),
        provider="demo",
        model="demo-transcription-v1",
    )


def test_store_recording_writes_in_the_callers_transaction(
    engine: Engine, store: AudioStore
) -> None:
    with Session(engine) as session:
        item = add_item(session, "fixed effects")
        recording = speech.shadowing_recording(f"  {TARGET} ", item_id=item.id)
        result = speech.store_recording(
            session,
            store,
            recording,
            data=WAV,
            content_type="audio/wav",
            duration_s=None,
            transcription=given(),
            at=NOW,
        )
        assert result.transcription.status == "ok"
        assert result.transcription.comparison is not None
        assert [u.word for u in result.transcription.comparison.unrecognized] == ["fixed"]
        assert result.audio_seconds == 3.4
        with Session(engine) as other:  # nothing committed yet
            assert count(other, ProductionAttempt) == 0
        session.commit()
    with Session(engine) as session:
        attempt = session.get_one(ProductionAttempt, result.production_id)
        assert (attempt.prompt_text, attempt.text) == (TARGET, HEARD)
        assert store.exists(attempt.audio_path)
        assert count(session, PronunciationResult) == 1
        recorded = events(session, EventType.PRODUCTION_RECORDED)
        assert [e["origin"] for e in recorded] == ["shadowing"]
        assert [e["provider"] for e in events(session, EventType.PRODUCTION_TRANSCRIBED)] == [
            "demo"
        ]


def test_store_recording_without_a_transcription_leaves_it_pending(
    engine: Engine, store: AudioStore
) -> None:
    failed: AiResult[TranscriptionOutput] = AiResult(status=AiStatus.UNAVAILABLE)
    with Session(engine) as session:
        result = speech.store_recording(
            session,
            store,
            speech.shadowing_recording(TARGET),
            data=WAV,
            content_type="audio/wav",
            duration_s=2.0,
            transcription=failed,
            at=NOW,
        )
        assert result.transcription.status == "unavailable"
        attempt = session.get_one(ProductionAttempt, result.production_id)
        assert speech.transcription_state(session, attempt) == "pending"


def test_store_recording_refuses_before_the_file_and_deletes_it_on_failure(
    engine: Engine, store: AudioStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments: dict[str, object] = {
        "data": WAV,
        "content_type": "audio/wav",
        "duration_s": 2.0,
        "transcription": given(),
        "at": NOW,
    }
    with Session(engine) as session:
        with pytest.raises(ItemNotFound):
            speech.store_recording(
                session, store, speech.shadowing_recording(TARGET, item_id=999), **arguments
            )  # type: ignore[arg-type]
        assert files(store) == []

        def broken(*args: object, **kwargs: object) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr(speech, "store_transcription", broken)
        with pytest.raises(RuntimeError, match="disk full"):
            speech.store_recording(session, store, speech.shadowing_recording(TARGET), **arguments)  # type: ignore[arg-type]
        assert files(store) == []
