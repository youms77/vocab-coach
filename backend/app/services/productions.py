"""Recording a production attempt (module E). M4 only records discovery sentences; M5 adds AI
correction and error logging on top of this service."""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import ProductionAttempt, ProductionTarget
from app.domain.enums import Modality, ProductionKind
from app.domain.events import ProductionRecorded
from app.domain.study_day import as_utc

DISCOVERY_SENTENCE_PROMPT = "discovery sentence"


def word_count(text: str) -> int:
    """Words the user produced: the denominator of "errors per 100 words" (same rule as the
    demo's productions)."""
    return len(text.split())


def record_written_production(
    session: Session,
    *,
    text: str,
    prompt: str | None,
    targets: Mapping[int, bool | None],
    at: datetime,
    kind: ProductionKind = ProductionKind.WRITING,
    study_session_id: int | None = None,
) -> ProductionAttempt:
    """A written attempt with its target terms (`targets`: term id -> used, None if not checked).
    No AI feedback yet; writes `production.recorded`. In the caller's transaction."""
    at = as_utc(at)
    attempt = ProductionAttempt(
        kind=kind,
        modality=Modality.WRITTEN,
        prompt_text=prompt,
        text=text,
        word_count=word_count(text),
        ai_feedback=None,
        study_session_id=study_session_id,
        created_at=at,
        updated_at=at,
    )
    session.add(attempt)
    session.flush()
    for item_id, used in targets.items():
        session.add(
            ProductionTarget(production_attempt_id=attempt.id, lexical_item_id=item_id, used=used)
        )
    record_event(
        session,
        ProductionRecorded(
            production_attempt_id=attempt.id,
            kind=kind,
            modality=Modality.WRITTEN,
            word_count=attempt.word_count,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    session.flush()
    return attempt
