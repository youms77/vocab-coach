"""AI usage per study day, computed from `ai_call_log` (no counter table, SPEC section 4 module I).

Read-only. A study day starts at `day_start_hour` in the `timezone` setting (D-014), so a call at
02:00 Douala time counts for the previous study day.
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import AICallLog
from app.db.settings_store import get_setting
from app.domain.study_day import study_day_bounds, study_day_of


@dataclass(frozen=True)
class ModelUsage:
    provider: str
    model: str
    requests: int  # every provider request made, retries included
    successes: int
    errors: dict[str, int]  # error code -> count
    input_tokens: int
    output_tokens: int
    avg_duration_ms: float | None


@dataclass(frozen=True)
class DailyAiUsage:
    day: date
    start: datetime  # [start, end) as UTC instants
    end: datetime
    rows: list[ModelUsage]

    @property
    def requests(self) -> int:
        return sum(row.requests for row in self.rows)

    @property
    def successes(self) -> int:
        return sum(row.successes for row in self.rows)

    @property
    def input_tokens(self) -> int:
        return sum(row.input_tokens for row in self.rows)

    @property
    def output_tokens(self) -> int:
        return sum(row.output_tokens for row in self.rows)


def _clock_settings(session: Session) -> tuple[ZoneInfo, int]:
    return ZoneInfo(get_setting(session, "timezone")), get_setting(session, "day_start_hour")


def study_day_now(session: Session, now: datetime) -> date:
    tz, day_start_hour = _clock_settings(session)
    return study_day_of(now, tz, day_start_hour)


def ai_usage_for_day(session: Session, day: date) -> DailyAiUsage:
    """Requests, successes, errors by type, tokens and mean duration per provider and model."""
    tz, day_start_hour = _clock_settings(session)
    start, end = study_day_bounds(day, tz, day_start_hour)
    in_day = (AICallLog.started_at >= start, AICallLog.started_at < end)

    totals = session.execute(
        select(
            AICallLog.provider,
            AICallLog.model,
            func.count(),
            func.sum(case((AICallLog.success.is_(True), 1), else_=0)),
            func.coalesce(func.sum(AICallLog.input_tokens), 0),
            func.coalesce(func.sum(AICallLog.output_tokens), 0),
            func.avg(AICallLog.duration_ms),
        )
        .where(*in_day)
        .group_by(AICallLog.provider, AICallLog.model)
        .order_by(AICallLog.provider, AICallLog.model)
    ).all()

    errors: dict[tuple[str, str], dict[str, int]] = {}
    failed = session.execute(
        select(AICallLog.provider, AICallLog.model, AICallLog.error_code, func.count())
        .where(*in_day, AICallLog.success.is_(False))
        .group_by(AICallLog.provider, AICallLog.model, AICallLog.error_code)
    ).all()
    for provider, model, code, count in failed:
        errors.setdefault((provider, model), {})[code or "unknown"] = count

    rows = [
        ModelUsage(
            provider=provider,
            model=model,
            requests=requests,
            successes=successes,
            errors=dict(sorted(errors.get((provider, model), {}).items())),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            avg_duration_ms=None if avg is None else float(avg),
        )
        for provider, model, requests, successes, input_tokens, output_tokens, avg in totals
    ]
    return DailyAiUsage(day=day, start=start, end=end, rows=rows)


def ai_usage_now(session: Session, now: datetime) -> DailyAiUsage:
    """Usage of the study day that contains `now`."""
    return ai_usage_for_day(session, study_day_now(session, now))
