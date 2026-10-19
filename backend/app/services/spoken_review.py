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
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult
from app.db.base import utcnow
from app.domain import exercises as ex
from app.domain.events import ProductionOrigin
from app.domain.grading import production_rating, production_warnings
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.speech_rules import RecordingKind
from app.domain.study_day import as_utc
from app.services import productions, review_flow, speaking, study_sessions
from app.services.corrections import CorrectionResult
from app.services.productions import TextTooLongError
from app.services.speech import TranscriptionOutcome
from app.speech.audio_store import AudioStore

SessionFactory = Callable[[], Session]
Status = Literal["ok", "incomplete", "unavailable"]


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
        ctx = review_flow.card_context(session, card_id, ex.SPOKEN_ANSWER, exercise_template_id)
        assert ctx.card is not None  # noqa: S101 (a card context always has its card)
        review_flow.require_due(session, ctx.card, now)
        if ctx.item.status not in REVIEWABLE_STATUSES:
            raise review_flow.ReviewRefused(
                f"Term {ctx.item.id} is {ctx.item.status}: its cards are not reviewed."
            )
        study_sessions.require_open(session, study_session_id)
        return ctx

    with session_factory() as session:
        ctx = review_checks(session)
        question = str((ctx.content or {}).get("question") or "")
        solution, summary = review_flow.solution_and_summary(ctx)
        item_id = ctx.item.id
        session.rollback()

    recorded = speaking.record_speaking(
        session_factory,
        gateway,
        store,
        data=data,
        content_type=content_type,
        duration_s=duration_s,
        prompt_text=question,
        target_item_ids=[item_id],
        study_session_id=study_session_id,
        transcription=transcription,
        bounds=RecordingKind.SPOKEN_ANSWER,
        origin=ProductionOrigin.REVIEW,
        check=review_checks,
        clock=clock,
    )

    def without_rating(status: Status, reason: str | None) -> SpokenCheck:
        return SpokenCheck(
            production_id=recorded.production_id,
            transcription=recorded.transcription,
            status=status,
            reason=reason,
            correction=None,
            proposed_rating=None,
            warnings=[],
            solution=solution,
            sheet_summary=summary,
        )

    heard = recorded.transcription
    if heard.status == "unavailable":
        return without_rating("unavailable", heard.reason)
    if heard.status == "silence":
        return without_rating("unavailable", "silence")
    try:
        result = speaking.correct_speaking(
            session_factory, gateway, recorded.production_id, clock=clock
        )
    except TextTooLongError:  # a transcription of more than 4 000 characters: kept, not corrected
        return without_rating("unavailable", "text_too_long")
    if result.status != "ok":
        reason = str(result.reason) if result.reason is not None else None
        return without_rating(result.status, reason)
    with session_factory() as session:
        feedback = productions.get_production(session, recorded.production_id).ai_feedback
        rating = production_rating(feedback, item_id)
        warnings = production_warnings(feedback, item_id)
        session.rollback()
    return SpokenCheck(
        production_id=recorded.production_id,
        transcription=heard,
        status="ok",
        reason=None,
        correction=result,
        proposed_rating=int(rating) if rating is not None else None,
        warnings=warnings,
        solution=solution,
        sheet_summary=summary,
    )
