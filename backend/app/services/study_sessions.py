"""Today's study session (module D): start, next step, end.

A session freezes the plan when it starts (`planned = {format: "session-1", plan}`), but the next
step is computed live: learning steps come back after 1 or 10 minutes, so the frozen order alone
cannot drive the session. Order of the steps:

1. a card to review now, in `order_reviews` order. A card is due now when its due time has
   passed, or when it is a new or Review card due later in the current study day (whole-day
   intervals; the planner counts them for today). A (re)learning card due later waits;
2. the next new term of the frozen plan still `discovering` (interrupted first) or `queued`;
3. `wait` until the next (re)learning card due today;
4. `practice_info` (targeted practice and consolidation, information only in M4) if the plan has
   any and the client has not seen it, then `done`.

The summary is computed from `review_log` and `event_log` (statistics rule), never from counters.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Card, Deck, EventLog, LexicalItem, ReviewLog, StudySession
from app.db.settings_store import get_setting
from app.domain.deck_queue import SUPPLYING_STATUSES
from app.domain.enums import DeckStatus, ItemStatus, SrsState
from app.domain.events import EventType, SessionEnded, SessionStarted
from app.domain.forecast import CardSnapshot
from app.domain.fsrs_engine import default_engine_factory
from app.domain.planner import (
    BlockKind,
    ConsolidationEntry,
    NewItemEntry,
    SessionPlan,
    TargetedPracticeEntry,
    order_reviews,
)
from app.domain.srs import EngineFactory, Rating
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.services.durations import observed_estimates
from app.services.library import LibraryError
from app.services.planning import card_snapshots, plan_today
from app.services.review_flow import ReviewStep, review_step

SESSION_FORMAT = "session-1"

# Cards of these states are scheduled in whole days: due any time today means due now.
DAY_GRANULAR_STATES = frozenset({SrsState.NEW, SrsState.REVIEW})


class SessionNotFound(LibraryError):
    status, code = 404, "session_not_found"


class SessionClosed(LibraryError):
    code = "session_closed"


# --- Days ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Day:
    day: date
    start: datetime
    end: datetime


def _clock(session: Session) -> tuple[ZoneInfo, int]:
    return ZoneInfo(get_setting(session, "timezone")), get_setting(session, "day_start_hour")


def _day_of(session: Session, at: datetime) -> _Day:
    tz, hour = _clock(session)
    day = study_day_of(at, tz, hour)
    start, end = study_day_bounds(day, tz, hour)
    return _Day(day, start, end)


def study_day_of_session(session: Session, study: StudySession) -> date:
    return _day_of(session, study.started_at).day


# --- Lookup --------------------------------------------------------------------------------------


def get_study_session(session: Session, study_id: int) -> StudySession:
    study = session.get(StudySession, study_id)
    if study is None:
        raise SessionNotFound(f"There is no study session {study_id}.")
    return study


def require_open(session: Session, study_id: int) -> StudySession:
    study = get_study_session(session, study_id)
    if study.ended_at is not None:
        raise SessionClosed(f"Study session {study_id} is closed.")
    return study


def open_session_of_day(session: Session, day: date) -> StudySession | None:
    for study in session.scalars(
        select(StudySession)
        .where(StudySession.ended_at.is_(None))
        .order_by(StudySession.started_at, StudySession.id)
    ):
        if study_day_of_session(session, study) == day:
            return study
    return None


def frozen_plan(study: StudySession) -> SessionPlan | None:
    plan = (study.planned or {}).get("plan")
    return SessionPlan.model_validate(plan) if plan is not None else None


# --- Summary -------------------------------------------------------------------------------------


def _events(session: Session, study_id: int, event_type: EventType) -> list[dict[str, Any]]:
    return [
        dict(payload)
        for payload in session.scalars(
            select(EventLog.payload).where(
                EventLog.study_session_id == study_id, EventLog.event_type == event_type
            )
        )
    ]


def last_activity(session: Session, study: StudySession) -> datetime:
    """The last event of the session (its start when nothing happened)."""
    last = session.scalar(
        select(func.max(EventLog.occurred_at)).where(EventLog.study_session_id == study.id)
    )
    return max(last, study.started_at) if last is not None else study.started_at


def compute_summary(session: Session, study: StudySession, ended_at: datetime) -> dict[str, Any]:
    reviews = session.scalar(
        select(func.count()).select_from(ReviewLog).where(ReviewLog.study_session_id == study.id)
    )
    failed = session.scalar(
        select(func.count())
        .select_from(ReviewLog)
        .where(ReviewLog.study_session_id == study.id, ReviewLog.final_rating == Rating.AGAIN)
    )
    started = [
        p
        for p in _events(session, study.id, EventType.ITEM_STATUS_CHANGED)
        if p.get("to_status") == ItemStatus.DISCOVERING
    ]
    productions = _events(session, study.id, EventType.PRODUCTION_RECORDED)
    plan = frozen_plan(study)
    return {
        "format": SESSION_FORMAT,
        "reviews": reviews or 0,
        "failed_reviews": failed or 0,
        "discoveries_started": len(started),
        "discoveries_completed": len(_events(session, study.id, EventType.DISCOVERY_COMPLETED)),
        "productions": len(productions),
        "words": sum(int(p.get("word_count", 0)) for p in productions),
        "duration_ms": max(0, round((ended_at - study.started_at).total_seconds() * 1000)),
        "planned_minutes": round(plan.total_seconds / 60) if plan is not None else None,
    }


def _close(session: Session, study: StudySession, at: datetime) -> None:
    study.ended_at = at
    study.updated_at = at
    study.summary = compute_summary(session, study, at)
    record_event(
        session,
        SessionEnded(
            study_session_id=study.id,
            duration_seconds=max(0.0, (at - study.started_at).total_seconds()),
        ),
        occurred_at=at,
        study_session_id=study.id,
    )
    session.flush()


# --- Start and end -------------------------------------------------------------------------------


def close_stale_sessions(session: Session, now: datetime) -> list[StudySession]:
    """Close the sessions left open on an earlier study day, at their last activity."""
    today = _day_of(session, now).day
    closed = []
    for study in list(
        session.scalars(
            select(StudySession)
            .where(StudySession.ended_at.is_(None))
            .order_by(StudySession.started_at, StudySession.id)
        )
    ):
        if study_day_of_session(session, study) < today:
            _close(session, study, last_activity(session, study))
            closed.append(study)
    return closed


def start_session(
    session: Session, now: datetime, engine_factory: EngineFactory = default_engine_factory
) -> tuple[StudySession, bool]:
    """Today's open session, or a new one with the plan frozen. Returns (session, created)."""
    now = as_utc(now)
    close_stale_sessions(session, now)
    existing = open_session_of_day(session, _day_of(session, now).day)
    if existing is not None:
        return existing, False
    plan = plan_today(session, now, engine_factory)
    study = StudySession(
        started_at=now,
        planned={"format": SESSION_FORMAT, "plan": plan.model_dump(mode="json")},
        created_at=now,
        updated_at=now,
    )
    session.add(study)
    session.flush()
    record_event(
        session,
        SessionStarted(study_session_id=study.id),
        occurred_at=now,
        study_session_id=study.id,
    )
    return study, True


