"""Pronunciation assessment of a shadowing take (module F, optional Azure tier, M6.c1).

`assess` scores the stored recording against the target sentence, word by word and phoneme by
phoneme, and stores the result in `pronunciation_result.scores` (format `azure-pa-1`). Order
of operations (D-038, D-215):

1. a short read: the refusals, in a fixed order, **before any call** (see `assess`), and the bytes
   of the recording; the session is closed;
2. `gateway.assess_pronunciation` with no session open;
3. a short write that checks again that the production is still assessable (a second writer may
   have committed during the call), then `store_assessment` and `pronunciation.assessed`.

An AI failure is a result, not an error (D-081): only the gateway's `ai_call_log` row is written
and the call can be repeated. Nothing here records an error (D-174): a score is an automatic
estimate, not a teacher's judgment.

`store_assessment` works in the **caller's** transaction (no commit, no AI call, D-165, D-189):
the demo builds its history that way. The scores share the row of the transcription's comparison
(`pronunciation_result`) whichever came first; when the assessment comes first it creates the row
with `transcript=""` and `provider=""` (nothing was transcribed), and `speech.store_transcription`
fills it in later. No migration is needed: both columns accept the empty string.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.pronunciation import PronunciationAssessmentOutput
from app.ai.types import AiResult, AiStatus
from app.config import get_settings
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import EventLog, ProductionAttempt, PronunciationResult
from app.db.settings_store import get_setting
from app.domain import pronunciation as pa
from app.domain.enums import ProductionKind
from app.domain.events import EventType, PronunciationAssessed
from app.domain.study_day import as_utc
from app.services.library import LibraryError
from app.services.productions import get_production
from app.services.speech import (
    AudioMissing,
    AudioTooLong,
    clip_of,
    pronunciation_of,
)
from app.speech.audio_store import AudioStore, InvalidAudioPath

SessionFactory = Callable[[], Session]
AssessableReason = Literal[
    "not_shadowing",
    "no_target",
    "no_audio",
    "disabled",
    "not_configured",
    "already_assessed",
    "unsupported_format",
    "too_long",
]

LANGUAGE = "en-US"
NOTE = (
    "Azure's free tier gives about 5 hours of audio a month (limit read on 2026-10-24, it may "
    "change); whether pronunciation assessment itself is included is not confirmed by Microsoft's "
    "pricing page. The scores are an automatic estimate, not a teacher's judgment."
)


class NotAssessable(LibraryError):
    """Not a shadowing, or a shadowing without a target sentence."""

    status, code = 422, "not_assessable"


class AssessmentDisabled(LibraryError):
    status, code = 409, "assessment_disabled"


class AlreadyAssessed(LibraryError):
    status, code = 409, "already_assessed"


class UnsupportedForAssessment(LibraryError):
    status, code = 422, pa.UNSUPPORTED_FOR_ASSESSMENT


@dataclass(frozen=True)
class AssessmentOutcome:
    status: Literal["ok", "silence", "unavailable", "incomplete"]
    # `unavailable`: an `UnavailableReason` (no_provider_configured, quota, auth...); `incomplete`:
    # the provider answered without a usable assessment.
    reason: str | None = None
    scores: dict[str, Any] | None = None  # the stored `azure-pa-1` document, `ok` and `silence`


# --- State ---------------------------------------------------------------------------------------


def azure_configured() -> bool:
    settings = get_settings()
    return settings.azure_speech_key is not None and settings.azure_speech_region is not None


def is_assessed(session: Session, attempt_id: int) -> bool:
    result = pronunciation_of(session, attempt_id)
    return result is not None and result.scores is not None


def assessable_reason(
    session: Session, attempt: ProductionAttempt, *, setting: str, configured: bool
) -> AssessableReason | None:
    """Why a production cannot be assessed now (None: it can). No file is read: the format is
    judged by the extension, the length by the stored duration (`assess` checks the bytes)."""
    if attempt.kind is not ProductionKind.SHADOWING:
        return "not_shadowing"
    if not attempt.prompt_text:
        return "no_target"
    if not attempt.audio_path:
        return "no_audio"
    if setting == "off":
        return "disabled"
    if not configured:
        return "not_configured"
    if is_assessed(session, attempt.id):
        return "already_assessed"
    if Path(attempt.audio_path).suffix.lstrip(".").lower() not in ("wav", "ogg"):
        return "unsupported_format"
    if attempt.audio_seconds is not None and attempt.audio_seconds > pa.MAX_ASSESSMENT_SECONDS:
        return "too_long"
    return None


def assessment_of(session: Session, attempt_id: int) -> dict[str, Any] | None:
    result = pronunciation_of(session, attempt_id)
    return dict(result.scores) if result is not None and result.scores is not None else None


# --- Writing -------------------------------------------------------------------------------------


def store_assessment(
    session: Session,
    attempt_id: int,
    result: AiResult[PronunciationAssessmentOutput],
    *,
    at: datetime,
) -> dict[str, Any]:
    """Write a successful assessment in the caller's transaction (no commit). Returns the stored
    document. Raises ProductionNotFound, NotAssessable, AlreadyAssessed."""
    output = result.data
    if output is None:
        raise ValueError("store_assessment needs a successful result")
    attempt = get_production(session, attempt_id)
    if attempt.kind is not ProductionKind.SHADOWING or not attempt.prompt_text:
        raise NotAssessable("Only a shadowing with a target sentence can be assessed.")
    row = pronunciation_of(session, attempt.id)
    if row is not None and row.scores is not None:
        raise AlreadyAssessed("This recording was already assessed.")
    provider = result.provider or "unknown"
    model = result.model or "unknown"
    document = pa.scores_document(output.model_dump(mode="json"), provider, model, as_utc(at))
    if row is not None:
        row.scores = document
        row.updated_at = at
    else:
        session.add(
            PronunciationResult(
                production_attempt_id=attempt.id,
                target_text=attempt.prompt_text,
                transcript="",  # nothing transcribed yet: `store_transcription` will fill it
                unrecognized_words=[],
                scores=document,
                provider="",
                created_at=at,
                updated_at=at,
            )
        )
    counts = pa.summarize(document["words"])
    overall = document["overall"]
    record_event(
        session,
        PronunciationAssessed(
            production_attempt_id=attempt.id,
            provider=provider,
            model=model,
            ai_call_id=result.call_id,
            status=output.status,
            audio_seconds=attempt.audio_seconds
            if attempt.audio_seconds is not None
            else document["duration_s"],
            accuracy=overall["accuracy"],
            fluency=overall["fluency"],
            completeness=overall["completeness"],
            pronunciation=overall["pronunciation"],
            word_count=len(document["words"]),
            **counts,
        ),
        occurred_at=at,
        study_session_id=attempt.study_session_id,
    )
    session.flush()
    return document


# --- Entry point ---------------------------------------------------------------------------------


def _read(
    session_factory: SessionFactory, store: AudioStore, production_id: int
) -> tuple[str, str, bytes]:
    """The checks of `assess` and the recording's bytes: (target, file name, data)."""
    with session_factory() as session:
        attempt = get_production(session, production_id)  # 1. 404 production_not_found
        if attempt.kind is not ProductionKind.SHADOWING or not attempt.prompt_text:
            raise NotAssessable("Only a shadowing with a target sentence can be assessed.")  # 2.
        target, audio_path, seconds = attempt.prompt_text, attempt.audio_path, attempt.audio_seconds
        path = _file(store, audio_path)  # 3. 404 no_audio
        if get_setting(session, "pronunciation_assessment") == "off":  # 4.
            raise AssessmentDisabled("Pronunciation assessment is turned off in the settings.")
        if is_assessed(session, production_id):  # 5.
            raise AlreadyAssessed("This recording was already assessed.")
        session.rollback()  # nothing stays open from here on
    data = path.read_bytes()
    if pa.audio_problem(data, path.suffix) is not None:  # 6.
        raise UnsupportedForAssessment(
            "Azure reads only WAV (PCM, 16 kHz, mono) and OGG Opus (mono); this one is neither."
        )
    duration = seconds if seconds is not None else pa.audio_duration_s(data)
    if duration is not None and duration > pa.MAX_ASSESSMENT_SECONDS:  # 7.
        raise AudioTooLong(
            f"Pronunciation assessment takes {pa.MAX_ASSESSMENT_SECONDS:g} seconds at most.",
            max_s=pa.MAX_ASSESSMENT_SECONDS,
        )
    return target, path.name, data


