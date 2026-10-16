"""`python -m app plan today`: today's session plan in the terminal. Read-only."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.settings_store import get_setting
from app.domain.planner import (
    BlockKind,
    ConsolidationEntry,
    NewItemEntry,
    ReviewEntry,
    SessionPlan,
    TargetedPracticeEntry,
)
from app.services.planning import plan_today


class CommandError(Exception):
    """The command cannot run; the message tells the user what to do."""


def build_today_plan(url: str, at: str | None) -> SessionPlan:
    """Plan as of `at` (ISO date-time; without an offset it is local time in the `timezone`
    setting), or now.

    Read-only: the connection is switched to `PRAGMA query_only`, so SQLite itself refuses any
    write, and the session is rolled back.
    """
    db_file = sqlite_file(url)
    if db_file is not None and not db_file.exists():
        raise CommandError(f"No database at {db_file}. Run `python -m app db upgrade` first.")
    engine = create_db_engine(url)
    try:
        if not migrate.schema_status(engine).at_head:
            raise CommandError("The database is not up to date. Run `python -m app db upgrade`.")
        with Session(engine) as session:
            session.execute(text("PRAGMA query_only = ON"))
            try:
                now = parse_at(at, ZoneInfo(get_setting(session, "timezone")))
                return plan_today(session, now)
            finally:
                session.rollback()
    finally:
        engine.dispose()


def parse_at(at: str | None, tz: ZoneInfo) -> datetime:
    if at is None:
        return datetime.now(UTC)
    try:
        moment = datetime.fromisoformat(at)
    except ValueError:
        raise CommandError(
            f"--at: {at!r} is not an ISO date-time (e.g. 2026-11-01T08:00)"
        ) from None
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment


def _duration(seconds: float) -> str:
    minutes, rest = divmod(round(seconds), 60)
    if minutes and rest:
        return f"{minutes} min {rest} s"
    return f"{minutes} min" if minutes else f"{rest} s"


def _beyond(overflow: bool) -> str:
    return " [beyond budget]" if overflow else ""


def render_plan(plan: SessionPlan) -> str:
    """Human-readable plan (a developer tool: English, no i18n)."""
    caps = plan.caps
    lines = [
        f"Study day {plan.study_day.isoformat()} "
        f"(planned at {plan.generated_at:%Y-%m-%d %H:%M} UTC)",
        f"Budget: {_duration(plan.budget_seconds)} | "
        f"Estimated total: {_duration(plan.total_seconds)}",
        f"New terms allowed: {plan.new_items_allowed} "
        f"(limit: {plan.limit.value.replace('_', ' ')}; caps: quota {caps.quota}, "
        f"budget {caps.budget}, anticipation {caps.anticipation}, available {caps.available})",
        "",
    ]

    reviews = plan.block(BlockKind.REVIEWS)
    if reviews:
        entries = [e for e in reviews.entries if isinstance(e, ReviewEntry)]
        overflow = sum(1 for e in entries if e.overflow)
        lines.append(
            f"1. Reviews: {len(entries)} card(s), {_duration(reviews.estimated_seconds)}"
            + (f", {overflow} beyond the budget" if overflow else "")
        )
    else:
        lines.append("1. Reviews: none due")

    new = plan.block(BlockKind.NEW_ITEMS)
    if new:
        items = [e for e in new.entries if isinstance(e, NewItemEntry)]
        ids = ", ".join(f"{e.lexical_item_id}{' (resumed)' if e.resumed else ''}" for e in items)
        lines.append(f"2. New terms: {len(items)}, {_duration(new.estimated_seconds)} (ids {ids})")
    else:
        lines.append("2. New terms: none")

    targeted = plan.block(BlockKind.TARGETED_PRACTICE)
    if targeted and isinstance(drill := targeted.entries[0], TargetedPracticeEntry):
        lines.append(
            f"3. Targeted practice: {drill.category_code} ({drill.error_count} errors), "
            f"{_duration(drill.estimated_seconds)}{_beyond(drill.overflow)}"
        )
    else:
        lines.append("3. Targeted practice: none")

    consolidation = plan.block(BlockKind.CONSOLIDATION)
    if consolidation and isinstance(task := consolidation.entries[0], ConsolidationEntry):
        lines.append(
            f"4. Consolidation: task {task.consolidation_task_id}, "
            f"{_duration(task.estimated_seconds)}{_beyond(task.overflow)}"
        )
    else:
        lines.append("4. Consolidation: none pending")

    if plan.decks_to_activate:
        lines.append(f"Decks to activate: {', '.join(map(str, plan.decks_to_activate))}")
    for pace in plan.deadline_paces:
        lines.append(
            f"Deadline: deck {pace.deck_id} on {pace.deadline.isoformat()}, {pace.remaining} "
            f"term(s) left over {pace.days_left} day(s): {pace.required_per_day} per day"
        )
    if plan.warnings:
        lines.append("Warnings:")
        for warning in plan.warnings:
            params = ", ".join(f"{key}={value}" for key, value in warning.params.items())
            lines.append(f"  - {warning.code.value}: {params}")
    if plan.observed_durations:
        lines.append(f"Observed durations used for: {', '.join(plan.observed_durations)}")
    return "\n".join(lines)