def end_session(session: Session, study: StudySession, now: datetime) -> StudySession:
    """Close an open session (raises SessionClosed)."""
    now = as_utc(now)
    if study.ended_at is not None:
        raise SessionClosed(f"Study session {study.id} is already closed.")
    _close(session, study, max(now, study.started_at))
    return study


# --- Next step -----------------------------------------------------------------------------------


class Progress(BaseModel):
    reviews_done: int
    reviews_remaining: int
    new_done: int
    new_remaining: int
    estimated_seconds_remaining: float


class NewItemStep(BaseModel):
    item_id: int
    term: str
    deck_id: int | None
    resumed: bool


class WaitStep(BaseModel):
    until: datetime


class TargetedPracticeInfo(BaseModel):
    category_code: str
    error_count: int


class PracticeStep(BaseModel):
    targeted_practice: TargetedPracticeInfo | None
    consolidation_task_id: int | None


StepType = Literal["review", "new_item", "wait", "practice_info", "done"]


class Step(BaseModel):
    type: StepType
    session_id: int
    progress: Progress
    review: ReviewStep | None = None
    new_item: NewItemStep | None = None
    wait: WaitStep | None = None
    practice: PracticeStep | None = None


def due_now(cards: list[CardSnapshot], now: datetime, day_end: datetime) -> list[CardSnapshot]:
    return [
        c
        for c in cards
        if c.schedulable and (c.due <= now or (c.state in DAY_GRANULAR_STATES and c.due < day_end))
    ]


