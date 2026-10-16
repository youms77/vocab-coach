"""AI usage per study day, including the 04:00 boundary in Africa/Douala (UTC+1)."""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db.models import AICallLog
from app.db.settings_store import set_setting
from app.services.ai_usage import ai_usage_for_day, ai_usage_now

DAY = date(2026, 10, 16)  # study day: 2026-10-16 04:00 to 2026-10-17 04:00 Douala


def call(
    at: datetime,
    *,
    provider: str = "gemini",
    model: str = "m1",
    success: bool = True,
    error_code: str | None = None,
    tokens: tuple[int, int] | None = (10, 5),
    duration_ms: int | None = 100,
) -> AICallLog:
    return AICallLog(
        started_at=at,
        provider=provider,
        model=model,
        task="connection_test",
        success=success,
        error_code=error_code,
        input_tokens=tokens[0] if tokens else None,
        output_tokens=tokens[1] if tokens else None,
        duration_ms=duration_ms,
        attempt=1,
    )


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def test_usage_by_provider_and_model(session: Session) -> None:
    session.add_all(
        [
            call(utc(16, 10), duration_ms=100),
            call(utc(16, 11), duration_ms=300, tokens=(20, 10)),
            call(utc(16, 12), success=False, error_code="rate_limited", tokens=None),
            call(utc(16, 13), success=False, error_code="rate_limited", tokens=None),
            call(utc(16, 14), success=False, error_code="network", tokens=None),
            call(utc(16, 15), provider="groq", model="llama", duration_ms=None, tokens=(7, 3)),
        ]
    )
    session.commit()

    usage = ai_usage_for_day(session, DAY)

    gemini, groq = usage.rows
    assert (gemini.provider, gemini.model, gemini.requests, gemini.successes) == (
        "gemini",
        "m1",
        5,
        2,
    )
    assert gemini.errors == {"network": 1, "rate_limited": 2}
    assert (gemini.input_tokens, gemini.output_tokens) == (30, 15)
    assert gemini.avg_duration_ms is not None and 100 <= gemini.avg_duration_ms <= 300
    assert (groq.requests, groq.successes, groq.errors, groq.avg_duration_ms) == (1, 1, {}, None)
    assert (usage.requests, usage.successes) == (6, 3)
    assert (usage.input_tokens, usage.output_tokens) == (37, 18)


def test_empty_day(session: Session) -> None:
    usage = ai_usage_for_day(session, DAY)
    assert usage.rows == [] and usage.requests == 0


def test_the_study_day_starts_at_04_00_in_douala(session: Session) -> None:
    # Douala is UTC+1, so 04:00 local is 03:00 UTC.
    session.add_all(
        [
            call(utc(16, 2, 59)),  # 03:59 Douala: still the previous study day
            call(utc(16, 3, 0)),  # 04:00 Douala: first minute of the day
            call(utc(17, 2, 59)),  # 03:59 next morning: last minute of the day
            call(utc(17, 3, 0)),  # 04:00 next morning: the next study day
        ]
    )
    session.commit()

    assert ai_usage_for_day(session, DAY).requests == 2
    assert ai_usage_for_day(session, date(2026, 10, 15)).requests == 1
    assert ai_usage_for_day(session, date(2026, 10, 17)).requests == 1


def test_bounds_follow_the_timezone_and_start_hour_settings(session: Session) -> None:
    set_setting(session, "day_start_hour", 0)
    set_setting(session, "timezone", "UTC")
    session.add_all([call(utc(16, 0, 0)), call(utc(15, 23, 59))])
    session.commit()

    usage = ai_usage_for_day(session, DAY)
    assert usage.requests == 1
    assert usage.start == utc(16, 0)


def test_usage_now_picks_the_study_day_of_the_moment(session: Session) -> None:
    session.add(call(utc(16, 10)))
    session.commit()
    # 02:00 Douala on the 17th is still the study day of the 16th.
    assert ai_usage_now(session, utc(17, 1)).requests == 1
    assert ai_usage_now(session, utc(17, 3)).requests == 0
