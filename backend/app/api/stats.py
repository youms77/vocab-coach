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
from app.db.engine import get_engine
from app.domain.stats import errors as error_rules
from app.domain.stats import memory as memory_rules
from app.domain.stats.common import Granularity, InvalidPeriod
from app.services import stats
from app.services.stats import Header, LapsedTerm, read_only

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_database)])

EngineDep = Annotated[Engine, Depends(get_engine)]


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