def _pending_new_items(
    session: Session, plan: SessionPlan | None
) -> list[tuple[NewItemEntry, LexicalItem]]:
    """New terms of the frozen plan still to do: interrupted discoveries first, then queued
    terms whose deck still supplies new terms."""
    block = plan.block(BlockKind.NEW_ITEMS) if plan is not None else None
    if block is None:
        return []
    discovering: list[tuple[NewItemEntry, LexicalItem]] = []
    queued: list[tuple[NewItemEntry, LexicalItem]] = []
    for entry in block.entries:
        if not isinstance(entry, NewItemEntry):
            continue
        item = session.get(LexicalItem, entry.lexical_item_id)
        if item is None:
            continue
        if item.status == ItemStatus.DISCOVERING:
            discovering.append((entry, item))
        elif item.status == ItemStatus.QUEUED:
            deck = session.get(Deck, entry.deck_id) if entry.deck_id is not None else None
            if deck is None or DeckStatus(deck.status) in SUPPLYING_STATUSES:
                queued.append((entry, item))
    return discovering + queued


def _practice(plan: SessionPlan | None) -> PracticeStep | None:
    if plan is None:
        return None
    targeted = next(
        (e for b in plan.blocks for e in b.entries if isinstance(e, TargetedPracticeEntry)),
        None,
    )
    consolidation = next(
        (e for b in plan.blocks for e in b.entries if isinstance(e, ConsolidationEntry)), None
    )
    if targeted is None and consolidation is None:
        return None
    return PracticeStep(
        targeted_practice=(
            TargetedPracticeInfo(
                category_code=targeted.category_code, error_count=targeted.error_count
            )
            if targeted is not None
            else None
        ),
        consolidation_task_id=(
            consolidation.consolidation_task_id if consolidation is not None else None
        ),
    )


def next_step(
    session: Session,
    study: StudySession,
    now: datetime,
    *,
    practice_seen: bool = False,
    engine_factory: EngineFactory = default_engine_factory,
) -> Step:
    """The next thing to do in an open session (raises SessionClosed)."""
    now = as_utc(now)
    if study.ended_at is not None:
        raise SessionClosed(f"Study session {study.id} is closed.")
    day = _day_of(session, now)
    plan = frozen_plan(study)
    durations = observed_estimates(session, now)

    cards = [c for c in card_snapshots(session, now, engine_factory) if c.schedulable]
    now_cards = due_now(cards, now, day.end)
    now_ids = {c.card_id for c in now_cards}
    later = [c for c in cards if c.card_id not in now_ids and c.due < day.end]
    new_items = _pending_new_items(session, plan)
    practice = _practice(plan)
    practice_left = practice is not None and not practice_seen

    remaining_seconds = sum(durations.for_due_card(c.direction) for c in [*now_cards, *later])
    remaining_seconds += len(new_items) * durations.discovery
    if practice_left and plan is not None:
        remaining_seconds += sum(
            b.estimated_seconds
            for b in plan.blocks
            if b.kind in (BlockKind.TARGETED_PRACTICE, BlockKind.CONSOLIDATION)
        )
    reviews_done = session.scalar(
        select(func.count()).select_from(ReviewLog).where(ReviewLog.study_session_id == study.id)
    )
    progress = Progress(
        reviews_done=reviews_done or 0,
        reviews_remaining=len(now_cards) + len(later),
        new_done=len(_events(session, study.id, EventType.DISCOVERY_COMPLETED)),
        new_remaining=len(new_items),
        estimated_seconds_remaining=remaining_seconds,
    )
    step = Step(type="done", session_id=study.id, progress=progress)

    if now_cards:
        card = session.get_one(Card, order_reviews(now_cards)[0].card_id)
        step.type, step.review = "review", review_step(session, card)
    elif new_items:
        entry, item = new_items[0]
        step.type = "new_item"
        step.new_item = NewItemStep(
            item_id=item.id,
            term=item.term,
            deck_id=entry.deck_id,
            resumed=item.status == ItemStatus.DISCOVERING,
        )
    elif later:
        step.type, step.wait = "wait", WaitStep(until=min(c.due for c in later))
    elif practice_left:
        step.type, step.practice = "practice_info", practice
    return step
