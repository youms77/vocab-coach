"""Recordings, their transcription and the word-by-word comparison of a shadowing (module F).

`record` is the core shared by the shadowing (M6.a1), free speaking and the spoken answer of a
review (M6.a2a, `app/services/speaking.py`). Order of operations (D-038, D-169):

1. validate the upload (media type, size, duration bounds; the target sentence of a shadowing)
   before anything is written, then check the terms, the study session and the caller's own
   checks in a short read;
2. write the file (`AudioStore`), then in **one short transaction**, after the same checks again,
   the oral production (`prompt_text` = the target or the topic, `text=""`, `word_count=0`), its
   target terms and `production.recorded`; if that transaction fails the file is deleted;
3. call `gateway.transcribe` with no session open. The clip is sent under its generated name and
   **never with the target sentence as a prompt** (D-172);
4. in a second short transaction (the production is re-checked: still there, not transcribed
   yet), store the text and `production.transcribed`; for a shadowing, the `pronunciation_result`
   and `pronunciation.checked`. A shadowing keeps `word_count = 0` (a repeated sentence holds none
   of the user's own words, the denominator of the error rates); a spoken production gets the
   number of words heard.

An AI failure is a result, not an error (D-081): the production and its audio stay, and
`transcribe_production` can be called again. Silence (no word, or Whisper's segments say so) stores
no text and no comparison. Nothing here records an error: speech recognition is not a
pronunciation judge (D-174).

`store_recording` does steps 1, 2 and 4 in the **caller's** transaction, with a transcription
already obtained (no AI call, no commit): the demo builds its history that way (D-189, as D-165).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult, AiStatus, AudioClip
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import EventLog, ProductionAttempt, ProductionTarget, PronunciationResult
from app.domain.enums import Modality, ProductionKind
from app.domain.events import (
    EventType,
    ProductionOrigin,
    ProductionRecorded,
    ProductionTranscribed,
    PronunciationChecked,
)
from app.domain.speech_compare import Comparison, Unrecognized, compare, words
from app.domain.speech_rules import (
    DURATION_BOUNDS,
    MAX_AUDIO_BYTES,
    MAX_TARGET_CHARS,
    DurationProblem,
    RecordingKind,
    duration_problem,
    is_silence,
)
from app.domain.study_day import as_utc
from app.services.library import LibraryError, get_item
from app.services.productions import get_production
from app.services.study_sessions import require_open
from app.speech.audio_store import (
    ACCEPTED_TYPES,
    AudioStore,
    InvalidAudioPath,
    extension_for,
    served_type,
)

SessionFactory = Callable[[], Session]
# A caller's own checks of a recording (a spoken answer: the card is due...), run before the file is
# written and again inside the transaction that creates the production.
Check = Callable[[Session], object]
TranscriptionState = Literal["pending", "ok", "silence"]
ShadowingOrigin = Literal["shadowing", "discovery"]

LANGUAGE = "en"
_ORIGINS = {"shadowing": ProductionOrigin.SHADOWING, "discovery": ProductionOrigin.DISCOVERY}


class AudioTooLarge(LibraryError):
    status, code = 413, "audio_too_large"


class UnsupportedAudio(LibraryError):
    status, code = 415, "unsupported_audio"


class AudioEmpty(LibraryError):
    status, code = 422, "audio_empty"


class AudioTooShort(LibraryError):
    status, code = 422, "audio_too_short"


class AudioTooLong(LibraryError):
    status, code = 422, "audio_too_long"


class InvalidTarget(LibraryError):
    status, code = 422, "invalid_target"


class NoAudio(LibraryError):
    """The production has no recording (or its file is gone): nothing to transcribe."""

    status, code = 422, "no_audio"


class AudioMissing(LibraryError):
    """Playback of a production without a recording, or whose file is gone."""

    status, code = 404, "no_audio"


class AlreadyTranscribed(LibraryError):
    code = "already_transcribed"


class DurationRequired(LibraryError):
    """No duration from the recorder, and none from the provider (the CLI without `--duration`)."""

    status, code = 422, "duration_required"


# --- Validation ----------------------------------------------------------------------------------


def unsupported_audio() -> UnsupportedAudio:
    return UnsupportedAudio(
        "This audio format is not accepted. Send one of: " + ", ".join(ACCEPTED_TYPES) + "."
    )


def audio_too_large() -> AudioTooLarge:
    return AudioTooLarge(
        f"The recording is larger than {MAX_AUDIO_BYTES // 1024 // 1024} MB.",
        max_bytes=MAX_AUDIO_BYTES,
    )


def check_audio(data: bytes, content_type: str | None) -> str:
    """The file extension of an acceptable upload. Raises UnsupportedAudio, AudioEmpty,
    AudioTooLarge."""
    extension = extension_for(content_type)
    if extension is None:
        raise unsupported_audio()
    if not data:
        raise AudioEmpty("The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise audio_too_large()
    return extension


def check_duration(kind: RecordingKind | ProductionKind, seconds: float) -> None:
    """Raises AudioTooShort, AudioTooLong (with the bounds, for the screen)."""
    problem = duration_problem(kind, seconds)
    if problem is None:
        return
    bounds = DURATION_BOUNDS[kind]
    error = AudioTooShort if problem is DurationProblem.TOO_SHORT else AudioTooLong
    raise error(
        f"A recording lasts from {bounds.min_s:g} to {bounds.max_s:g} seconds.",
        min_s=bounds.min_s,
        max_s=bounds.max_s,
    )


def check_target(text: str) -> str:
    """The target sentence, stripped. Raises InvalidTarget."""
    target = text.strip()
    if len(target) > MAX_TARGET_CHARS:
        raise InvalidTarget(f"The sentence has more than {MAX_TARGET_CHARS} characters.")
    if not words(target):
        raise InvalidTarget("The sentence to repeat has no word.")
    return target


def clip_of(data: bytes, extension: str, name: str) -> AudioClip:
    """What the provider receives: the bytes under a generated name, nothing else."""
    return AudioClip(data=data, filename=name, content_type=served_type(f"x.{extension}"))


# --- Outcomes ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptionOutcome:
    status: Literal["ok", "silence", "unavailable"]
    text: str | None = None  # `ok` only
    # Why it is unavailable: an `UnavailableReason` (no_provider_configured, quota, network...) or
    # `incomplete` (the provider answered without a usable text).
    reason: str | None = None
    comparison: Comparison | None = None


@dataclass(frozen=True)
class SpeechResult:
    production_id: int
    audio_seconds: float | None
    transcription: TranscriptionOutcome


def _failure(result: AiResult[TranscriptionOutput]) -> TranscriptionOutcome:
    if result.status is AiStatus.INCOMPLETE:
        return TranscriptionOutcome("unavailable", reason="incomplete")
    reason = result.reason.value if result.reason is not None else None
    return TranscriptionOutcome("unavailable", reason=reason)


# --- State ---------------------------------------------------------------------------------------


def _transcribed_event(session: Session, attempt_id: int) -> EventLog | None:
    """The `production.transcribed` event of a production: the "already transcribed" marker."""
    return session.scalar(
        select(EventLog)
        .where(
            EventLog.event_type == EventType.PRODUCTION_TRANSCRIBED.value,
            EventLog.entity_type == "production_attempt",
            EventLog.entity_id == attempt_id,
        )
        .order_by(EventLog.id.desc())
        .limit(1)
    )


def transcription_state(session: Session, attempt: ProductionAttempt) -> TranscriptionState | None:
    """`pending` (a recording not transcribed yet), `ok`, `silence`; None without a recording."""
    if not attempt.audio_path:
        return None
    event = _transcribed_event(session, attempt.id)
    if event is None:
        return "pending"
    return "silence" if event.payload.get("status") == "silence" else "ok"


def pronunciation_of(session: Session, attempt_id: int) -> PronunciationResult | None:
    return session.scalar(
        select(PronunciationResult)
        .where(PronunciationResult.production_attempt_id == attempt_id)
        .order_by(PronunciationResult.id.desc())
        .limit(1)
    )


def comparison_of(session: Session, attempt: ProductionAttempt) -> Comparison | None:
    """The word-by-word comparison of a transcribed shadowing, computed again from the stored
    target and transcript (a better comparator improves the old attempts, D-173)."""
    if attempt.kind is not ProductionKind.SHADOWING:
        return None
    result = pronunciation_of(session, attempt.id)
    if result is None or not result.transcript:  # an assessed take not transcribed yet (D-215)
        return None
    return compare(result.target_text, result.transcript)


# --- Writing -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Recording:
    """What a new recording is: its production kind, the bounds of its duration, its prompt (the
    target sentence of a shadowing, the topic or the question of a spoken production), its target
    terms and its origin."""

    kind: ProductionKind
    bounds: RecordingKind
    prompt_text: str | None
    item_ids: tuple[int, ...]
    origin: ProductionOrigin
    study_session_id: int | None


def _check(session: Session, recording: Recording, check: Check | None) -> None:
    """The checks that read the database. Raises ItemNotFound, SessionNotFound, SessionClosed."""
    for item_id in recording.item_ids:
        get_item(session, item_id)
    if recording.study_session_id is not None:
        require_open(session, recording.study_session_id)
    if check is not None:
        check(session)


def _create(
    session: Session,
    recording: Recording,
    *,
    audio_path: str,
    duration_s: float,
    check: Check | None,
    at: datetime,
) -> ProductionAttempt:
    _check(session, recording, check)
    return _insert(session, recording, audio_path=audio_path, duration_s=duration_s, at=at)


def _insert(
    session: Session,
    recording: Recording,
    *,
    audio_path: str,
    duration_s: float,
    at: datetime,
) -> ProductionAttempt:
    attempt = ProductionAttempt(
        kind=recording.kind,
        modality=Modality.ORAL,
        prompt_text=recording.prompt_text,
        text="",
        audio_path=audio_path,
        audio_seconds=duration_s,
        word_count=0,
        study_session_id=recording.study_session_id,
        created_at=at,
        updated_at=at,
    )
    session.add(attempt)
    session.flush()
    for item_id in recording.item_ids:
        session.add(ProductionTarget(production_attempt_id=attempt.id, lexical_item_id=item_id))
    record_event(
        session,
        ProductionRecorded(
            production_attempt_id=attempt.id,
            kind=recording.kind,
            modality=Modality.ORAL,
            word_count=0,
            audio_seconds=duration_s,
            origin=recording.origin,
        ),
        occurred_at=at,
        study_session_id=recording.study_session_id,
    )
    session.flush()
    return attempt


def store_transcription(
    session: Session,
    attempt_id: int,
    result: AiResult[TranscriptionOutput],
    *,
    at: datetime,
) -> TranscriptionOutcome:
    """Write a successful transcription in the caller's transaction (no commit). Raises
    ProductionNotFound, AlreadyTranscribed."""
    output = result.data
    if output is None:
        raise ValueError("store_transcription needs a successful result")
    attempt = get_production(session, attempt_id)
    if _transcribed_event(session, attempt.id) is not None:
        raise AlreadyTranscribed("This recording was already transcribed.")
    text = " ".join(output.text.split())
    heard = words(text)
    segments = [(segment.no_speech_prob, segment.avg_logprob) for segment in output.segments]
    silence = is_silence(len(heard), segments)
    if output.duration_s is not None:
        attempt.audio_seconds = output.duration_s  # the provider's measure wins (D-171)
    attempt.text = "" if silence else text
    if attempt.kind is ProductionKind.SPEAKING:  # the learner's own words (D-175: not a shadowing)
        attempt.word_count = 0 if silence else len(heard)
    attempt.updated_at = at
    provider = result.provider or "unknown"
    record_event(
        session,
        ProductionTranscribed(
            production_attempt_id=attempt.id,
            kind=attempt.kind,
            provider=provider,
            model=result.model or "unknown",
            ai_call_id=result.call_id,
            status="silence" if silence else "ok",
            heard_word_count=0 if silence else len(heard),
            audio_seconds=attempt.audio_seconds,
        ),
        occurred_at=at,
        study_session_id=attempt.study_session_id,
    )
    if silence:
        session.flush()
        return TranscriptionOutcome("silence")
    comparison = None
    if attempt.kind is ProductionKind.SHADOWING and attempt.prompt_text:
        comparison = compare(attempt.prompt_text, text)
        unrecognized = [_unrecognized(u) for u in comparison.unrecognized]
        existing = pronunciation_of(session, attempt.id)
        if existing is not None:
            # A pronunciation assessment came first and created the row (M6.c1, D-215): it keeps
            # its scores and gets the transcription.
            existing.transcript = text
            existing.unrecognized_words = unrecognized
            existing.provider = provider
            existing.updated_at = at
        else:
            session.add(
                PronunciationResult(
                    production_attempt_id=attempt.id,
                    target_text=attempt.prompt_text,
                    transcript=text,
                    unrecognized_words=unrecognized,
                    scores=None,  # filled by `pronunciation.store_assessment` (M6.c1)
                    provider=provider,
                    created_at=at,
                    updated_at=at,
                )
            )
        record_event(
            session,
            PronunciationChecked(
                production_attempt_id=attempt.id,
                target_word_count=comparison.target_word_count,
                recognized_count=comparison.recognized_count,
                unrecognized_count=len(comparison.unrecognized),
                word_accuracy=round(comparison.word_accuracy, 4),
                comparator_version=comparison.version,
                provider=provider,
            ),
            occurred_at=at,
            study_session_id=attempt.study_session_id,
        )
    session.flush()
    return TranscriptionOutcome("ok", text=text, comparison=comparison)


def _unrecognized(word: Unrecognized) -> dict[str, object]:
    return {"position": word.position, "word": word.word, "heard": word.heard}


def _write_transcription(
    session_factory: SessionFactory,
    attempt_id: int,
    result: AiResult[TranscriptionOutput],
    at: datetime,
) -> tuple[TranscriptionOutcome, float | None]:
    with session_factory() as session:
        outcome = store_transcription(session, attempt_id, result, at=at)
        seconds = get_production(session, attempt_id).audio_seconds
        session.commit()
    return outcome, seconds


# --- Entry points --------------------------------------------------------------------------------


def _validated(
    recording: Recording,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput] | None,
) -> tuple[str, float]:
    """The extension and the duration of an acceptable upload (the given transcription's duration
    when none is given). Raises UnsupportedAudio, AudioEmpty, AudioTooLarge, DurationRequired,
    AudioTooShort, AudioTooLong."""
    extension = check_audio(data, content_type)
    if duration_s is None and transcription is not None and transcription.data is not None:
        duration_s = transcription.data.duration_s
    if duration_s is None:
        raise DurationRequired("Give the duration of the recording.")
    check_duration(recording.bounds, duration_s)
    return extension, duration_s


def shadowing_recording(
    target_text: str,
    *,
    item_id: int | None = None,
    origin: ShadowingOrigin = "shadowing",
    study_session_id: int | None = None,
) -> Recording:
    """What a shadowing is: its target sentence (stripped), its term and its origin. Raises
    InvalidTarget."""
    return Recording(
        kind=ProductionKind.SHADOWING,
        bounds=RecordingKind.SHADOWING,
        prompt_text=check_target(target_text),
        item_ids=(item_id,) if item_id is not None else (),
        origin=_ORIGINS[origin],
        study_session_id=study_session_id,
    )


def store_recording(
    session: Session,
    store: AudioStore,
    recording: Recording,
    *,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput],
    check: Check | None = None,
    at: datetime,
) -> SpeechResult:
    """A recording and its transcription, already obtained, in the caller's transaction (no commit,
    no AI call; the demo, D-189). The same checks as `record` run before the file is written; if a
    later write raises, the file is deleted (the caller rolls its transaction back). A failed
    `transcription` leaves the recording to transcribe. Raises as `record`."""
    extension, duration_s = _validated(recording, data, content_type, duration_s, transcription)
    at = as_utc(at)
    _check(session, recording, check)
    audio_path = store.save(data, extension, at=at)
    try:
        attempt = _insert(session, recording, audio_path=audio_path, duration_s=duration_s, at=at)
        if transcription.status is not AiStatus.OK or transcription.data is None:
            return SpeechResult(attempt.id, attempt.audio_seconds, _failure(transcription))
        outcome = store_transcription(session, attempt.id, transcription, at=at)
    except BaseException:
        store.delete(audio_path)
        raise
    return SpeechResult(attempt.id, attempt.audio_seconds, outcome)


def transcribe_clip(gateway: Gateway, data: bytes, extension: str) -> AiResult[TranscriptionOutput]:
    """Transcribe an upload before anything is stored (the CLI without `--duration`). The clip goes
    under a neutral generated name."""
    return gateway.transcribe(clip_of(data, extension, f"recording.{extension}"), language=LANGUAGE)


def record(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    recording: Recording,
    *,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput] | None = None,
    check: Check | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> SpeechResult:
    """Store a recording, then transcribe it (and compare a shadowing): see the module docstring.

    `transcription` is a result already obtained for these bytes (`transcribe_clip`): it is stored
    instead of calling the provider again. Without `duration_s`, its duration is used. Raises
    UnsupportedAudio, AudioEmpty, AudioTooLarge, DurationRequired, AudioTooShort, AudioTooLong,
    ItemNotFound, SessionNotFound, SessionClosed (and whatever `check` raises); nothing is stored
    then."""
    extension, duration_s = _validated(recording, data, content_type, duration_s, transcription)
    with session_factory() as session:  # refuse before the file is written
        _check(session, recording, check)
        session.rollback()
    at = as_utc(clock())
    audio_path = store.save(data, extension, at=at)
    try:
        with session_factory() as session:
            attempt = _create(
                session,
                recording,
                audio_path=audio_path,
                duration_s=duration_s,
                check=check,
                at=at,
            )
            attempt_id = attempt.id
            session.commit()
    except BaseException:
        store.delete(audio_path)
        raise
    if transcription is None:
        clip = clip_of(data, extension, Path(audio_path).name)
        transcription = gateway.transcribe(clip, language=LANGUAGE)
    return _finish(session_factory, attempt_id, transcription, duration_s, clock)


def record_shadowing(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    *,
    data: bytes,
    content_type: str | None,
    target_text: str,
    duration_s: float | None,
    item_id: int | None = None,
    origin: ShadowingOrigin = "shadowing",
    study_session_id: int | None = None,
    transcription: AiResult[TranscriptionOutput] | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> SpeechResult:
    """Store a shadowing recording, then transcribe and compare it (see the module docstring).

    `transcription` is a result already obtained for these bytes (`transcribe_clip`): it is stored
    instead of calling the provider again. Without `duration_s`, its duration is used. Raises
    UnsupportedAudio, AudioEmpty, AudioTooLarge, InvalidTarget, DurationRequired, AudioTooShort,
    AudioTooLong, ItemNotFound, SessionNotFound, SessionClosed; nothing is stored then."""
    check_audio(data, content_type)
    recording = shadowing_recording(
        target_text, item_id=item_id, origin=origin, study_session_id=study_session_id
    )
    return record(
        session_factory,
        gateway,
        store,
        recording,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        transcription=transcription,
        clock=clock,
    )


def transcribe_production(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    production_id: int,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> SpeechResult:
    """Transcribe again a recording that has no transcription yet (after an AI failure). Raises
    ProductionNotFound, NoAudio, AlreadyTranscribed."""
    with session_factory() as session:
        attempt = get_production(session, production_id)
        audio_path = attempt.audio_path
        seconds = attempt.audio_seconds
        if not audio_path:
            raise NoAudio("This production has no recording.")
        if _transcribed_event(session, attempt.id) is not None:
            raise AlreadyTranscribed("This recording was already transcribed.")
        session.rollback()  # nothing stays open during the AI call
    try:
        path = store.resolve(audio_path)
        data = path.read_bytes()
    except (InvalidAudioPath, OSError) as exc:
        raise NoAudio("The recording file is missing.") from exc
    clip = clip_of(data, path.suffix.lstrip("."), path.name)
    result = gateway.transcribe(clip, language=LANGUAGE)
    return _finish(session_factory, production_id, result, seconds, clock)


def _finish(
    session_factory: SessionFactory,
    attempt_id: int,
    result: AiResult[TranscriptionOutput],
    seconds: float | None,
    clock: Callable[[], datetime],
) -> SpeechResult:
    if result.status is not AiStatus.OK or result.data is None:
        return SpeechResult(attempt_id, seconds, _failure(result))
    outcome, seconds = _write_transcription(session_factory, attempt_id, result, as_utc(clock()))
    return SpeechResult(attempt_id, seconds, outcome)
