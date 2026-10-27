"""Productions of a consolidation task and their correction (module G, M7.a2).

Written (`record_written`): a production `kind=consolidation`, `modality=written`, `prompt_text` =
the English prompt of the task, the terms of the task as targets (`used` is computed from the text
when it is corrected, as in M5), `production.recorded` (version 6, origin `consolidation`). Same
limits as free writing (4 000 characters, 40 sentences).

Spoken (`record_spoken`): the path of free speaking (D-182) with the bounds of
`RecordingKind.CONSOLIDATION` (20 to 240 s); the checks run before the file is written and again
in the creating transaction; the task prompt is never sent to the recogniser (D-172).

In both cases the first attempt makes a `proposed` task `accepted`, in the creating transaction,
and an attempt on a `completed` or `dismissed` task is 409 `task_closed`.

Correction (`correct_consolidation`): a written text goes through `production_correction` in
`paragraph` mode, a spoken one through `speaking_correction` in `monologue` mode; the errors have
the source `consolidation`. The result is applied to the terms of the task
(`consolidation.apply_result`) in the **same write transaction** as the correction, so a
correction that is not stored changes no status, and a retry applies it once.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult
from app.db.base import utcnow
from app.db.models import ProductionAttempt
from app.domain.enums import Modality, ProductionKind
from app.domain.events import ProductionOrigin
from app.domain.speech_rules import RecordingKind
from app.services import consolidation, corrections, productions, speaking, speech
from app.services.corrections import CorrectionResult
from app.services.library import LibraryError
from app.speech.audio_store import AudioStore

SessionFactory = Callable[[], Session]
KINDS = (ProductionKind.CONSOLIDATION,)


class NotAConsolidationAttempt(LibraryError):
    status, code = 422, "not_correctable"


def _prompt_of(session: Session, task_id: int) -> str:
    task = consolidation.get_task(session, task_id)
    return str((task.suggested_structure or {}).get("prompt", {}).get("en", task.topic))


def record_written(
    session: Session,
    task_id: int,
    *,
    text: str,
    study_session_id: int | None,
    at: datetime,
) -> ProductionAttempt:
    """A written production for a task, in the caller's transaction (no commit). Raises
    TaskNotFound, TaskClosed, InvalidProduction, TextTooLongError, SessionNotFound."""
    consolidation.ensure_open(session, task_id)
    attempt = productions.create_writing(
        session,
        text=text,
        prompt=_prompt_of(session, task_id),
        target_item_ids=consolidation.task_item_ids(session, task_id),
        study_session_id=study_session_id,
        at=at,
        origin=ProductionOrigin.CONSOLIDATION,
        kind=ProductionKind.CONSOLIDATION,
        consolidation_task_id=task_id,
    )
    consolidation.note_attempt(session, task_id, at)
    return attempt


def record_spoken(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    task_id: int,
    *,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    study_session_id: int | None = None,
    transcription: AiResult[TranscriptionOutput] | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> speech.SpeechResult:
    """A recorded talk for a task, stored and transcribed (not corrected: `correct_consolidation`
    does it). Raises as `speaking.record_speaking`, plus TaskNotFound and TaskClosed; nothing is
    stored then."""
    speech.check_audio(data, content_type)
    with session_factory() as session:
        consolidation.ensure_open(session, task_id)
        prompt = _prompt_of(session, task_id)
        item_ids = tuple(consolidation.task_item_ids(session, task_id))
        session.rollback()
    recording = speech.Recording(
        kind=ProductionKind.CONSOLIDATION,
        bounds=RecordingKind.CONSOLIDATION,
        prompt_text=speaking.check_prompt(prompt),
        item_ids=item_ids,
        origin=ProductionOrigin.CONSOLIDATION,
        study_session_id=study_session_id,
        consolidation_task_id=task_id,
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
        check=lambda session: consolidation.ensure_open(session, task_id),
        clock=clock,
    )


def correct_consolidation(
    session_factory: SessionFactory,
    gateway: Gateway,
    attempt_id: int,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> CorrectionResult:
    """Correct a consolidation production and apply the result (see the module docstring).
    Raises ProductionNotFound, NotCorrectable, AlreadyCorrected, NotTranscribed, NothingToCorrect,
    TextTooLongError. An AI failure is a result: nothing is written, no status changes."""
    with session_factory() as session:
        attempt = productions.get_production(session, attempt_id)
        if attempt.kind is not ProductionKind.CONSOLIDATION:
            raise NotAConsolidationAttempt("This is not a consolidation production.")
        oral = attempt.modality is Modality.ORAL
        session.rollback()

    def after_store(session: Session) -> dict | None:
        return consolidation.apply_result(session, attempt_id, clock())

    if oral:
        return speaking.correct_speaking(
            session_factory,
            gateway,
            attempt_id,
            kinds=KINDS,
            after_store=after_store,
            clock=clock,
        )
    return corrections.correct_production(
        session_factory,
        gateway,
        attempt_id,
        mode="paragraph",
        kinds=KINDS,
        after_store=after_store,
        clock=clock,
    )
