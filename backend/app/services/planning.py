"""Builds the planner's inputs from the database. Read-only: no row is added or changed."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Card,
    ConsolidationTask,
    Deck,
    DeckItem,
    Enrichment,
    ErrorCategory,
    ErrorEvent,
    LexicalItem,
)
from app.db.settings_store import get_setting
from app.domain.deck_queue import DeckItemRef, DeckSnapshot
from app.domain.enums import (
    CardDirection,
    ConsolidationTaskStatus,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    SrsState,
)
from app.domain.forecast import CardSnapshot
from app.domain.fsrs_engine import default_engine_factory
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.planner import (
    TARGETED_PRACTICE_WINDOW,
    DiscoveringItem,
    ErrorSample,
    PlanInputs,
    SessionPlan,
    plan_session,
)
from app.domain.srs import EngineFactory
from app.domain.study_day import as_utc
from app.domain.usage_sheet import is_usable
from app.services.durations import observed_estimates
from app.services.reviews import card_state

PENDING_CONSOLIDATION = (ConsolidationTaskStatus.PROPOSED, ConsolidationTaskStatus.ACCEPTED)


def card_snapshots(
    session: Session, now: datetime, engine_factory: EngineFactory = default_engine_factory
) -> list[CardSnapshot]:
    """Cards that may be reviewed (reviewable term, not suspended), with their retrievability at
    `now`. Ordered by id."""
    now = as_utc(now)
    engine = engine_factory(get_setting(session, "target_retention"))
    return [
        CardSnapshot(
            card_id=card.id,
            lexical_item_id=card.lexical_item_id,
            direction=CardDirection(card.direction),
            state=SrsState(card.srs_state),
            due=card.due,
            item_status=ItemStatus(item_status),
            suspended=card.suspended,
            retrievability=engine.retrievability(card_state(card), now),
        )
        for card, item_status in session.execute(
            select(Card, LexicalItem.status)
            .join(LexicalItem, LexicalItem.id == Card.lexical_item_id)
            .where(LexicalItem.status.in_(REVIEWABLE_STATUSES), Card.suspended.is_(False))
            .order_by(Card.id)
        )
    ]


def items_without_sheet(session: Session) -> frozenset[int]:
    """Queued terms whose current sheet is missing or not usable (D-105)."""
    rows = session.execute(
        select(LexicalItem.id, Enrichment.status, Enrichment.content)
        .outerjoin(
            Enrichment,
            (Enrichment.lexical_item_id == LexicalItem.id) & Enrichment.is_current,
        )
        .where(LexicalItem.status == ItemStatus.QUEUED)
    )
    return frozenset(
        item_id
        for item_id, status, content in rows
        if status is None or not is_usable(status, dict(content))
    )


def build_plan_inputs(
    session: Session, now: datetime, engine_factory: EngineFactory = default_engine_factory
) -> PlanInputs:
    now = as_utc(now)
    cards = card_snapshots(session, now, engine_factory)

    refs: dict[int, list[DeckItemRef]] = defaultdict(list)
    for deck_id, item_id, item_status, position in session.execute(
        select(
            DeckItem.deck_id, DeckItem.lexical_item_id, LexicalItem.status, DeckItem.position
        ).join(LexicalItem, LexicalItem.id == DeckItem.lexical_item_id)
    ):
        refs[deck_id].append(DeckItemRef(item_id, ItemStatus(item_status), position))
    decks = [
        DeckSnapshot(
            id=deck.id,
            status=DeckStatus(deck.status),
            deadline=deck.deadline,
            queue_position=deck.queue_position,
            items=tuple(refs[deck.id]),
        )
        for deck in session.scalars(select(Deck))
    ]

    discovering = [
        DiscoveringItem(item_id, since)
        for item_id, since in session.execute(
            select(LexicalItem.id, LexicalItem.status_changed_at).where(
                LexicalItem.status == ItemStatus.DISCOVERING
            )
        )
    ]
    errors = [
        ErrorSample(code, occurred_at)
        for code, occurred_at in session.execute(
            select(ErrorCategory.code, ErrorEvent.occurred_at)
            .join(ErrorCategory, ErrorCategory.id == ErrorEvent.category_id)
            .where(
                ErrorEvent.occurred_at > now - TARGETED_PRACTICE_WINDOW,
                ErrorEvent.occurred_at <= now,
                # Errors made in a drill do not choose the next drill (D-029 as amended, D-136).
                ErrorEvent.source != ErrorSource.DRILL,
            )
        )
    ]
    consolidation_ids = list(
        session.scalars(
            select(ConsolidationTask.id)
            .where(ConsolidationTask.status.in_(PENDING_CONSOLIDATION))
            .order_by(ConsolidationTask.created_at, ConsolidationTask.id)
        )
    )

    return PlanInputs(
        now=now,
        tz=ZoneInfo(get_setting(session, "timezone")),
        day_start_hour=get_setting(session, "day_start_hour"),
        budget_minutes=get_setting(session, "daily_time_budget_minutes"),
        new_items_per_day=get_setting(session, "new_items_per_day"),
        durations=observed_estimates(session, now),
        cards=cards,
        decks=decks,
        discovering=discovering,
        recent_errors=errors,
        pending_consolidation_task_ids=consolidation_ids,
        items_without_sheet=items_without_sheet(session),
    )


def plan_today(
    session: Session, now: datetime, engine_factory: EngineFactory = default_engine_factory
) -> SessionPlan:
    """Today's plan. Writes nothing: M4 records the session when the user starts it."""
    return plan_session(build_plan_inputs(session, now, engine_factory))
