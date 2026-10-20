"""A `spoken_answer` review checked by transcription and the AI (modules C and F, M6.a2a).

`check_spoken_answer` is called after the learner recorded their answer and before they rate it.
Every refusal comes **before any write and any AI call**, in this order: the card and its exercise
(404 `card_not_found`, 422 `exercise_mismatch`), the card is due (409 `not_due`), its term is
reviewable (409 `review_not_allowed`), the study session is open (404 `session_not_found`, 409
`session_closed`), then the recording (422 `audio_empty`, `audio_too_short`, `audio_too_long`; 415
and 413 come even earlier, while the body is read). Then three short transactions, none open
during an AI call (D-038):

1. the recording, as a `speaking` production (prompt = the question, target = the term,
   `origin: review`), after the same checks again (`speech.record`);
2. its transcription (Groq Whisper, never with the question or the example answer as a prompt,
   D-172);
3. its correction in `answer` mode (`speaking.correct_speaking`); its errors have the source
   `review`.

A failed transcription keeps the recording (`status: unavailable` with the transcription's
reason); silence gives `unavailable` / `silence`, a transcription too long to be corrected
`unavailable` / `text_too_long`; a failed correction keeps the transcription.
Each of these leaves the review self-graded. The solution (the example answer) is returned only
now that the attempt was made (D-103). Nothing here rates the card: `POST /api/reviews` gives the
production id back and computes the proposed rating again from the stored feedback (D-129).

`store_spoken_answer` does the same in the **caller's** transaction (no commit), with a
transcription already obtained and an injected corrector instead of the AI: the demo (D-189).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.schemas.speaking_correction import SpeakingCorrectionOutput
from app.ai.types import AiResult
from app.db.base import utcnow
from app.domain import exercises as ex
from app.domain.events import ProductionOrigin
from app.domain.grading import production_rating, production_warnings
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.speech_rules import RecordingKind
from app.domain.study_day import as_utc
from app.services import corrections, productions, review_flow, speaking, speech, study_sessions
from app.services.corrections import CorrectionResult
from app.services.productions import TextTooLongError
from app.services.speech import SpeechResult, TranscriptionOutcome
from app.speech.audio_store import AudioStore

SessionFactory = Callable[[], Session]
Status = Literal["ok", "incomplete", "unavailable"]
# The demo's stand-in for the `speaking_correction` call: the output for the prepared answer.
Corrector = Callable[[speaking.PreparedSpeech], SpeakingCorrectionOutput]


@dataclass(frozen=True)
class SpokenCheck:
    production_id: int
    transcription: TranscriptionOutcome
    status: Status
    # Why there is no correction: the transcription's reason (`no_provider_configured`, `quota`,
    # `network`..., `incomplete`), `silence`, or the correction's reason.
    reason: str | None
    correction: CorrectionResult | None  # `ok` only
    proposed_rating: int | None
    warnings: list[str]
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


def answer_context(
    session: Session,
    *,
    card_id: int,
    exercise_template_id: int,
    study_session_id: int,
    now: datetime,
) -> review_flow.ExerciseContext:
    """The checks of a spoken answer, in the order of the module docstring. Raises CardNotFound,
    ExerciseMismatch, NotDue, ReviewRefused, SessionNotFound, SessionClosed."""
    ctx = review_flow.card_context(session, card_id, ex.SPOKEN_ANSWER, exercise_template_id)
    assert ctx.card is not None  # noqa: S101 (a card context always has its card)
    review_flow.require_due(session, ctx.card, now)
    if ctx.item.status not in REVIEWABLE_STATUSES:
        raise review_flow.ReviewRefused(
            f"Term {ctx.item.id} is {ctx.item.status}: its cards are not reviewed."
        )
    study_sessions.require_open(session, study_session_id)
    return ctx


@dataclass(frozen=True)
class _Answer:
    """What the checks give the recording and the result: the question, the term, the solution."""

    question: str
    item_id: int
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


def _answer_of(ctx: review_flow.ExerciseContext) -> _Answer:
    solution, summary = review_flow.solution_and_summary(ctx)
    question = str((ctx.content or {}).get("question") or "")
    return _Answer(question, ctx.item.id, solution, summary)


def _without_rating(
    answer: _Answer, recorded: SpeechResult, status: Status, reason: str | None
) -> SpokenCheck:
    return SpokenCheck(
        production_id=recorded.production_id,
        transcription=recorded.transcription,
        status=status,
        reason=reason,
        correction=None,
        proposed_rating=None,
        warnings=[],
        solution=answer.solution,
        sheet_summary=answer.sheet_summary,
    )


def _not_correctable(answer: _Answer, recorded: SpeechResult) -> SpokenCheck | None:
    """The result when the transcription failed or heard nothing, else None."""
    heard = recorded.transcription
    if heard.status == "unavailable":
        return _without_rating(answer, recorded, "unavailable", heard.reason)
    if heard.status == "silence":
        return _without_rating(answer, recorded, "unavailable", "silence")
    return None


def _rated(
    session: Session, answer: _Answer, recorded: SpeechResult, result: CorrectionResult
) -> SpokenCheck:
    feedback = productions.get_production(session, recorded.production_id).ai_feedback
    rating = production_rating(feedback, answer.item_id)
    return SpokenCheck(
        production_id=recorded.production_id,
        transcription=recorded.transcription,
        status="ok",
        reason=None,
        correction=result,
        proposed_rating=int(rating) if rating is not None else None,
        warnings=production_warnings(feedback, answer.item_id),
        solution=answer.solution,
        sheet_summary=answer.sheet_summary,
    )


def check_spoken_answer(
    session_factory: SessionFactory,
    gateway: Gateway,
    store: AudioStore,
    *,
    card_id: int,
    study_session_id: int,
    exercise_template_id: int,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput] | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> SpokenCheck:
    """Record, transcribe and correct a spoken answer (see the module docstring). `transcription`
    is a result already obtained for these bytes. Raises CardNotFound, ExerciseMismatch, NotDue,
    ReviewRefused, SessionNotFound, SessionClosed, then the recording's refusals; nothing is
    stored then. A failed transcription or correction is a result."""
    now = as_utc(clock())

    def review_checks(session: Session) -> review_flow.ExerciseContext:
        return answer_context(
            session,
            card_id=card_id,
            exercise_template_id=exercise_template_id,
            study_session_id=study_session_id,
            now=now,
        )

    with session_factory() as session:
        answer = _answer_of(review_checks(session))
        session.rollback()

    recorded = speaking.record_speaking(
        session_factory,
        gateway,
        store,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        prompt_text=answer.question,
        target_item_ids=[answer.item_id],
        study_session_id=study_session_id,
        transcription=transcription,
        bounds=RecordingKind.SPOKEN_ANSWER,
        origin=ProductionOrigin.REVIEW,
        check=review_checks,
        clock=clock,
    )
    refused = _not_correctable(answer, recorded)
    if refused is not None:
        return refused
    try:
        result = speaking.correct_speaking(
            session_factory, gateway, recorded.production_id, clock=clock
        )
    except TextTooLongError:  # a transcription of more than 4 000 characters: kept, not corrected
        return _without_rating(answer, recorded, "unavailable", "text_too_long")
    if result.status != "ok":
        reason = str(result.reason) if result.reason is not None else None
        return _without_rating(answer, recorded, result.status, reason)
    with session_factory() as session:
        checked = _rated(session, answer, recorded, result)
        session.rollback()
    return checked


def store_spoken_answer(
    session: Session,
    store: AudioStore,
    *,
    card_id: int,
    study_session_id: int,
    exercise_template_id: int,
    data: bytes,
    content_type: str | None,
    duration_s: float | None,
    transcription: AiResult[TranscriptionOutput],
    correct: Corrector,
    provenance: tuple[str | None, str | None, str | None],
    at: datetime,
) -> SpokenCheck:
    """`check_spoken_answer` in the caller's transaction (no commit, no AI call; the demo, D-189):
    the same checks, the recording with its given transcription, then the output of `correct`
    stored as the correction (`answer` mode, source `review`). Raises as
    `check_spoken_answer`."""
    at = as_utc(at)

    def review_checks(checked: Session) -> review_flow.ExerciseContext:
        return answer_context(
            checked,
            card_id=card_id,
            exercise_template_id=exercise_template_id,
            study_session_id=study_session_id,
            now=at,
        )

    answer = _answer_of(review_checks(session))
    recording = speaking.speaking_recording(
        prompt_text=answer.question,
        target_item_ids=[answer.item_id],
        study_session_id=study_session_id,
        bounds=RecordingKind.SPOKEN_ANSWER,
        origin=ProductionOrigin.REVIEW,
    )
    recorded = speech.store_recording(
        session,
        store,
        recording,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        transcription=transcription,
        at=at,
    )
    refused = _not_correctable(answer, recorded)
    if refused is not None:
        return refused
    try:
        prepared = speaking.prepare_speaking(session, recorded.production_id)
    except TextTooLongError:
        return _without_rating(answer, recorded, "unavailable", "text_too_long")
    written = corrections.store_speaking_correction(
        session,
        prepared.correction,
        correct(prepared),
        source=prepared.correction.source,
        provenance=provenance,
        ai_call_id=None,
        at=at,
    )
    result = CorrectionResult(
        "ok",
        None,
        recorded.production_id,
        error_ids=written.error_ids,
        proposed_category_ids=written.proposed_ids,
    )
    return _rated(session, answer, recorded, result)
