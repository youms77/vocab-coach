"""Pronunciation assessment service (app/services/pronunciation.py), with fake providers."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.pronunciation import PronunciationAssessmentOutput, WordScore
from app.ai.types import AiResult, AiStatus, Capability, ErrorKind, PronunciationRequest
from app.db.event_log import record_event
from app.db.models import (
    AICallLog,
    ErrorEvent,
    EventLog,
    ProductionAttempt,
    PronunciationResult,
)
from app.db.settings_store import set_setting
from app.domain.events import PronunciationAssessed
from app.services import pronunciation, speech
from app.services.productions import ProductionNotFound, create_writing
from app.services.speech import AudioMissing, AudioTooLong
from app.speech.audio_store import AudioStore
from tests.audio_support import WEBM, ogg, wav
from tests.library_support import events
from tests.speech_support import HEARD, TARGET, heard

NOW = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
PA = Capability.PRONUNCIATION_ASSESSMENT
CLIP = wav(2.0)
OUTPUT = PronunciationAssessmentOutput(
    status="ok",
    accuracy=78,
    fluency=84,
    completeness=90,
    pronunciation=74.5,
    duration_s=2.0,
    words=[
        WordScore(word="We", accuracy=95, error_type="None"),
        WordScore(word="fixed", accuracy=40, error_type="Mispronunciation"),
        WordScore(word="effects", accuracy=0, error_type="Omission"),
    ],
)
SILENCE = PronunciationAssessmentOutput(status="silence")


@pytest.fixture
def store(tmp_path: Path) -> AudioStore:
    return AudioStore(tmp_path / "data" / "audio")


@pytest.fixture
def factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def assessment_on(engine: Engine) -> None:
    with Session(engine) as session:
        set_setting(session, "pronunciation_assessment", "azure")
        session.commit()


def azure(engine: Engine, *script: Success | Failure) -> tuple[Gateway, FakeProvider]:
    provider = FakeProvider(
        "azure",
        script or [Success(content="", assessment=OUTPUT)],
        capabilities=[PA],
        model="pa-rest-v1",
    )
    gateway = Gateway(
        {"azure": provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: [],
        sleep=lambda _: None,
    )
    return gateway, provider


def stt(engine: Engine, *script: Success | Failure) -> Gateway:
    provider = FakeProvider("fake", script, capabilities=[Capability.TRANSCRIPTION])
    return Gateway(
        {"fake": provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: ["fake"],
        sleep=lambda _: None,
    )


def shadow(
    factory,
    store,
    engine,
    *,
    data: bytes = CLIP,
    content_type: str = "audio/wav",
    transcribed: bool = False,
) -> int:
    script = [heard()] if transcribed else []
    gateway = stt(engine, *script)
    if not transcribed:  # no provider configured: the recording waits for its transcription
        gateway = Gateway({}, session_factory=lambda: Session(engine), provider_order=lambda: [])
    result = speech.record_shadowing(
        factory,
        gateway,
        store,
        data=data,
        content_type=content_type,
        target_text=TARGET,
        duration_s=2.0,
        clock=lambda: NOW,
    )
    return result.production_id


def new_writing(session: Session) -> ProductionAttempt:
    return create_writing(
        session,
        text="I fix the model.",
        prompt=None,
        target_item_ids=[],
        study_session_id=None,
        at=NOW,
    )


def assess(factory, gateway, store, production_id: int):
    return pronunciation.assess(factory, gateway, store, production_id, clock=lambda: NOW)


def rows(engine: Engine) -> list[PronunciationResult]:
    with Session(engine) as session:
        return list(session.scalars(select(PronunciationResult)))


def count(engine: Engine, model: type) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


# --- Refusals: before any call, nothing written --------------------------------------------------


def refusal_cases(engine, factory, store):
    def writing() -> int:
        with Session(engine) as session:
            attempt = new_writing(session)
            session.commit()
            return attempt.id

    def no_target() -> int:
        production_id = shadow(factory, store, engine)
        with Session(engine) as session:
            session.get(ProductionAttempt, production_id).prompt_text = None
            session.commit()
        return production_id

    def no_audio() -> int:
        production_id = shadow(factory, store, engine)
        with Session(engine) as session:
            session.get(ProductionAttempt, production_id).audio_path = None
            session.commit()
        return production_id

    def file_gone() -> int:
        production_id = shadow(factory, store, engine)
        for path in store.root.rglob("*.wav"):
            path.unlink()
        return production_id

    def off() -> int:
        production_id = shadow(factory, store, engine)
        with Session(engine) as session:
            set_setting(session, "pronunciation_assessment", "off")
            session.commit()
        return production_id

    def already() -> int:
        production_id = shadow(factory, store, engine)
        gateway, _ = azure(engine)
        assess(factory, gateway, store, production_id)
        return production_id

    def webm() -> int:
        return shadow(factory, store, engine, data=WEBM, content_type="audio/webm")

    def stereo_wav() -> int:
        return shadow(factory, store, engine, data=wav(2.0, channels=2))

    def too_long() -> int:
        production_id = shadow(factory, store, engine)
        with Session(engine) as session:
            session.get(ProductionAttempt, production_id).audio_seconds = 31.0
            session.commit()
        return production_id

    return [
        (lambda: 999, ProductionNotFound, "production_not_found"),
        (writing, pronunciation.NotAssessable, "not_assessable"),
        (no_target, pronunciation.NotAssessable, "not_assessable"),
        (no_audio, AudioMissing, "no_audio"),
        (file_gone, AudioMissing, "no_audio"),
        (off, pronunciation.AssessmentDisabled, "assessment_disabled"),
        (already, pronunciation.AlreadyAssessed, "already_assessed"),
        (webm, pronunciation.UnsupportedForAssessment, "unsupported_for_assessment"),
        (stereo_wav, pronunciation.UnsupportedForAssessment, "unsupported_for_assessment"),
        (too_long, AudioTooLong, "audio_too_long"),
    ]


@pytest.mark.parametrize("index", range(10))
def test_each_refusal_makes_no_call_and_writes_nothing(engine, factory, store, index) -> None:
    make, error, code = refusal_cases(engine, factory, store)[index]
    production_id = make()
    gateway, provider = azure(engine)
    before = (count(engine, PronunciationResult), count(engine, EventLog), count(engine, AICallLog))
    with pytest.raises(error) as caught:
        assess(factory, gateway, store, production_id)
    assert caught.value.code == code
    assert provider.calls == 0
    after = (count(engine, PronunciationResult), count(engine, EventLog), count(engine, AICallLog))
    assert after == before


def test_the_refusals_come_in_the_documented_order(engine, factory, store) -> None:
    # Disabled AND already assessed AND unsupported: "disabled" is reported first.
    production_id = shadow(factory, store, engine, data=WEBM, content_type="audio/webm")
    with Session(engine) as session:
        set_setting(session, "pronunciation_assessment", "off")
        session.commit()
    gateway, _ = azure(engine)
    with pytest.raises(pronunciation.AssessmentDisabled):
        assess(factory, gateway, store, production_id)


# --- Success, both write orders ------------------------------------------------------------------


def test_assessment_first_creates_the_row_and_the_transcription_fills_it(
    engine, factory, store
) -> None:
    production_id = shadow(factory, store, engine)  # not transcribed
    gateway, provider = azure(engine)
    outcome = assess(factory, gateway, store, production_id)
    assert outcome.status == "ok" and outcome.scores["format"] == "azure-pa-1"
    [only] = rows(engine)
    assert (only.transcript, only.provider, only.unrecognized_words) == ("", "", [])
    assert only.target_text == TARGET and only.scores == outcome.scores
    [request] = provider.assessments
    assert isinstance(request, PronunciationRequest) and request.reference_text == TARGET
    assert request.audio.data == CLIP and request.language == "en-US"
    with Session(engine) as session:  # no comparison against an empty transcript
        attempt = session.get(ProductionAttempt, production_id)
        assert speech.comparison_of(session, attempt) is None

    speech.transcribe_production(
        factory, stt(engine, heard()), store, production_id, clock=lambda: NOW
    )
    [only] = rows(engine)  # still one row
    assert only.transcript == HEARD and only.provider == "fake"
    assert only.scores == outcome.scores and len(only.unrecognized_words) == 1
    with Session(engine) as session:
        assert speech.comparison_of(session, session.get(ProductionAttempt, production_id))
        assert len(events(session, "pronunciation.checked")) == 1


def test_transcription_first_then_the_assessment_adds_the_scores(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine, transcribed=True)
    [before] = rows(engine)
    assert before.scores is None
    gateway, _ = azure(engine)
    outcome = assess(factory, gateway, store, production_id)
    [only] = rows(engine)
    assert only.id == before.id and only.transcript == HEARD and only.provider == "fake"
    assert only.scores == outcome.scores
    assert only.unrecognized_words == before.unrecognized_words


def test_the_stored_document_and_the_event(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine, transcribed=True)
    gateway, _ = azure(engine)
    outcome = assess(factory, gateway, store, production_id)
    doc = outcome.scores
    assert (doc["provider"], doc["model"], doc["status"]) == ("azure", "pa-rest-v1", "ok")
    assert doc["overall"] == {
        "accuracy": 78.0,
        "fluency": 84.0,
        "completeness": 90.0,
        "pronunciation": 74.5,
    }
    assert [w["word"] for w in doc["words"]] == ["We", "fixed", "effects"]
    assert doc["assessed_at"].startswith("2026-10-24T09:00:00")
    with Session(engine) as session:
        [event] = events(session, "pronunciation.assessed")
        call = session.scalars(
            select(AICallLog).where(AICallLog.task == "pronunciation_assessment")
        ).one()
    assert event == {
        "production_attempt_id": production_id,
        "provider": "azure",
        "model": "pa-rest-v1",
        "ai_call_id": call.id,
        "status": "ok",
        "audio_seconds": 3.4,  # the transcription's measure wins
        "accuracy": 78.0,
        "fluency": 84.0,
        "completeness": 90.0,
        "pronunciation": 74.5,
        "word_count": 3,
        "mispronounced": 1,
        "omitted": 1,
        "inserted": 0,
    }
    assert "We" not in str(event) and TARGET not in str(event)  # no text


def test_a_silent_take_is_stored_as_silence(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine)
    gateway, _ = azure(engine, Success(content="", assessment=SILENCE))
    outcome = assess(factory, gateway, store, production_id)
    assert outcome.status == "silence" and outcome.scores["overall"]["pronunciation"] is None
    with Session(engine) as session:
        [event] = events(session, "pronunciation.assessed")
    assert event["status"] == "silence" and event["pronunciation"] is None
    assert event["word_count"] == 0


def test_an_ogg_take_is_accepted(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine, data=ogg(2.0), content_type="audio/ogg")
    gateway, provider = azure(engine)
    assert assess(factory, gateway, store, production_id).status == "ok"
    assert provider.assessments[0].audio.filename.endswith(".ogg")


# --- Failures and concurrency -----------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "status", "reason"),
    [
        (Failure(ErrorKind.AUTH, status_code=401), "unavailable", "auth"),
        (Failure(ErrorKind.QUOTA_EXHAUSTED, status_code=429), "unavailable", "quota"),
        (Failure(ErrorKind.NETWORK), "unavailable", "network"),
        (Success(content=""), "incomplete", "incomplete"),
    ],
)
def test_an_ai_failure_is_a_result_and_can_be_retried(
    engine, factory, store, step, status, reason
) -> None:
    production_id = shadow(factory, store, engine)
    gateway, _ = azure(engine, step)
    outcome = assess(factory, gateway, store, production_id)
    assert (outcome.status, outcome.reason, outcome.scores) == (status, reason, None)
    assert rows(engine) == [] and count(engine, ErrorEvent) == 0
    with Session(engine) as session:
        assert events(session, "pronunciation.assessed") == []
    assert count(engine, AICallLog) >= 1  # the gateway's own journal
    retry, _ = azure(engine)
    assert assess(factory, retry, store, production_id).status == "ok"


def test_an_unconfigured_provider_is_unavailable_without_a_call(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine)
    provider = FakeProvider("azure", [], capabilities=[PA], configured=False)
    gateway = Gateway(
        {"azure": provider}, session_factory=lambda: Session(engine), provider_order=lambda: []
    )
    outcome = assess(factory, gateway, store, production_id)
    assert (outcome.status, outcome.reason) == ("unavailable", "no_provider_configured")
    assert provider.calls == 0 and count(engine, AICallLog) == 0


def test_a_second_writer_during_the_call_wins_and_no_transaction_is_open(
    engine, factory, store
) -> None:
    production_id = shadow(factory, store, engine)
    competing = AiResult(status=AiStatus.OK, data=OUTPUT, provider="other", model="m", attempts=1)

    class Rival(FakeProvider):
        def assess_pronunciation(self, request):
            # A short write transaction commits while the "call" is in progress: it would fail
            # or wait if the service still held one open.
            with Session(engine) as session:
                pronunciation.store_assessment(session, production_id, competing, at=NOW)
                session.commit()
            return super().assess_pronunciation(request)

    provider = Rival("azure", [Success(content="", assessment=OUTPUT)], capabilities=[PA])
    gateway = Gateway(
        {"azure": provider}, session_factory=lambda: Session(engine), provider_order=lambda: []
    )
    with pytest.raises(pronunciation.AlreadyAssessed):
        assess(factory, gateway, store, production_id)
    [only] = rows(engine)
    assert only.scores["provider"] == "other"  # the first committed result is kept
    with Session(engine) as session:
        assert len(events(session, "pronunciation.assessed")) == 1


def test_store_assessment_refuses_a_second_result_and_a_writing(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine)
    result = AiResult(status=AiStatus.OK, data=OUTPUT, provider="azure", model="m", attempts=1)
    with Session(engine) as session:
        pronunciation.store_assessment(session, production_id, result, at=NOW)
        session.commit()
    with Session(engine) as session, pytest.raises(pronunciation.AlreadyAssessed):
        pronunciation.store_assessment(session, production_id, result, at=NOW)
    with Session(engine) as session:
        writing = new_writing(session)
        session.flush()
        with pytest.raises(pronunciation.NotAssessable):
            pronunciation.store_assessment(session, writing.id, result, at=NOW)
    with Session(engine) as session, pytest.raises(ValueError):
        pronunciation.store_assessment(
            session, production_id, AiResult(status=AiStatus.UNAVAILABLE), at=NOW
        )


# --- State shown to the screens ---------------------------------------------------------


def test_assessable_reason_in_order(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine)
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, production_id)

        def reason(setting="azure", configured=True) -> str | None:
            return pronunciation.assessable_reason(
                session, attempt, setting=setting, configured=configured
            )

        assert reason() is None
        assert reason("off") == "disabled"
        assert reason("azure", False) == "not_configured"
        attempt.audio_seconds = 31.0
        assert reason() == "too_long"
        attempt.audio_path = attempt.audio_path.replace(".wav", ".webm")
        assert reason() == "unsupported_format"
        attempt.audio_path = None
        assert reason() == "no_audio"
        attempt.prompt_text = None
        assert reason() == "no_target"
        session.rollback()


def test_already_assessed_and_not_shadowing_reasons(engine, factory, store) -> None:
    production_id = shadow(factory, store, engine)
    gateway, _ = azure(engine)
    assess(factory, gateway, store, production_id)
    with Session(engine) as session:
        attempt = session.get(ProductionAttempt, production_id)
        assert (
            pronunciation.assessable_reason(session, attempt, setting="azure", configured=True)
            == "already_assessed"
        )
        assert pronunciation.assessment_of(session, production_id)["format"] == "azure-pa-1"
        writing = new_writing(session)
        session.flush()
        assert (
            pronunciation.assessable_reason(session, writing, setting="azure", configured=True)
            == "not_shadowing"
        )
        assert pronunciation.assessment_of(session, writing.id) is None


# --- Monthly use ------------------------------------------------------------------------


def add_assessed(session: Session, at: datetime, seconds: float | None, status="ok") -> None:
    record_event(
        session,
        PronunciationAssessed(
            production_attempt_id=1,
            provider="azure",
            model="m",
            status=status,
            audio_seconds=seconds,
        ),
        occurred_at=at,
    )


def test_monthly_usage_counts_the_calendar_month_in_utc(engine) -> None:
    with Session(engine) as session:
        add_assessed(session, datetime(2026, 9, 30, 23, 59, tzinfo=UTC), 10)  # last month
        add_assessed(session, datetime(2026, 10, 1, 0, 0, tzinfo=UTC), 4.5)
        add_assessed(session, datetime(2026, 10, 15, 12, 0, tzinfo=UTC), 6, "silence")
        add_assessed(session, datetime(2026, 10, 31, 23, 59, tzinfo=UTC), None)
        add_assessed(session, datetime(2026, 11, 1, 0, 0, tzinfo=UTC), 99)  # next month
        session.commit()
        usage = pronunciation.monthly_usage(session, datetime(2026, 10, 24, 9, tzinfo=UTC))
    assert (usage.month, usage.audio_seconds, usage.assessments) == ("2026-10", 10.5, 3)
    with Session(engine) as session:
        empty = pronunciation.monthly_usage(session, datetime(2026, 12, 31, 23, tzinfo=UTC))
    assert (empty.month, empty.audio_seconds, empty.assessments) == ("2026-12", 0.0, 0)


def test_month_bounds_wrap_the_year() -> None:
    start, following = pronunciation.month_bounds(datetime(2026, 12, 5, tzinfo=UTC))
    assert (start.month, following.year, following.month) == (12, 2027, 1)
    assert following - start == timedelta(days=31)
