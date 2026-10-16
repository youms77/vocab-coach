"""Demo-only direct writes: rows that no service creates yet (D-035, provisional).

Deck and term creation and triage decisions belong to module A (M3); productions and errors to
module E (M5); study sessions to module D's interface (M4). Until those services exist, the demo
writes the rows here, always with the matching event and a backdated `occurred_at`. When the
services arrive, the simulation calls them instead and this module shrinks.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    Deck,
    DeckItem,
    ErrorCategory,
    ErrorEvent,
    LexicalItem,
    ProductionAttempt,
    Source,
    StudySession,
)
from app.demo.dataset import DemoDeck, DemoTerm, ErrorTemplate
from app.domain.enums import (
    DeckKind,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    Modality,
    ProductionKind,
)
from app.domain.events import (
    DeckCreated,
    DeckItemAdded,
    ErrorRecorded,
    ItemCreated,
    ItemOrigin,
    ItemTriaged,
    ProductionRecorded,
    SessionEnded,
    SessionStarted,
    TriageDecision,
)
from app.services.items import transition_item

# Format of `study_session.planned` / `summary` written by the demo; M4 owns the real format.
DEMO_SESSION_FORMAT = "demo-provisional-1"


def create_deck(
    session: Session,
    spec: DemoDeck,
    at: datetime,
    *,
    deadline: date | None,
    queue_position: int | None,
) -> Deck:
    source_id = None
    if spec.source is not None:
        source = Source(
            title=spec.source.title,
            author=spec.source.author,
            domain=spec.domain,
            created_at=at,
            updated_at=at,
        )
        session.add(source)
        session.flush()
        source_id = source.id
    deck = Deck(
        name=spec.name,
        description=spec.description,
        domain=spec.domain,
        source_id=source_id,
        kind=DeckKind.CUSTOM,
        status=DeckStatus.QUEUED,
        deadline=deadline,
        queue_position=queue_position,
        created_at=at,
        updated_at=at,
    )
    session.add(deck)
    session.flush()
    record_event(
        session, DeckCreated(deck_id=deck.id, kind=deck.kind, status=deck.status), occurred_at=at
    )
    return deck


def create_item(session: Session, spec: DemoTerm, deck: Deck, at: datetime) -> LexicalItem:
    """A new term, in `draft`, created through `deck`."""
    item = LexicalItem(
        term=spec.term,
        normalized_form=spec.term.lower(),
        item_type=spec.type,
        part_of_speech=spec.pos,
        origin_sentence=spec.sentence,
        status=ItemStatus.DRAFT,
        status_changed_at=at,
        created_at=at,
        updated_at=at,
    )
    session.add(item)
    session.flush()
    record_event(
        session,
        ItemCreated(
            lexical_item_id=item.id,
            item_type=item.item_type,
            origin=ItemOrigin.DEMO,
            deck_id=deck.id,
        ),
        occurred_at=at,
    )
    return item


def add_to_deck(
    session: Session, deck: Deck, item: LexicalItem, position: int, at: datetime
) -> DeckItem:
    link = DeckItem(deck_id=deck.id, lexical_item_id=item.id, position=position, added_at=at)
    session.add(link)
    session.flush()
    record_event(session, DeckItemAdded(deck_id=deck.id, lexical_item_id=item.id), occurred_at=at)
    return link


def triage_item(
    session: Session, item: LexicalItem, decision: TriageDecision, at: datetime
) -> None:
    """Record the intake decision, then apply the status change through the item service."""
    record_event(session, ItemTriaged(lexical_item_id=item.id, decision=decision), occurred_at=at)
    target = ItemStatus.KNOWN if decision == TriageDecision.KNOWN else ItemStatus.QUEUED
    transition_item(session, item, target, at)


def start_study_session(session: Session, at: datetime, planned: dict[str, Any]) -> StudySession:
    study = StudySession(
        started_at=at,
        planned={"format": DEMO_SESSION_FORMAT, "plan": planned},
        created_at=at,
        updated_at=at,
    )
    session.add(study)
    session.flush()
    record_event(
        session,
        SessionStarted(study_session_id=study.id),
        occurred_at=at,
        study_session_id=study.id,
    )
    return study


def end_study_session(
    session: Session, study: StudySession, at: datetime, summary: dict[str, Any]
) -> None:
    study.ended_at = at
    study.summary = {"format": DEMO_SESSION_FORMAT, **summary}
    record_event(
        session,
        SessionEnded(
            study_session_id=study.id,
            duration_seconds=(at - study.started_at).total_seconds(),
        ),
        occurred_at=at,
        study_session_id=study.id,
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
