"""Demo-only direct writes: rows that no service creates yet (D-035, provisional).

Productions and errors belong to module E (M5). Until that service exists, the demo writes the
rows here, always with the matching event and a backdated `occurred_at`. Decks, terms, deck links
and triage decisions moved to the library services in M3.a (`app/services/library.py`,
`triage.py`); study sessions to `app/services/study_sessions.py` in M4.a2.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    ErrorCategory,
    ErrorEvent,
    ProductionAttempt,
)
from app.demo.dataset import ErrorTemplate
from app.domain.enums import (
    ErrorSource,
    Modality,
    ProductionKind,
)
from app.domain.events import (
    ErrorRecorded,
    ProductionRecorded,
)


def record_production(
    session: Session,
    kind: ProductionKind,
    prompt: str,
    text: str,
    at: datetime,
    *,
    audio_seconds: float | None,
    study_session_id: int | None,
) -> ProductionAttempt:
    modality = Modality.WRITTEN if kind == ProductionKind.WRITING else Modality.ORAL
    attempt = ProductionAttempt(
        kind=kind,
        modality=modality,
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
            modality=modality,
            word_count=attempt.word_count,
            audio_seconds=audio_seconds,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    return attempt


class CategoryIds:
    """code -> error_category.id, read once."""

    def __init__(self, session: Session) -> None:
        rows = session.execute(select(ErrorCategory.code, ErrorCategory.id))
        self._ids = {code: category_id for code, category_id in rows}

    def __getitem__(self, code: str) -> int:
        return self._ids[code]


def record_error(
    session: Session,
    categories: CategoryIds,
    *,
    code: str,
    source: ErrorSource,
    original: str,
    wrong: str,
    correction: str,
    alternatives: list[str],
    explanation: str,
    at: datetime,
    production_attempt_id: int | None = None,
    review_log_id: int | None = None,
    lexical_item_id: int | None = None,
    study_session_id: int | None = None,
) -> ErrorEvent:
    error = ErrorEvent(
        production_attempt_id=production_attempt_id,
        review_log_id=review_log_id,
        source=source,
        original_text=original,
        erroneous_text=wrong,
        correction=correction,
        alternatives=alternatives,
        explanation=explanation,
        category_id=categories[code],
        lexical_item_id=lexical_item_id,
        occurred_at=at,
        created_at=at,
        updated_at=at,
    )
    session.add(error)
    session.flush()
    record_event(
        session,
        ErrorRecorded(
            error_event_id=error.id,
            category_code=code,
            source=source,
            lexical_item_id=lexical_item_id,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    return error


def record_template_error(
    session: Session,
    categories: CategoryIds,
    template: ErrorTemplate,
    source: ErrorSource,
    at: datetime,
    production_attempt_id: int,
    study_session_id: int | None,
) -> ErrorEvent:
    return record_error(
        session,
        categories,
        code=template.code,
        source=source,
        original=template.original,
        wrong=template.wrong,
        correction=template.correction,
        alternatives=list(template.alternatives),
        explanation=template.explanation,
        at=at,
        production_attempt_id=production_attempt_id,
        study_session_id=study_session_id,
    )
