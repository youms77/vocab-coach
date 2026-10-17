"""Recording a card review (module C): FSRS state, counters, review log, event, item status."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Card, LexicalItem, ReviewLog
from app.db.settings_store import get_setting
from app.domain.enums import CardDirection, SrsState
from app.domain.events import CardReviewed
from app.domain.fsrs_engine import default_engine_factory
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.srs import EngineFactory, Rating, SrsCardState
from app.domain.study_day import as_utc
from app.services.items import sync_consolidation

SECONDS_PER_DAY = 86400.0


class ReviewNotAllowed(ValueError):
    """The review is refused (archived or known item, review earlier than the last one...)."""


def card_state(card: Card) -> SrsCardState:
    """The card's scheduling state as the SRS interface sees it."""
    return SrsCardState(
        state=SrsState(card.srs_state),
        due=card.due,
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        last_review=card.last_review_at,
        payload=dict(card.srs_payload) if card.srs_payload is not None else None,
    )


def apply_card_state(card: Card, state: SrsCardState, algorithm: str) -> None:
    card.srs_state = state.state
    card.due = state.due
    card.step = state.step
    card.stability = state.stability
    card.difficulty = state.difficulty
    card.last_review_at = state.last_review
    card.srs_algorithm = algorithm
    # Reassign, never edit in place: MutableDict only tracks top-level changes (D-020).
    card.srs_payload = dict(state.payload) if state.payload is not None else None


def record_review(
    session: Session,
    card: Card,
    final_rating: int,
    at: datetime,
    response_time_ms: int | None,
    exercise_type: str,
    answer: str | None = None,
    auto_rating: int | None = None,
    *,
    study_session_id: int | None = None,
    exercise_template_id: int | None = None,
    audio_path: str | None = None,
    production_attempt_id: int | None = None,
    engine_factory: EngineFactory = default_engine_factory,
) -> ReviewLog:
    """Apply `final_rating` to `card` at `at`, in the caller's transaction (no commit).

    `auto_rating` (the rating the app proposed) is only stored, to measure later how often the
    user overrides it. Raises ReviewNotAllowed.
    """
    at = as_utc(at)
    rating = Rating(final_rating)
    proposed = Rating(auto_rating) if auto_rating is not None else None
    item = session.get_one(LexicalItem, card.lexical_item_id)
    if item.status not in REVIEWABLE_STATUSES:
        raise ReviewNotAllowed(f"card {card.id}: item {item.id} is {item.status}")
    if card.last_review_at is not None and at < card.last_review_at:
        raise ReviewNotAllowed(
            f"card {card.id}: review at {at.isoformat()} is earlier than the last review "
            f"({card.last_review_at.isoformat()})"
        )

    # Read at every review: a retention change applies to the next reviews only.
    engine = engine_factory(get_setting(session, "target_retention"))
    before = card_state(card)
    after = engine.review(before, rating, at, response_time_ms)

    log = ReviewLog(
        card_id=card.id,
        study_session_id=study_session_id,
        reviewed_at=at,
        exercise_type=exercise_type,
        exercise_template_id=exercise_template_id,
        answer_text=answer,
        audio_path=audio_path,
        production_attempt_id=production_attempt_id,
        auto_rating=proposed,
        final_rating=rating,
        response_time_ms=response_time_ms,
        state_before=before.state,
        stability_before=before.stability,
        difficulty_before=before.difficulty,
        due_before=before.due,
        elapsed_days=(
            (at - before.last_review).total_seconds() / SECONDS_PER_DAY
            if before.last_review is not None
            else None
        ),
        retrievability=engine.retrievability(before, at),
        state_after=after.state,
        stability_after=after.stability,
        difficulty_after=after.difficulty,
        due_after=after.due,
        scheduled_days=(after.due - at).total_seconds() / SECONDS_PER_DAY,
        srs_algorithm=engine.algorithm,
    )
    session.add(log)

    card.reps = (card.reps or 0) + 1
    # A lapse is forgetting a card that had graduated; failing a (re)learning step is not one.
    if before.state == SrsState.REVIEW and rating == Rating.AGAIN:
        card.lapses = (card.lapses or 0) + 1
    apply_card_state(card, after, engine.algorithm)
    session.flush()

    record_event(
        session,
        CardReviewed(
            card_id=card.id,
            review_log_id=log.id,
            lexical_item_id=item.id,
            direction=CardDirection(card.direction),
            exercise_type=exercise_type,
            auto_rating=proposed,
            final_rating=rating,
            response_time_ms=response_time_ms,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    sync_consolidation(session, item, at)
    return log
