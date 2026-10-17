"""Recording and reading production attempts (module E). M4 records discovery sentences; M5.a1 adds
free writing (`create_writing`) and reading. The AI correction is `app/services/corrections.py`."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    LexicalItem,
    ProductionAttempt,
    ProductionTarget,
    StudySession,
)
from app.domain.enums import Modality, ProductionKind
from app.domain.events import ProductionOrigin, ProductionRecorded
from app.domain.sentences import MAX_SENTENCES, TextTooLong, split_sentences
from app.domain.study_day import as_utc
from app.services.library import LibraryError, get_item
from app.services.study_sessions import SessionNotFound

DISCOVERY_SENTENCE_PROMPT = "discovery sentence"

MAX_TEXT_CHARS = 4000
MAX_PROMPT_CHARS = 500
MAX_TARGETS = 15
MAX_PAGE_SIZE = 100


class ProductionNotFound(LibraryError):
    status, code = 404, "production_not_found"


class InvalidProduction(LibraryError):
    status, code = 422, "invalid_production"


class TextTooLongError(LibraryError):
    """More than `MAX_TEXT_CHARS` characters or `MAX_SENTENCES` sentences."""

    status, code = 422, "text_too_long"


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
    origin: ProductionOrigin | None = None,
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
            origin=origin,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    session.flush()
    return attempt


def create_writing(
    session: Session,
    *,
    text: str,
    prompt: str | None,
    target_item_ids: Sequence[int],
    study_session_id: int | None,
    at: datetime,
    origin: ProductionOrigin = ProductionOrigin.WRITING,
) -> ProductionAttempt:
    """A free-writing production (`POST /api/productions`). Raises InvalidProduction,
    TextTooLongError, ItemNotFound, SessionNotFound. In the caller's transaction."""
    text = text.strip()
    prompt = (prompt or "").strip() or None
    if not text:
        raise InvalidProduction("Write something first: the text is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise TextTooLongError(
            f"The text has {len(text)} characters; at most {MAX_TEXT_CHARS} are accepted."
        )
    if prompt is not None and len(prompt) > MAX_PROMPT_CHARS:
        raise InvalidProduction(f"The prompt has more than {MAX_PROMPT_CHARS} characters.")
    try:
        split_sentences(text)
    except TextTooLong as exc:
        raise TextTooLongError(str(exc), max_sentences=MAX_SENTENCES) from exc
    ids = list(dict.fromkeys(target_item_ids))
    if len(ids) > MAX_TARGETS:
        raise InvalidProduction(f"At most {MAX_TARGETS} target terms.")
    for item_id in ids:
        get_item(session, item_id)
    if study_session_id is not None and session.get(StudySession, study_session_id) is None:
        raise SessionNotFound(f"There is no study session {study_session_id}.")
    return record_written_production(
        session,
        text=text,
        prompt=prompt,
        targets=dict.fromkeys(ids),
        at=at,
        study_session_id=study_session_id,
        origin=origin,
    )


def get_production(session: Session, production_id: int) -> ProductionAttempt:
    attempt = session.get(ProductionAttempt, production_id)
    if attempt is None:
        raise ProductionNotFound(f"There is no production {production_id}.")
    return attempt


def list_productions(
    session: Session,
    *,
    kind: ProductionKind | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ProductionAttempt], int]:
    """Newest first: (page, total for the filter)."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    stmt = select(ProductionAttempt)
    count = select(func.count()).select_from(ProductionAttempt)
    if kind is not None:
        stmt = stmt.where(ProductionAttempt.kind == kind)
        count = count.where(ProductionAttempt.kind == kind)
    page = session.scalars(
        stmt.order_by(ProductionAttempt.created_at.desc(), ProductionAttempt.id.desc())
        .limit(limit)
        .offset(max(offset, 0))
    )
    return list(page), session.scalar(count) or 0


def targets_of(session: Session, attempt_id: int) -> list[tuple[ProductionTarget, LexicalItem]]:
    """The target terms of a production in a stable order (their position is the AI `ref`)."""
    rows = session.execute(
        select(ProductionTarget, LexicalItem)
        .join(LexicalItem, LexicalItem.id == ProductionTarget.lexical_item_id)
        .where(ProductionTarget.production_attempt_id == attempt_id)
        .order_by(ProductionTarget.id)
    )
    return [(target, item) for target, item in rows]
