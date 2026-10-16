"""Observed durations, read from `review_log` and `event_log` (never from ad hoc counters)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, EventLog, ReviewLog
from app.domain.durations import (
    OBSERVATION_WINDOW,
    DurationEstimates,
    duration_class,
    estimate_durations,
)
from app.domain.enums import CardDirection
from app.domain.events import EventType
from app.domain.study_day import as_utc


def observed_estimates(session: Session, now: datetime) -> DurationEstimates:
    """Duration estimates from the last 30 days, falling back to defaults when data is thin."""
    now = as_utc(now)
    since = now - OBSERVATION_WINDOW
    reviews = session.execute(
        select(Card.direction, ReviewLog.exercise_type, ReviewLog.response_time_ms)
        .join(Card, Card.id == ReviewLog.card_id)
        .where(
            ReviewLog.reviewed_at > since,
            ReviewLog.reviewed_at <= now,
            ReviewLog.response_time_ms.is_not(None),
        )
    )
    review_samples = [
        (duration_class(CardDirection(direction), exercise_type), ms / 1000)
        for direction, exercise_type, ms in reviews
    ]
    payloads = session.scalars(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.DISCOVERY_COMPLETED,
            EventLog.occurred_at > since,
            EventLog.occurred_at <= now,
        )
    )
    discovery_samples = [
        p["duration_ms"] / 1000 for p in payloads if p.get("duration_ms") is not None
    ]
    return estimate_durations(review_samples, discovery_samples)
