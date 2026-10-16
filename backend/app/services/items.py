"""Item status changes. The rules live in app/domain/item_status.py; this module applies them."""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Card, LexicalItem
from app.db.settings_store import get_setting
from app.domain.enums import CardDirection, ItemStatus
from app.domain.events import ItemStatusChanged
from app.domain.item_status import (
    TransitionKind,
    check_item_transition,
    consolidation_target,
    unarchive_target,
)
from app.domain.study_day import as_utc


def set_item_status(
    session: Session,
    item: LexicalItem,
    to_status: ItemStatus,
    at: datetime,
    kind: TransitionKind,
) -> None:
    """Check the transition, apply it, log `item.status_changed`. Raises InvalidItemTransition."""
    at = as_utc(at)
    from_status = ItemStatus(item.status)
    check_item_transition(item.id, from_status, to_status, kind)
    item.status = to_status
    item.status_changed_at = at
    record_event(
        session,
        ItemStatusChanged(lexical_item_id=item.id, from_status=from_status, to_status=to_status),
        occurred_at=at,
    )


def transition_item(
    session: Session, item: LexicalItem, to_status: ItemStatus, at: datetime
) -> None:
    """A status change chosen by the user (triage, queue, known, archive...)."""
    set_item_status(session, item, to_status, at, TransitionKind.MANUAL)


def mark_active(session: Session, item: LexicalItem, at: datetime) -> None:
    """Learning or consolidated -> active. Called by module G (M7) only."""
    set_item_status(session, item, ItemStatus.ACTIVE, at, TransitionKind.MARK_ACTIVE)


def _has_cards(session: Session, item: LexicalItem) -> bool:
    return bool(session.scalar(select(exists().where(Card.lexical_item_id == item.id))))


def unarchive_item(session: Session, item: LexicalItem, at: datetime) -> None:
    """Archived -> learning when the item has cards (then re-check consolidation), else queued."""
    set_item_status(
        session, item, unarchive_target(_has_cards(session, item)), at, TransitionKind.UNARCHIVE
    )
    sync_consolidation(session, item, at)


def sync_consolidation(session: Session, item: LexicalItem, at: datetime) -> None:
    """Move learning <-> consolidated from the productive card's stability."""
    productive_stability = session.scalar(
        select(Card.stability).where(
            Card.lexical_item_id == item.id, Card.direction == CardDirection.PRODUCTIVE
        )
    )
    threshold = get_setting(session, "consolidation_min_stability_days")
    target = consolidation_target(ItemStatus(item.status), productive_stability, threshold)
    if target is not None:
        set_item_status(session, item, target, at, TransitionKind.AUTOMATIC)
