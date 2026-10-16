"""Helpers for the library tests (fictional data only)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import EventLog, LexicalItem
from app.domain.events import parse_event


def events(session: Session, event_type: str) -> list[dict[str, Any]]:
    """Payloads of one event type, oldest first; each is re-validated against its model."""
    rows = session.scalars(
        select(EventLog).where(EventLog.event_type == event_type).order_by(EventLog.id)
    )
    payloads = []
    for row in rows:
        parse_event(row.event_type, row.payload)
        payloads.append(row.payload)
    return payloads


def count(session: Session, model: Any) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def item_by_term(session: Session, term: str) -> LexicalItem:
    item = session.scalar(select(LexicalItem).where(LexicalItem.term == term))
    assert item is not None, term
    return item
