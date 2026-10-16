"""Write events to `event_log` inside the caller's transaction."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import EventLog
from app.domain.events import Event


def record_event(
    session: Session,
    event: Event,
    *,
    occurred_at: datetime | None = None,
    study_session_id: int | None = None,
) -> EventLog:
    """Validate `event` and add it to the session; the caller commits.

    The row joins the same transaction as the business change, so a rollback removes both.
    `occurred_at` defaults to now; demo data may pass an earlier date (backdated history).
    """
    # Re-validate: an instance built with `model_construct` or mutated would skip validation.
    validated = type(event).model_validate(event.model_dump(warnings=False))
    row = EventLog(
        occurred_at=occurred_at or utcnow(),
        event_type=validated.event_type.value,
        entity_type=validated.entity_type,
        entity_id=validated.entity_id(),
        payload=validated.model_dump(mode="json"),
        payload_version=validated.payload_version,
        study_session_id=study_session_id,
    )
    session.add(row)
    return row
