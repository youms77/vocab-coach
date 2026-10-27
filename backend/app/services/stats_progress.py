"""Statistics of module I, part 2 (M9.a2): progress, practice, AI and the overview.

Read-only like `stats.py` (call these inside `stats.read_only`). Existing computations are reused,
never rewritten: the review-load forecast is `forecast_load` on the planner's own card snapshots
(D-028, D-029), AI usage is `ai_usage.ai_usage_for_day` (D-041), the Azure month is
`pronunciation.monthly_usage` (D-216), tracks are `curriculum.list_tracks`.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CurriculumTrack,
    CurriculumUnit,
    EventLog,
    LexicalItem,
    ProductionAttempt,
    ReviewLog,
    StudySession,
)
from app.domain.enums import UnitProgress
from app.domain.events import EventType
from app.domain.forecast import DayLoad, forecast_load
from app.domain.settings_defaults import default_for
from app.domain.stats import errors as error_rules
from app.domain.stats import memory as memory_rules
from app.domain.stats import practice as practice_rules
from app.domain.stats import progress as progress_rules
from app.domain.stats.common import (
    DECIMALS,
    Granularity,
    Period,
    Rate,
    Share,
    days_back,
    make_period,
)
from app.services import ai_usage, curriculum, pronunciation
from app.services.planning import build_plan_inputs
from app.services.stats import (
    Context,
    Header,
    _int,
    context,
    header,
    load_errors,
    load_productions,
    load_reviews,
    retention_changes,
)

FORECAST_DAYS = 14
OVERVIEW_ERROR_DAYS = 28
OVERVIEW_RETENTION_DAYS = 28
OVERVIEW_TIME_DAYS = 7

# --- Progress ------------------------------------------------------------------------------------


def lifecycle_events(session: Session) -> list[progress_rules.LifecycleEvent]:
    found = []
    kinds = {
        EventType.ITEM_CREATED.value: progress_rules.Change.CREATED,
        EventType.ITEM_STATUS_CHANGED.value: progress_rules.Change.STATUS,
        EventType.ITEM_DELETED.value: progress_rules.Change.REMOVED,
        EventType.ITEM_MERGED.value: progress_rules.Change.REMOVED,
    }
    rows = session.execute(
        select(EventLog.id, EventLog.occurred_at, EventLog.event_type, EventLog.payload)
        .where(EventLog.event_type.in_(list(kinds)))
        .order_by(EventLog.occurred_at, EventLog.id)
    )
    for event_id, occurred_at, event_type, payload in rows:
        payload = payload if isinstance(payload, dict) else {}
        key = "merged_item_id" if event_type == EventType.ITEM_MERGED.value else "lexical_item_id"
        item_id = _int(payload.get(key))
        if item_id is None:
            continue
        status = payload.get("to_status")
        found.append(
            progress_rules.LifecycleEvent(
                occurred_at,
                event_id,
                item_id,
                kinds[event_type],
                status if isinstance(status, str) else None,
            )  # fmt: skip
        )
    return found


def current_statuses(session: Session) -> dict[str, int]:
    return progress_rules.snapshot(str(s) for s in session.scalars(select(LexicalItem.status)))


@dataclass(frozen=True)
class TrackProgress:
    code: str
    title_en: str
    title_fr: str
    kind: str
    started: bool
    unit_count: int
    opened_units: int
    triaged_units: int
    done_units: int


def track_progress(session: Session) -> list[TrackProgress]:
    done: dict[str, int] = {
        code: count
        for code, count in session.execute(
            select(CurriculumTrack.code, func.count(CurriculumUnit.id))
            .join(CurriculumUnit, CurriculumUnit.track_id == CurriculumTrack.id)
            .where(CurriculumUnit.progress == UnitProgress.DONE)
            .group_by(CurriculumTrack.code)
        )
    }
    return [
        TrackProgress(
            track.code,
            track.title.en,
            track.title.fr,
            track.kind.value,
            track.started,
            track.unit_count,
            track.opened_units,
            track.triaged_units,
            done.get(track.code, 0),
        )  # fmt: skip
        for track in curriculum.list_tracks(session)
    ]


def load_forecast(session: Session, ctx: Context, days: int = FORECAST_DAYS) -> list[DayLoad]:
    """Cards due per study day from today (overdue cards count today), and the estimated time."""
    inputs = build_plan_inputs(session, ctx.now)
    return forecast_load(
        inputs.cards, ctx.today, ctx.tz, ctx.day_start_hour, inputs.durations, days=days
    )


@dataclass(frozen=True)
class ProgressStats:
    header: Header
    funnel_order: tuple[str, ...]
    outside_funnel: tuple[str, ...]
    snapshot: dict[str, int]
    rebuilt: list[progress_rules.FunnelBucket]
    active: list[tuple[date, int]]  # (bucket key, active terms at its end)
    tracks: list[TrackProgress]
    forecast: list[DayLoad]


def progress_stats(
    session: Session,
    now: datetime,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
) -> ProgressStats:
    ctx = context(session, now)
    period = make_period(start, end, ctx.today)
    rebuilt = progress_rules.rebuild(lifecycle_events(session), ctx.day_of, period, granularity)
    return ProgressStats(
        header=header(ctx, period, granularity),
        funnel_order=progress_rules.FUNNEL,
        outside_funnel=progress_rules.OUTSIDE_FUNNEL,
        snapshot=current_statuses(session),
        rebuilt=rebuilt,
        active=[(b.key, b.counts["active"]) for b in rebuilt],
        tracks=track_progress(session),
        forecast=load_forecast(session, ctx),
    )


# --- Practice ------------------------------------------------------------------------------------

# Events that are an action of the learner (with `review_log` and the creation of a production).
ACTION_EVENTS = (
    EventType.DRILL_ITEM_ANSWERED,
    EventType.DISCOVERY_COMPLETED,
    EventType.ITEM_TRIAGED,
    EventType.CURRICULUM_UNIT_STEP_COMPLETED,
)


def action_instants(session: Session, lower: datetime, upper: datetime) -> list[datetime]:
    """Instants of the learner's actions in [lower, upper): reviews, productions, drill answers,
    discoveries started and completed, triage decisions, unit steps."""
    instants = list(
        session.scalars(
            select(ReviewLog.reviewed_at).where(
                ReviewLog.reviewed_at >= lower, ReviewLog.reviewed_at < upper
            )
        )
    )
    instants += session.scalars(
        select(ProductionAttempt.created_at).where(
            ProductionAttempt.created_at >= lower, ProductionAttempt.created_at < upper
        )
    )
    instants += session.scalars(
        select(EventLog.occurred_at).where(
            EventLog.event_type.in_([e.value for e in ACTION_EVENTS]),
            EventLog.occurred_at >= lower,
            EventLog.occurred_at < upper,
        )
    )
    for occurred_at, payload in session.execute(
        select(EventLog.occurred_at, EventLog.payload).where(
            EventLog.event_type == EventType.ITEM_STATUS_CHANGED.value,
            EventLog.occurred_at >= lower,
            EventLog.occurred_at < upper,
        )
    ):
        if isinstance(payload, dict) and payload.get("to_status") == "discovering":
            instants.append(occurred_at)  # a discovery started
    return instants


def all_active_days(session: Session, ctx: Context) -> set[date]:
    """Every study day with at least one action (for the streaks)."""
    first = min(
        (
            value
            for value in (
                session.scalar(select(func.min(ReviewLog.reviewed_at))),
                session.scalar(select(func.min(ProductionAttempt.created_at))),
                session.scalar(select(func.min(EventLog.occurred_at))),
            )
            if value is not None
        ),
        default=None,
    )
    if first is None:
        return set()
    upper = ctx.bounds(Period(ctx.today, ctx.today))[1]
    return {ctx.day_of(t) for t in action_instants(session, first, upper)}


def ended_sessions(
    session: Session, lower: datetime, upper: datetime
) -> list[practice_rules.SessionSpan]:
    return [
        practice_rules.SessionSpan(started, ended)
        for started, ended in session.execute(
            select(StudySession.started_at, StudySession.ended_at).where(
                StudySession.ended_at.is_not(None),
                StudySession.started_at >= lower,
                StudySession.started_at < upper,
            )
        )
    ]


def recordings(
    session: Session, lower: datetime, upper: datetime
) -> list[practice_rules.Recording]:
    return [
        practice_rules.Recording(str(kind), created_at, float(seconds))
        for kind, created_at, seconds in session.execute(
            select(
                ProductionAttempt.kind,
                ProductionAttempt.created_at,
                ProductionAttempt.audio_seconds,
            ).where(
                ProductionAttempt.audio_path.is_not(None),
                ProductionAttempt.audio_seconds.is_not(None),
                ProductionAttempt.created_at >= lower,
                ProductionAttempt.created_at < upper,
            )
        )
    ]


@dataclass(frozen=True)
class PracticeStats:
    header: Header
    study_time: practice_rules.StudyTime
    streaks: practice_rules.Streaks
    words: list[practice_rules.WordsBucket]
    words_written: int
    words_oral: int
    speech: list[practice_rules.SpeechBucket]
    speech_seconds: float
    speech_by_kind: dict[str, float]


def practice_stats(
    session: Session,
    now: datetime,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
) -> PracticeStats:
    ctx = context(session, now)
    period = make_period(start, end, ctx.today)
    lower, upper = ctx.bounds(period)
    time = practice_rules.study_time(
        action_instants(session, lower, upper),
        ended_sessions(session, lower, upper),
        ctx.day_of,
        period,
        granularity,
    )
    words = practice_rules.words_produced(
        load_productions(session), ctx.day_of, period, granularity
    )
    speech = practice_rules.recorded_speech(
        recordings(session, lower, upper), ctx.day_of, period, granularity
    )
    by_kind: dict[str, float] = defaultdict(float)
    for bucket in speech:
        for kind, seconds in bucket.by_kind.items():
            by_kind[kind] += seconds
    return PracticeStats(
        header=header(ctx, period, granularity),
        study_time=time,
        streaks=practice_rules.streaks(all_active_days(session, ctx), ctx.today),
        words=words,
        words_written=sum(b.written for b in words),
        words_oral=sum(b.oral for b in words),
        speech=speech,
        speech_seconds=round(sum(b.seconds for b in speech), 3),
        speech_by_kind={k: round(v, 3) for k, v in sorted(by_kind.items())},
    )


# --- AI ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderDay:
    provider: str
    models: list[str]
    requests: int
    successes: int
    errors: dict[str, int]  # error code -> count
    rate_limited: int
    quota_exhausted: int
    input_tokens: int
    output_tokens: int
    avg_duration_ms: float | None  # weighted by the requests of each model


@dataclass(frozen=True)
class AiDay:
    day: date
    requests: int
    successes: int
    providers: list[ProviderDay]


@dataclass(frozen=True)
class AzureMonth:
    month: str
    audio_seconds: float
    assessments: int


@dataclass(frozen=True)
class AiStats:
    header: Header
    days: list[AiDay]  # every study day of the period, oldest first
    totals: list[ProviderDay]  # per provider over the period
    azure_month: AzureMonth


def _merge(provider: str, rows: list[ai_usage.ModelUsage]) -> ProviderDay:
    errors: dict[str, int] = defaultdict(int)
    for row in rows:
        for code, count in row.errors.items():
            errors[code] += count
    requests = sum(r.requests for r in rows)
    timed = [(r.avg_duration_ms, r.requests) for r in rows if r.avg_duration_ms is not None]
    weight = sum(n for _, n in timed)
    return ProviderDay(
        provider=provider,
        models=sorted({r.model for r in rows}),
        requests=requests,
        successes=sum(r.successes for r in rows),
        errors=dict(sorted(errors.items())),
        rate_limited=errors.get("rate_limited", 0),
        quota_exhausted=errors.get("quota_exhausted", 0),
        input_tokens=sum(r.input_tokens for r in rows),
        output_tokens=sum(r.output_tokens for r in rows),
        avg_duration_ms=round(sum(a * n for a, n in timed) / weight, 1) if weight else None,
    )


def _by_provider(rows: list[ai_usage.ModelUsage]) -> list[ProviderDay]:
    grouped: dict[str, list[ai_usage.ModelUsage]] = defaultdict(list)
    for row in rows:
        grouped[row.provider].append(row)
    return [_merge(provider, grouped[provider]) for provider in sorted(grouped)]


def ai_stats(
    session: Session,
    now: datetime,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
) -> AiStats:
    """Per study day and provider (the granularity is echoed; AI usage is always per day)."""
    ctx = context(session, now)
    period = make_period(start, end, ctx.today)
    days = []
    every_row: list[ai_usage.ModelUsage] = []
    for offset in range(period.days):
        usage = ai_usage.ai_usage_for_day(session, period.start + timedelta(days=offset))
        every_row += usage.rows
        days.append(AiDay(usage.day, usage.requests, usage.successes, _by_provider(usage.rows)))
    month = pronunciation.monthly_usage(session, ctx.now)
    return AiStats(
        header=header(ctx, period, granularity),
        days=days,
        totals=_by_provider(every_row),
        azure_month=AzureMonth(month.month, month.audio_seconds, month.assessments),
    )


# --- Overview ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Count:
    value: int
    n: int  # what the value was counted on (terms, study days...)


@dataclass(frozen=True)
class Overview:
    computed_at: datetime
    study_day: date
    demo: bool
    error_rate_last_28: Rate
    error_rate_previous_28: Rate
    retention_last_28: Share
    target_retention: float | None  # mean over those reviews; None without one
    current_target: float
    active_terms: Count  # n = every term of the library
    current_streak: Count  # n = active study days in the last 30
    study_minutes_last_7: float
    study_days_last_7: int
    reviews_due_tomorrow: Count  # n = cards that can be reviewed


def overview(session: Session, now: datetime) -> Overview:
    ctx = context(session, now)
    b = days_back(ctx.today, OVERVIEW_ERROR_DAYS)
    a = Period(b.start - timedelta(days=OVERVIEW_ERROR_DAYS), b.start - timedelta(days=1))
    productions = load_productions(session)
    errors = load_errors(session)
    rate_b = error_rules.error_rates(productions, errors, ctx.day_of, b, Granularity.WEEK).rate
    rate_a = error_rules.error_rates(productions, errors, ctx.day_of, a, Granularity.WEEK).rate

    recent = days_back(ctx.today, OVERVIEW_RETENTION_DAYS)
    lower, upper = ctx.bounds(recent)
    changes = retention_changes(session)
    default_target = float(default_for("target_retention"))
    retention = memory_rules.observed_retention(
        load_reviews(session, lower, upper), ctx.day_of, recent, Granularity.WEEK, changes,
        default_target,
    )  # fmt: skip
    current_target = memory_rules.target_at(changes, default_target, ctx.now)

    statuses = current_statuses(session)
    streak = practice_rules.streaks(all_active_days(session, ctx), ctx.today)
    week = days_back(ctx.today, OVERVIEW_TIME_DAYS)
    week_lower, week_upper = ctx.bounds(week)
    time = practice_rules.study_time(
        action_instants(session, week_lower, week_upper), [], ctx.day_of, week, Granularity.WEEK
    )
    inputs = build_plan_inputs(session, ctx.now)
    loads = forecast_load(
        inputs.cards, ctx.today, ctx.tz, ctx.day_start_hour, inputs.durations, days=2
    )
    schedulable = sum(1 for card in inputs.cards if card.schedulable)
    return Overview(
        computed_at=ctx.now,
        study_day=ctx.today,
        demo=ctx.demo,
        error_rate_last_28=rate_b,
        error_rate_previous_28=rate_a,
        retention_last_28=retention.all,
        target_retention=retention.target,
        current_target=current_target,
        active_terms=Count(statuses["active"], sum(statuses.values())),
        current_streak=Count(streak.current, streak.active_days_last_30),
        study_minutes_last_7=round(time.seconds / 60, DECIMALS),
        study_days_last_7=time.active_days,
        reviews_due_tomorrow=Count(loads[1].cards, schedulable),
    )
