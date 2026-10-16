"""Command line: `python -m app [--reload]` runs the API; `python -m app db ...` manages the DB;
`python -m app plan today` prints today's session plan (read-only); `python -m app demo seed`
builds the fictional demo database; `python -m app ai simulate` shows the AI gateway at work
offline. `--demo` (before the command) works on the demo database."""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cli_plan import CommandError, build_today_plan, render_plan
from app.config import get_settings
from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.taxonomy import SyncResult, sync_taxonomy

SQLITE_SIDE_FILES = ("-wal", "-shm")


def db_upgrade(url: str) -> SyncResult:
    """`alembic upgrade head`, then load the built-in error taxonomy. Safe to run repeatedly."""
    migrate.upgrade(url)
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            result = sync_taxonomy(session)
            session.commit()
    finally:
        engine.dispose()
    return result


def db_reset(url: str, now: datetime | None = None) -> Path | None:
    """Move the current database aside as `<name>.bak-YYYYMMDD-HHMMSS`, then recreate it.

    Returns the backup path (None when there was no database file).
    """
    db_file = sqlite_file(url)
    if db_file is None:
        raise ValueError(f"db reset only works with a SQLite file database, not {url!r}")
    backup: Path | None = None
    if db_file.exists():
        # Fold the write-ahead log into the main file so the backup is complete on its own.
        engine = create_db_engine(url)
        try:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        finally:
            engine.dispose()
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005 (local time, for humans)
        backup = db_file.with_name(f"{db_file.name}.bak-{stamp}")
        db_file.rename(backup)
        for suffix in SQLITE_SIDE_FILES:
            side = db_file.with_name(db_file.name + suffix)
            if side.exists():
                side.rename(backup.with_name(backup.name + suffix))
    db_upgrade(url)
    return backup


def _serve(reload: bool) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=reload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description=__doc__)
    parser.add_argument("--reload", action="store_true", help="restart the API on code changes")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use the demo database (data/vocab-coach-demo.sqlite3), same as VOCAB_DEMO=1",
    )
    commands = parser.add_subparsers(dest="command")

    db = commands.add_parser("db", help="manage the SQLite database")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("upgrade", help="apply migrations and load the error taxonomy")
    reset = db_commands.add_parser(
        "reset", help="back up the current database file, then recreate an empty one"
    )
    reset.add_argument("--yes", action="store_true", help="confirm the reset")

    plan = commands.add_parser("plan", help="session planning (read-only)")
    plan_commands = plan.add_subparsers(dest="plan_command", required=True)
    today = plan_commands.add_parser("today", help="print today's session plan")
    today.add_argument(
        "--at", help="plan as of this ISO date-time (e.g. 2026-11-01T08:00; local if no offset)"
    )
    today.add_argument("--json", action="store_true", help="print the raw plan as JSON")

    demo = commands.add_parser("demo", help="fictional demo data (always the demo database)")
    demo_commands = demo.add_subparsers(dest="demo_command", required=True)
    seed = demo_commands.add_parser(
        "seed", help="generate the demo database from content/demo/ (deterministic)"
    )
    seed.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    seed.add_argument("--days", type=int, default=60, help="days of history (default 60)")
    seed.add_argument(
        "--anchor",
        type=date.fromisoformat,
        help="anchor study day, YYYY-MM-DD (default: the current study day)",
    )
    seed.add_argument(
        "--reset", action="store_true", help="rebuild an existing demo database (no backup)"
    )
    seed.add_argument(
        "--if-missing",
        action="store_true",
        help="do nothing when the demo database already holds demo data (launch scripts)",
    )

    ai = commands.add_parser("ai", help="AI gateway tools (no network, no personal data)")
    ai_commands = ai.add_subparsers(dest="ai_command", required=True)
    ai_commands.add_parser(
        "simulate",
        help="run three gateway scenarios with fake providers on a throwaway database",
    )
    return parser


def _demo_seed(args: argparse.Namespace, demo_file: Path) -> int:
    # Imported here: the simulation pulls in every service, which other commands do not need.
    from app.demo.seed import DemoSeedError, check_target, is_seeded, render_summary, seed_demo

    if args.if_missing and is_seeded(demo_file):
        print(f"Demo database already seeded ({demo_file}).")
        return 0
    try:
        check_target(demo_file, reset=args.reset)  # refuse before announcing anything
        print(f"Generating the demo database ({demo_file})...", flush=True)
        summary = seed_demo(
            demo_file, seed=args.seed, days=args.days, anchor=args.anchor, reset=args.reset
        )
    except DemoSeedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"demo seed failed: {exc}", file=sys.stderr)
        return 1
    print(render_summary(summary))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.demo:
        # Through the environment so the API's reload subprocess inherits it too.
        os.environ["VOCAB_DEMO"] = "1"
        get_settings.cache_clear()
    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 1
    if args.command is None:
        return _serve(args.reload)

    if args.command == "demo":
        # Never the personal database: always the demo file, whatever VOCAB_DATABASE_URL says.
        return _demo_seed(args, settings.demo_database_file)
    if args.command == "ai":
        # A throwaway database: the personal one is never opened.
        from app.ai.simulate import run_simulation

        return run_simulation()
    url = settings.resolved_database_url
    if args.command == "plan":
        try:
            plan = build_today_plan(url, args.at)
        except CommandError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(plan.model_dump_json(indent=2) if args.json else render_plan(plan))
        return 0
    try:
        if args.db_command == "upgrade":
            result = db_upgrade(url)
            print(
                f"Database ready ({url}). Error taxonomy: "
                f"{result.added} added, {result.updated} updated."
            )
        elif args.db_command == "reset":
            if not args.yes:
                print(
                    "db reset moves the current database aside (a .bak-<date> copy stays in the "
                    "same folder) and creates an empty one.\n"
                    "Nothing was changed. Run `python -m app db reset --yes` to confirm.",
                    file=sys.stderr,
                )
                return 2
            backup = db_reset(url)
            print(f"Previous database saved as {backup}." if backup else "No database to back up.")
            print(f"Empty database created ({url}).")
    except PermissionError as exc:
        print(
            f"Cannot access the database file ({exc}). Is the app still running?", file=sys.stderr
        )
        return 1
    except Exception as exc:
        print(f"Database command failed: {exc}", file=sys.stderr)
        return 1
    return 0
