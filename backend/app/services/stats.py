"""Statistics of module I (M9): read the logs, pass them to `app/domain/stats/`, build answers.

Read-only: `read_only` sets `PRAGMA query_only` on the connection (SQLite itself refuses any write)
and restores it afterwards, because the connection goes back to the pool (D-064). Reading a
statistic writes no row and no event.

Old payload versions are read as they are: a missing field is never an error, and an id quoted by
an old event that no longer exists (a merged or deleted term, D-076, D-077) is skipped.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.db.demo_marker import read_demo_marker
from app.db.models import (
    Card,
    ErrorCategory,
    ErrorEvent,
    EventLog,
    LexicalItem,
    ProductionAttempt,
    ReviewLog,
)
from app.db.settings_store import get_setting
from app.domain.events import EventType
from app.domain.settings_defaults import default_for
from app.domain.stats import errors as error_rules
from app.domain.stats import memory as memory_rules
from app.domain.stats.common import Granularity, Period, make_period
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.services.error_cards import carded_keys

# --- Session and clock ---------------------------------------------------------------------------


@contextmanager
def read_only(engine: Engine) -> Iterator[Session]:
    """A session whose connection refuses every write, reset to writable afterwards.

    The reset runs on the very connection the session holds, *before* the rollback gives it back
    to the pool: after a rollback the session's next statement may get another pooled connection,
    which would leave `query_only` ON in the first (a later write on it then failed with "attempt
    to write a readonly database", seen on `POST /api/backup`, M10.b)."""
    with Session(engine) as session:
        connection = session.connection()
        connection.execute(text("PRAGMA query_only = ON"))
        try:
            yield session
        finally:
            try:
                connection.execute(text("PRAGMA query_only = OFF"))
            finally:
                session.rollback()


@dataclass(frozen=True)
class Context:
    """What every statistic needs: the instant, today's study day and the day function."""

    now: datetime
    today: date
    tz: ZoneInfo
    day_start_hour: int
    demo: bool

    def day_of(self, instant: datetime) -> date:
        return study_day_of(instant, self.tz, self.day_start_hour)

    def bounds(self, period: Period) -> tuple[datetime, datetime]:
        """[start, end) of the period as UTC instants."""
        start, _ = study_day_bounds(period.start, self.tz, self.day_start_hour)
        _, end = study_day_bounds(period.end, self.tz, self.day_start_hour)
        return start, end


def context(session: Session, now: datetime) -> Context:
    now = as_utc(now)
    tz = ZoneInfo(get_setting(session, "timezone"))
    hour = int(get_setting(session, "day_start_hour"))
    return Context(
        now, study_day_of(now, tz, hour), tz, hour, read_demo_marker(session) is not None
    )


@dataclass(frozen=True)
class Header:
    computed_at: datetime
    study_day: date
    start: date  # `from` in the API
    end: date  # `to` in the API
    granularity: Granularity
    demo: bool


def header(ctx: Context, period: Period, granularity: Granularity) -> Header:
    return Header(ctx.now, ctx.today, period.start, period.end, granularity, ctx.demo)


# --- Loaders -------------------------------------------------------------------------------------


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _event_payloads(session: Session, event_type: EventType) -> Iterator[tuple[datetime, dict]]:
    rows = session.execute(
        select(EventLog.occurred_at, EventLog.payload)
        .where(EventLog.event_type == event_type.value)
        .order_by(EventLog.occurred_at, EventLog.id)
    )
    for occurred_at, payload in rows:
        yield occurred_at, payload if isinstance(payload, dict) else {}


def transcript_days(session: Session) -> dict[int, date]:
    """production id -> the day of the conversation (`occurred_on`, `production.recorded` v3+)."""
    found: dict[int, date] = {}
    for _, payload in _event_payloads(session, EventType.PRODUCTION_RECORDED):
        production_id = _int(payload.get("production_attempt_id"))
        raw = payload.get("occurred_on")
        if production_id is None or not isinstance(raw, str):
            continue
        try:
            found[production_id] = date.fromisoformat(raw)
        except ValueError:
            continue
    return found


def load_productions(session: Session) -> list[error_rules.ProductionWords]:
    days = transcript_days(session)
    rows = session.execute(
        select(
            ProductionAttempt.id,
            ProductionAttempt.kind,
            ProductionAttempt.modality,
            ProductionAttempt.word_count,
            ProductionAttempt.created_at,
        ).order_by(ProductionAttempt.id)
    )
    return [
        error_rules.ProductionWords(
            pid, str(kind), str(modality), words or 0, created, days.get(pid)
        )
        for pid, kind, modality, words, created in rows
    ]


def load_errors(session: Session) -> list[error_rules.ErrorFact]:
    """Every existing error (deleted ones are gone: they were false positives)."""
    rows = session.execute(
        select(
            ErrorEvent.id,
            ErrorCategory.code,
            ErrorEvent.source,
            ErrorEvent.occurred_at,
            ErrorEvent.production_attempt_id,
            ProductionAttempt.kind,
            ErrorEvent.review_log_id,
            ErrorEvent.erroneous_text,
            ErrorEvent.correction,
            ErrorEvent.original_text,
        )
        .join(ErrorCategory, ErrorCategory.id == ErrorEvent.category_id)
        .outerjoin(ProductionAttempt, ProductionAttempt.id == ErrorEvent.production_attempt_id)
        .order_by(ErrorEvent.id)
    )
    return [
        error_rules.ErrorFact(
            eid,
            code,
            str(source),
            occurred,
            pid,
            str(kind) if kind else None,
            rid,
            wrong or "",
            right or "",
            original or "",
        )  # fmt: skip
        for eid, code, source, occurred, pid, kind, rid, wrong, right, original in rows
    ]


def load_reviews(
    session: Session,
    start: datetime | None = None,
    end: datetime | None = None,
    item_ids: set[int] | None = None,
) -> list[memory_rules.ReviewFact]:
    query = (
        select(
            ReviewLog.id,
            ReviewLog.card_id,
            Card.lexical_item_id,
            Card.direction,
            ReviewLog.reviewed_at,
            ReviewLog.exercise_type,
            ReviewLog.state_before,
            ReviewLog.final_rating,
            ReviewLog.auto_rating,
            ReviewLog.retrievability,
        )
        .join(Card, Card.id == ReviewLog.card_id)
        .order_by(ReviewLog.reviewed_at, ReviewLog.id)
    )
    if start is not None:
        query = query.where(ReviewLog.reviewed_at >= start)
    if end is not None:
        query = query.where(ReviewLog.reviewed_at < end)
    if item_ids is not None:
        query = query.where(Card.lexical_item_id.in_(item_ids))
    return [
        memory_rules.ReviewFact(
            rid, card, item, str(direction), at, exercise, str(state), final, auto, predicted
        )
        for rid, card, item, direction, at, exercise, state, final, auto, predicted in (
            session.execute(query)
        )
    ]


def retention_changes(session: Session) -> list[memory_rules.RetentionChange]:
    found = []
    for occurred_at, payload in _event_payloads(session, EventType.SETTING_CHANGED):
        value = payload.get("new_value")
        if payload.get("key") == "target_retention" and isinstance(value, int | float):
            found.append(memory_rules.RetentionChange(occurred_at, float(value)))
    return found


def first_status_times(session: Session, status: str) -> dict[int, datetime]:
    """item id -> the first time it moved to `status` (`item.status_changed`)."""
    found: dict[int, datetime] = {}
    for occurred_at, payload in _event_payloads(session, EventType.ITEM_STATUS_CHANGED):
        item_id = _int(payload.get("lexical_item_id"))
        if item_id is not None and payload.get("to_status") == status and item_id not in found:
            found[item_id] = occurred_at
    return found


def discovery_times(session: Session) -> dict[int, datetime]:
    """item id -> first `discovery.completed`, else the term's `discovered_at`."""
    found: dict[int, datetime] = {}
    for occurred_at, payload in _event_payloads(session, EventType.DISCOVERY_COMPLETED):
        item_id = _int(payload.get("lexical_item_id"))
        if item_id is not None and item_id not in found:
            found[item_id] = occurred_at
    for item_id, discovered_at in session.execute(
        select(LexicalItem.id, LexicalItem.discovered_at).where(
            LexicalItem.discovered_at.is_not(None)
        )
    ):
        found.setdefault(item_id, discovered_at)
    return found


def load_cards(session: Session) -> list[memory_rules.CardFact]:
    rows = session.execute(
        select(Card.id, Card.direction, LexicalItem.status, Card.stability)
        .join(LexicalItem, LexicalItem.id == Card.lexical_item_id)
        .order_by(Card.id)
    )
    return [
        memory_rules.CardFact(cid, str(direction), str(status), stability)
        for cid, direction, status, stability in rows
    ]


def terms_of(session: Session, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    rows = session.execute(
        select(LexicalItem.id, LexicalItem.term).where(LexicalItem.id.in_(item_ids))
    )
    return {item_id: term for item_id, term in rows}


# --- Errors --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorStats:
    header: Header
    rates: error_rules.ErrorRates
    top_recurring: list[error_rules.RecurringError]
    trends: error_rules.Trends


def error_stats(
    session: Session,
    now: datetime,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
) -> ErrorStats:
    """Raises `InvalidPeriod` for `from` after `to` or a period over 366 days."""
    ctx = context(session, now)
    period = make_period(start, end, ctx.today)
    productions = load_productions(session)
    errors = load_errors(session)
    return ErrorStats(
        header=header(ctx, period, granularity),
        rates=error_rules.error_rates(productions, errors, ctx.day_of, period, granularity),
        top_recurring=error_rules.top_recurring(errors, ctx.day_of, period, carded_keys(session)),
        trends=error_rules.error_trends(productions, errors, ctx.day_of, ctx.today),
    )


# --- Memory --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LapsedTerm:
    item_id: int
    term: str | None  # None: the term no longer exists
    lapses: int


@dataclass(frozen=True)
class MemoryStats:
    header: Header
    default_target: float
    retention: memory_rules.Retention
    calibration: list[memory_rules.CalibrationBin]
    success_by_exercise: list[memory_rules.ExerciseSuccess]
    rating_agreement: memory_rules.RatingAgreement
    lapses: memory_rules.Lapses
    top_lapsed_terms: list[LapsedTerm]
    stability: list[memory_rules.StabilityDistribution]
    time_to_consolidation: memory_rules.TimeToConsolidation


def memory_stats(
    session: Session,
    now: datetime,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
) -> MemoryStats:
    ctx = context(session, now)
    period = make_period(start, end, ctx.today)
    lower, upper = ctx.bounds(period)
    reviews = load_reviews(session, lower, upper)
    default_target = float(default_for("target_retention"))
    lapse_stats = memory_rules.lapses(reviews, ctx.day_of, period, granularity)
    terms = terms_of(session, [i.item_id for i in lapse_stats.top_items])

    consolidated = first_status_times(session, "consolidated")
    in_period = {i for i, at in consolidated.items() if ctx.day_of(at) in period}
    delays = memory_rules.time_to_consolidation(
        consolidated,
        discovery_times(session),
        load_reviews(session, item_ids=in_period) if in_period else [],
        ctx.day_of,
        period,
    )
    return MemoryStats(
        header=header(ctx, period, granularity),
        default_target=default_target,
        retention=memory_rules.observed_retention(
            reviews, ctx.day_of, period, granularity, retention_changes(session), default_target
        ),
        calibration=memory_rules.calibration(reviews, ctx.day_of, period),
        success_by_exercise=memory_rules.success_by_exercise(reviews, ctx.day_of, period),
        rating_agreement=memory_rules.rating_agreement(reviews, ctx.day_of, period),
        lapses=lapse_stats,
        top_lapsed_terms=[
            LapsedTerm(i.item_id, terms.get(i.item_id), i.lapses) for i in lapse_stats.top_items
        ],
        stability=memory_rules.stability_distribution(load_cards(session)),
        time_to_consolidation=delays,
    )
