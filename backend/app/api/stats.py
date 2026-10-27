"""Statistics endpoints (module I, M9.a). Read-only: no row and no event is written.

Every answer carries `computed_at`, `study_day` (today), `from`, `to`, `granularity` and `demo`.
`from` and `to` are study days (included); the default is the last 30 study days up to today.
`from` after `to`, or more than 366 days, is 422 `invalid_request` (D-063).
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import api_error, require_database
from app.api.library import DeckOut, decks_out
from app.db.engine import get_engine
from app.domain.forecast import DayLoad
from app.domain.stats import errors as error_rules
from app.domain.stats import memory as memory_rules
from app.domain.stats import practice as practice_rules
from app.domain.stats import progress as progress_rules
from app.domain.stats.common import Granularity, InvalidPeriod
from app.services import library, stats, stats_progress
from app.services.stats import Header, LapsedTerm, read_only
from app.services.stats_progress import TrackProgress

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_database)])

EngineDep = Annotated[Engine, Depends(get_engine)]


class ActivePoint(BaseModel):
    key: date
    active: int


class PeriodQuery(BaseModel):
    start: date | None
    end: date | None
    granularity: Granularity


def period_query(
    from_: Annotated[
        date | None, Query(alias="from", description="First study day (YYYY-MM-DD), included.")
    ] = None,
    to: Annotated[
        date | None, Query(description="Last study day (YYYY-MM-DD), included. Default: today.")
    ] = None,
    granularity: Annotated[
        Granularity, Query(description="`day`, or `week` (ISO weeks from Monday).")
    ] = Granularity.DAY,
) -> PeriodQuery:
    return PeriodQuery(start=from_, end=to, granularity=granularity)


PeriodDep = Annotated[PeriodQuery, Depends(period_query)]


class StatsHeaderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    computed_at: datetime
    study_day: date
    from_: date = Field(alias="from")
    to: date
    granularity: Granularity
    demo: bool


def header_fields(head: Header) -> dict[str, object]:
    return {
        "computed_at": head.computed_at,
        "study_day": head.study_day,
        "from": head.start,
        "to": head.end,
        "granularity": head.granularity,
        "demo": head.demo,
    }


def run[T](engine: Engine, compute: Callable[[Session], T]) -> T:
    """Compute in a read-only session; a bad period is 422 `invalid_request`."""
    with read_only(engine) as session:
        try:
            return compute(session)
        except InvalidPeriod as exc:
            raise api_error(
                422,
                "invalid_request",
                str(exc),
                errors=[{"loc": ["query", "from"], "message": str(exc)}],
            ) from exc


class ErrorStatsOut(StatsHeaderOut):
    rates: error_rules.ErrorRates
    top_recurring: list[error_rules.RecurringError]
    trends: error_rules.Trends


@router.get("/errors")
def error_stats(engine: EngineDep, now: NowDep, period: PeriodDep) -> ErrorStatsOut:
    """Errors per 100 words (overall, levels 1 and 2, per bucket), errors kept out of the rates,
    the top 5 recurring errors and the lasting trends (last 28 study days against the 28 before,
    whatever the period)."""
    result = run(
        engine,
        lambda s: stats.error_stats(s, now, period.start, period.end, period.granularity),
    )
    return ErrorStatsOut(
        **header_fields(result.header),
        rates=result.rates,
        top_recurring=result.top_recurring,
        trends=result.trends,
    )


class MemoryStatsOut(StatsHeaderOut):
    default_target: float
    retention: memory_rules.Retention
    calibration: list[memory_rules.CalibrationBin]
    success_by_exercise: list[memory_rules.ExerciseSuccess]
    rating_agreement: memory_rules.RatingAgreement
    lapses: memory_rules.Lapses
    top_lapsed_terms: list[LapsedTerm]
    stability: list[memory_rules.StabilityDistribution]
    time_to_consolidation: memory_rules.TimeToConsolidation


@router.get("/memory")
def memory_stats(engine: EngineDep, now: NowDep, period: PeriodDep) -> MemoryStatsOut:
    """Observed retention against the target, calibration, success by exercise type, agreement of
    ratings, lapses, current stability and time before consolidation."""
    result = run(
        engine,
        lambda s: stats.memory_stats(s, now, period.start, period.end, period.granularity),
    )
    return MemoryStatsOut(
        **header_fields(result.header),
        default_target=result.default_target,
        retention=result.retention,
        calibration=result.calibration,
        success_by_exercise=result.success_by_exercise,
        rating_agreement=result.rating_agreement,
        lapses=result.lapses,
        top_lapsed_terms=result.top_lapsed_terms,
        stability=result.stability,
        time_to_consolidation=result.time_to_consolidation,
    )


class ProgressStatsOut(StatsHeaderOut):
    funnel_order: list[str]
    outside_funnel: list[str]
    snapshot: dict[str, int]
    rebuilt: list[progress_rules.FunnelBucket]
    active: list[ActivePoint]
    decks: list[DeckOut]
    tracks: list[TrackProgress]
    forecast: list[DayLoad]


@router.get("/progress")
def progress_stats(engine: EngineDep, now: NowDep, period: PeriodDep) -> ProgressStatsOut:
    """Status funnel now and rebuilt from the event log at the end of every bucket, active terms,
    decks (as `GET /api/decks`), tracks and the review load of the next 14 study days."""
    result, decks = run(
        engine,
        lambda s: (
            stats_progress.progress_stats(s, now, period.start, period.end, period.granularity),
            # Every deck as `GET /api/decks` gives it, in the same read-only session.
            decks_out(s, library.list_decks(s), now),
        ),
    )
    return ProgressStatsOut(
        **header_fields(result.header),
        funnel_order=list(result.funnel_order),
        outside_funnel=list(result.outside_funnel),
        snapshot=result.snapshot,
        rebuilt=result.rebuilt,
        active=[ActivePoint(key=key, active=value) for key, value in result.active],
        decks=decks,
        tracks=result.tracks,
        forecast=result.forecast,
    )


class PracticeStatsOut(StatsHeaderOut):
    study_time: practice_rules.StudyTime
    streaks: practice_rules.Streaks
    words: list[practice_rules.WordsBucket]
    words_written: int
    words_oral: int
    speech: list[practice_rules.SpeechBucket]
    speech_seconds: float
    speech_by_kind: dict[str, float]


@router.get("/practice")
def practice_stats(engine: EngineDep, now: NowDep, period: PeriodDep) -> PracticeStatsOut:
    """Study time from the activity blocks (sessions alongside, not added), streaks, words
    produced in writing and speech, seconds of recorded speech."""
    result = run(
        engine,
        lambda s: stats_progress.practice_stats(
            s, now, period.start, period.end, period.granularity
        ),
    )
    return PracticeStatsOut(
        **header_fields(result.header),
        study_time=result.study_time,
        streaks=result.streaks,
        words=result.words,
        words_written=result.words_written,
        words_oral=result.words_oral,
        speech=result.speech,
        speech_seconds=result.speech_seconds,
        speech_by_kind=result.speech_by_kind,
    )


class AiStatsOut(StatsHeaderOut):
    days: list[stats_progress.AiDay]
    totals: list[stats_progress.ProviderDay]
    azure_month: stats_progress.AzureMonth


@router.get("/ai")
def ai_stats(engine: EngineDep, now: NowDep, period: PeriodDep) -> AiStatsOut:
    """AI requests per study day and provider (successes, errors by code, rate limits and
    exhausted quotas apart, tokens, mean duration) and this month's Azure use. No key, no prompt,
    no answer."""
    result = run(
        engine,
        lambda s: stats_progress.ai_stats(s, now, period.start, period.end, period.granularity),
    )
    return AiStatsOut(
        **header_fields(result.header),
        days=result.days,
        totals=result.totals,
        azure_month=result.azure_month,
    )


@router.get("/overview")
def overview(engine: EngineDep, now: NowDep) -> stats_progress.Overview:
    """The headline figures of the dashboard, each with its count."""
    return run(engine, lambda s: stats_progress.overview(s, now))
