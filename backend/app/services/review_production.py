"""A `sentence_production` review checked by the AI (modules C and E, M5.a1).

`check_production` is called after the learner wrote their sentence and before they rate it:

1. in a short transaction, check the session, the card and the exercise, record the sentence as a
   written production (prompt = the situation, target = the term, `origin: review`), and keep the
   solution to return;
2. correct it in `sentence` mode (`corrections.correct_production`, no transaction open during the
   AI call); its errors have the source `review`;
3. return the production, the correction (or why there is none) and the proposed rating.

The solution (the example answer) is part of the answer only because the attempt was made (D-103).
Nothing here rates the card: the review is recorded later by `POST /api/reviews`, which gives the
production id back and computes the proposed rating again from the stored feedback (D-128).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.db.base import utcnow
from app.domain import exercises as ex
from app.domain.events import ProductionOrigin
from app.domain.grading import production_rating
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.study_day import as_utc
from app.services import corrections, productions, review_flow, study_sessions

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ProductionCheck:
    result: corrections.CorrectionResult
    proposed_rating: int | None
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


def check_production(
    session_factory: SessionFactory,
    gateway: Gateway,
    *,
    card_id: int,
    study_session_id: int,
    exercise_template_id: int,
    answer: str,
    clock: Callable[[], datetime] = utcnow,
) -> ProductionCheck:
    """Record and correct the sentence. Raises SessionNotFound, SessionClosed, CardNotFound,
    ExerciseMismatch, ReviewRefused, InvalidProduction. An AI failure is a result."""
    with session_factory() as session:
        study = study_sessions.require_open(session, study_session_id)
        ctx = review_flow.card_context(
            session, card_id, ex.SENTENCE_PRODUCTION, exercise_template_id
        )
        if ctx.item.status not in REVIEWABLE_STATUSES:
            raise review_flow.ReviewRefused(
                f"Term {ctx.item.id} is {ctx.item.status}: its cards are not reviewed."
            )
        content = ctx.content or {}
        attempt = productions.create_writing(
            session,
            text=answer,
            prompt=str(content.get("situation") or ""),
            target_item_ids=[ctx.item.id],
            study_session_id=study.id,
            at=as_utc(clock()),
            origin=ProductionOrigin.REVIEW,
        )
        solution, summary = review_flow.solution_and_summary(ctx)
        attempt_id, item_id = attempt.id, ctx.item.id
        session.commit()
    result = corrections.correct_production(
        session_factory, gateway, attempt_id, mode="sentence", clock=clock
    )
    rating = None
    if result.status == "ok":
        with session_factory() as session:
            feedback = productions.get_production(session, attempt_id).ai_feedback
            rating = production_rating(feedback, item_id)
            session.rollback()
    return ProductionCheck(
        result=result,
        proposed_rating=int(rating) if rating is not None else None,
        solution=solution,
        sheet_summary=summary,
    )