def _file(store: AudioStore, audio_path: str | None) -> Path:
    if not audio_path:
        raise AudioMissing("This production has no recording.")
    try:
        path = store.resolve(audio_path)
    except InvalidAudioPath as exc:
        raise AudioMissing("The recording file is missing.") from exc
    if not path.is_file():
        raise AudioMissing("The recording file is missing.")
    return path


def assess(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    production_id: int,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> AssessmentOutcome:
    """Score a stored shadowing (see the module docstring). Raises, before any call and in this
    order: ProductionNotFound (404), NotAssessable (422), AudioMissing (404 `no_audio`),
    AssessmentDisabled (409), AlreadyAssessed (409), UnsupportedForAssessment (422), AudioTooLong
    (422). An AI failure is returned as `unavailable` or `incomplete`."""
    target, name, data = _read(session_factory, store, production_id)
    result = gateway.assess_pronunciation(
        clip_of(data, Path(name).suffix.lstrip("."), name),
        reference_text=target,
        language=LANGUAGE,
    )
    if result.status is not AiStatus.OK or result.data is None:
        if result.status is AiStatus.INCOMPLETE:
            return AssessmentOutcome("incomplete", reason="incomplete")
        reason = result.reason.value if result.reason is not None else None
        return AssessmentOutcome("unavailable", reason=reason)
    with session_factory() as session:
        document = store_assessment(session, production_id, result, at=as_utc(clock()))
        session.commit()
    return AssessmentOutcome(result.data.status, scores=document)


# --- Monthly use of the free quota ----------------------------------------------------


@dataclass(frozen=True)
class MonthlyUsage:
    month: str  # "YYYY-MM" (UTC)
    audio_seconds: float
    assessments: int


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    moment = as_utc(now)
    start = datetime(moment.year, moment.month, 1, tzinfo=UTC)
    following = (
        datetime(moment.year + 1, 1, 1, tzinfo=UTC)
        if moment.month == 12
        else datetime(moment.year, moment.month + 1, 1, tzinfo=UTC)
    )
    return start, following


def monthly_usage(session: Session, now: datetime) -> MonthlyUsage:
    """Audio seconds and number of `pronunciation.assessed` events of the current calendar month
    (UTC), silence included, failed requests not counted: what the owner's own app sent to Azure
    that month, not what Microsoft counts (D-216)."""
    start, following = month_bounds(now)
    payloads = session.scalars(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.PRONUNCIATION_ASSESSED.value,
            EventLog.occurred_at >= start,
            EventLog.occurred_at < following,
        )
    )
    seconds, count = 0.0, 0
    for payload in payloads:
        count += 1
        value = payload.get("audio_seconds")
        seconds += float(value) if isinstance(value, int | float) else 0.0
    return MonthlyUsage(
        month=start.strftime("%Y-%m"), audio_seconds=round(seconds, 3), assessments=count
    )
