"""Free speaking and the correction of a transcription (module F, M6.a2a).

Recording (`record_speaking`): the same steps as a shadowing (`app/services/speech.py`, D-169):
the upload and the request are checked before anything is written, the file is written, then a
short transaction creates the production (`kind=speaking`, `modality=oral`, `prompt_text` = the
topic, target terms with `used = null`) and `production.recorded` (version 5, origin `speaking`,
or `review` for a spoken answer). The clip is transcribed with no session open, **never with the
topic or an expected answer as a prompt** (D-172); a second short transaction stores the text,
whose words become `word_count` (the denominator of the error rates).

Correction (`correct_speaking`), D-038:

1. a short read: the production must be a transcribed `speaking` production not corrected yet;
   its text is cut into at most 40 units (`speech_units`); the session is closed;
2. the AI call (`speaking_correction`) with no session open;
3. `ok`: one short write transaction that checks the production again, then writes the feedback
   (`format: "speaking-1"`, the `correction-1` keys plus `structure`), the target checks, one error
   event per error and `production.corrected` (`corrections.store_speaking_correction`);
4. `incomplete` or `unavailable`: nothing is written; it can be corrected again.

The mode and the source of the errors follow the origin of the recording: a spoken answer in a
review (`origin: review`) is corrected in `answer` mode and its errors have the source `review`;
anything else is a `monologue` whose errors have the source `speaking`. A retry through
`POST /productions/{id}/correct` therefore keeps them. The correction is about what the recogniser
heard: Whisper may smooth over a mistake, or mishear a word.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.schemas.speaking_correction import Mode, SpeakingCorrectionOutput, speaking_context
from app.ai.tasks import speaking_output_budget
from app.ai.types import AiResult, AiStatus
from app.db.base import utcnow
from app.domain.enums import ErrorSource, ProductionKind
from app.domain.events import ProductionOrigin
from app.domain.speech_rules import MAX_SPEAKING_CHARS, RecordingKind, speech_units
from app.domain.study_day import as_utc
from app.services import corrections, productions, speech, transcripts
from app.services.corrections import AlreadyCorrected, CorrectionResult, NotCorrectable
from app.services.library import LibraryError
from app.services.productions import InvalidProduction, TextTooLongError
from app.speech.audio_store import AudioStore

TASK = "speaking_correction"

SessionFactory = Callable[[], Session]


class NotTranscribed(LibraryError):
    """The recording has no transcription yet (it failed, or never ran): transcribe it first."""

    code = "not_transcribed"


class NothingToCorrect(LibraryError):
    """The transcription heard nothing (silence)."""

    status, code = 422, "nothing_to_correct"


# --- Recording -----------------------------------------------------------------------------------


def check_prompt(prompt_text: str | None) -> str | None:
    """The topic, stripped (None when empty). Raises InvalidProduction."""
    prompt = (prompt_text or "").strip() or None
    if prompt is not None and len(prompt) > productions.MAX_PROMPT_CHARS:
        raise InvalidProduction(
            f"The topic has more than {productions.MAX_PROMPT_CHARS} characters."
        )
    return prompt


def _checked_targets(target_item_ids: Sequence[int]) -> tuple[int, ...]:
    ids = tuple(dict.fromkeys(target_item_ids))
    if len(ids) > productions.MAX_TARGETS:
        raise InvalidProduction(f"At most {productions.MAX_TARGETS} target terms.")
    return ids


def speaking_recording(
    *,
    prompt_text: str | None,
    target_item_ids: Sequence[int],
    study_session_id: int | None,
    bounds: RecordingKind = RecordingKind.SPEAKING,
    origin: ProductionOrigin = ProductionOrigin.SPEAKING,
) -> speech.Recording:
    """What a spoken production is: free speaking by default, a spoken answer with the bounds and
    the origin of a review. Raises InvalidProduction."""
    return speech.Recording(
        kind=ProductionKind.SPEAKING,
        bounds=bounds,
        prompt_text=check_prompt(prompt_text),
        item_ids=_checked_targets(target_item_ids),
        origin=origin,
        study_session_id=study_session_id,
    )


def store_speaking(
    session: Session,
    store: AudioStore,
    *,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput],
    prompt_text: str | None = None,
    target_item_ids: Sequence[int] = (),
    study_session_id: int | None = None,
    at: datetime,
) -> speech.SpeechResult:
    """Free speaking and its transcription, already obtained, in the caller's transaction (no
    commit, no AI call; the demo, D-189). `prepare_speaking` and
    `corrections.store_speaking_correction` then correct it the same way. Raises as
    `record_speaking`."""
    speech.check_audio(data, content_type)
    recording = speaking_recording(
        prompt_text=prompt_text,
        target_item_ids=target_item_ids,
        study_session_id=study_session_id,
    )
    return speech.store_recording(
        session,
        store,
        recording,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        transcription=transcription,
        at=at,
    )


def record_speaking(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    *,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    prompt_text: str | None = None,
    target_item_ids: Sequence[int] = (),
    study_session_id: int | None = None,
    transcription: AiResult[TranscriptionOutput] | None = None,
    bounds: RecordingKind = RecordingKind.SPEAKING,
    origin: ProductionOrigin = ProductionOrigin.SPEAKING,
    check: speech.Check | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> speech.SpeechResult:
    """Store a spoken production and transcribe it (see the module docstring). Nothing is
    corrected yet: `correct_speaking` does it.

    `transcription` is a result already obtained for these bytes (the CLI without `--duration`);
    `bounds`, `origin` and `check` serve the spoken answer of a review (`spoken_review.py`): its
    checks run again just before the file is written and inside the creating transaction. Raises
    UnsupportedAudio, AudioEmpty, AudioTooLarge, InvalidProduction, DurationRequired,
    AudioTooShort, AudioTooLong, ItemNotFound, SessionNotFound, SessionClosed (and whatever
    `check` raises); nothing is stored then."""
    speech.check_audio(data, content_type)
    recording = speaking_recording(
        prompt_text=prompt_text,
        target_item_ids=target_item_ids,
        study_session_id=study_session_id,
        bounds=bounds,
        origin=origin,
    )
    return speech.record(
        session_factory,
        gateway,
        store,
        recording,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        transcription=transcription,
        check=check,
        clock=clock,
    )


# --- Correction: reading (step 1) ----------------------------------------------------------------


@dataclass(frozen=True)
class PreparedSpeech:
    correction: corrections.Prepared  # the units as `sentences`
    mode: Mode


def mode_and_source(session: Session, attempt_id: int) -> tuple[Mode, ErrorSource]:
    """`answer` and `review` for a spoken answer of a review, else `monologue` and `speaking`."""
    if corrections.recorded_origin(session, attempt_id) == ProductionOrigin.REVIEW.value:
        return "answer", ErrorSource.REVIEW
    return "monologue", ErrorSource.SPEAKING


def prepare_speaking(session: Session, attempt_id: int) -> PreparedSpeech:
    """Everything the call needs, refused before any AI call. Raises ProductionNotFound,
    NotCorrectable, AlreadyCorrected, NotTranscribed, NothingToCorrect, TextTooLongError."""
    attempt = productions.get_production(session, attempt_id)
    if attempt.kind is not ProductionKind.SPEAKING:
        raise NotCorrectable("Only a spoken production can be corrected here.")
    if attempt.ai_feedback is not None:
        raise AlreadyCorrected("This production was already corrected.")
    state = speech.transcription_state(session, attempt)
    if state not in ("ok", "silence"):
        raise NotTranscribed("This recording has no transcription yet: transcribe it first.")
    units = speech_units(attempt.text)
    if state == "silence" or not units:
        raise NothingToCorrect("Nothing was heard in this recording: there is nothing to correct.")
    if len(attempt.text) > MAX_SPEAKING_CHARS:
        raise TextTooLongError(
            f"The transcription has {len(attempt.text)} characters; at most "
            f"{MAX_SPEAKING_CHARS} are corrected."
        )
    mode, source = mode_and_source(session, attempt.id)
    prepared = corrections.Prepared(
        attempt_id=attempt.id,
        text=attempt.text,
        prompt=corrections.prompt_line(attempt.prompt_text),
        source=source,
        sentences=units,
        targets=corrections.targets_for(session, attempt.id),
        # Spelling is the recogniser's, and pronunciation cannot be judged from a transcription.
        taxonomy=transcripts.allowed_taxonomy(session),
    )
    return PreparedSpeech(prepared, mode)


# --- Entry point ---------------------------------------------------------------------------------


def correct_speaking(
    session_factory: SessionFactory,
    gateway: Gateway,
    attempt_id: int,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> CorrectionResult:
    """Correct a transcribed spoken production (see the module docstring). Raises
    ProductionNotFound, NotCorrectable, AlreadyCorrected, NotTranscribed, NothingToCorrect,
    TextTooLongError. An AI failure is a result: nothing is written."""
    with session_factory() as session:
        speech_to_correct = prepare_speaking(session, attempt_id)
        session.rollback()  # nothing stays open during the AI call
    prepared, mode = speech_to_correct.correction, speech_to_correct.mode
    result = gateway.generate_json(
        TASK,
        corrections.task_inputs(prepared, mode),
        SpeakingCorrectionOutput,
        validation_context=speaking_context(
            {unit.index: unit.text for unit in prepared.sentences},
            set(prepared.taxonomy),
            {target.ref for target in prepared.targets},
            mode,
            prepared.text,
        ),
        max_output_tokens=speaking_output_budget(len(prepared.sentences)),
    )
    if result.status is not AiStatus.OK or result.data is None:
        status: Literal["incomplete", "unavailable"] = (
            "incomplete" if result.status is AiStatus.INCOMPLETE else "unavailable"
        )
        return CorrectionResult(status, result.reason, attempt_id, detail=result.detail)
    with session_factory() as session:
        written = corrections.store_speaking_correction(
            session,
            prepared,
            result.data,
            source=prepared.source,
            provenance=(result.provider, result.model, result.prompt_version),
            ai_call_id=result.call_id,
            at=as_utc(clock()),
        )
        session.commit()
    return CorrectionResult(
        "ok",
        None,
        attempt_id,
        error_ids=written.error_ids,
        proposed_category_ids=written.proposed_ids,
    )
