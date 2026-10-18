"""The only demo write that no service does yet: an oral production (D-035, narrowed in D-163).

Written productions, corrections, transcripts, drills, errors and cards of the demo all go through
the services of module E since M5.a3. Speaking (module F, M6) has no service yet, so the demo
writes its spoken productions here, with the matching event and a backdated `occurred_at`; their
errors still go through `error_log.record_error`. Delete this file when M6 adds the service.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import ProductionAttempt
from app.domain.enums import Modality, ProductionKind
from app.domain.events import ProductionRecorded


def record_oral_production(
    session: Session,
    kind: ProductionKind,
    prompt: str,
    text: str,
    at: datetime,
    *,
    audio_seconds: float | None,
    study_session_id: int | None,
) -> ProductionAttempt:
    attempt = ProductionAttempt(
        kind=kind,
        modality=Modality.ORAL,
        prompt_text=prompt,
        text=text,
        word_count=len(text.split()),
        audio_seconds=audio_seconds,
        study_session_id=study_session_id,
        created_at=at,
        updated_at=at,
    )
    session.add(attempt)
    session.flush()
    record_event(
        session,
        ProductionRecorded(
            production_attempt_id=attempt.id,
            kind=kind,
            modality=Modality.ORAL,
            word_count=attempt.word_count,
            audio_seconds=audio_seconds,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    return attempt
