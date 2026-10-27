"""Command line: `python -m app [--reload]` runs the API; `python -m app db ...` manages the DB;
`python -m app plan today` prints today's session plan (read-only); `python -m app demo seed`
builds the fictional demo database; `python -m app ai simulate` shows the AI gateway at work
offline; `python -m app ai status | test | usage` look at the real AI providers;
`python -m app library import <file>` previews (or, with `--commit`, imports) a Markdown list;
`library enrich` writes usage sheets through the AI and `library extend <deck_id>` asks for related
terms. `python -m app errors list | show | add | categories | card | suggestions | dismiss` reads
and edits the error log (`card` makes a review card from an error) and
`write correct --file <txt>` has the AI correct a text; `transcript analyse --file <txt>` finds
your errors in a conversation transcript; `drill new <code>` and `drill list` are targeted drills.
`consolidation status | new <deck_id> | show <id> | export <id> | write <id> --file |
speak <id> --file` are the consolidation tasks. `curriculum tracks | show <code> | start <code> |
open <code> <n> | generate <code> <n> | unit <id> | step | terms | edit` are the general English
tracks (word lists, then scenario units written by the AI).
`stats summary`, `stats errors | memory [--from] [--to] [--granularity]` print statistics and
`stats export [--out file.zip] [--force]` writes every event table as CSV in a zip archive.
`backup create [--out file.zip] [--force]` writes a full backup (all tables as JSON lines and the
recordings), `backup verify <zip>` checks one, `backup restore <zip> [--replace --yes]` restores it
into an empty database with the app stopped, `backup auto` makes the automatic copy now.
`speech shadow --file <clip> --target "<sentence>"` records, transcribes and compares a shadowing,
`speech transcribe <id>` transcribes it again, `speech compare "<target>" "<heard>"` compares two
texts without AI; `speech speak --file <clip> [--prompt "<topic>"]` records free speaking and has
the AI correct what was heard, `speech correct <id>` corrects it again, `speech assess <id>`
scores a shadowing's pronunciation with Azure (optional). `--demo` (before the command) works on
the demo database."""

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
from app.config import Settings, get_settings
from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.taxonomy import SyncResult, sync_taxonomy
from app.domain.enums import ErrorSource
from app.domain.settings_defaults import KNOWN_AI_PROVIDERS, KNOWN_SPEECH_PROVIDERS
from app.domain.stats.common import Granularity

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

    ai = commands.add_parser("ai", help="AI gateway tools")
    ai_commands = ai.add_subparsers(dest="ai_command", required=True)
    ai_commands.add_parser(
        "simulate",
        help="run three gateway scenarios with fake providers on a throwaway database "
        "(no network, no personal data)",
    )
    ai_commands.add_parser(
        "status", help="which providers are configured, their models and order (no network)"
    )
    test = ai_commands.add_parser(
        "test",
        help="one real call per configured provider (uses free quota, writes ai_call_log)",
    )
    test.add_argument(
        "--provider",
        choices=(*KNOWN_AI_PROVIDERS, *KNOWN_SPEECH_PROVIDERS),
        help="test this provider only (azure: assess one second of silence)",
    )
    test.add_argument(
        "--audio", type=Path, metavar="FILE", help="also transcribe this short clip (Groq Whisper)"
    )
    usage = ai_commands.add_parser("usage", help="requests and tokens per study day (read-only)")
    usage.add_argument(
        "--days", type=_days, default=7, help="how many study days to look back (1-90, default 7)"
    )
    library = commands.add_parser("library", help="vocabulary library")
    library_commands = library.add_subparsers(dest="library_command", required=True)
    importer = library_commands.add_parser(
        "import", help="preview a Markdown list (writes nothing unless --commit)"
    )
    importer.add_argument("file", type=Path, help="the Markdown file (UTF-8)")
    importer.add_argument("--deck-id", type=int, help="add to this deck instead of a new one")
    importer.add_argument(
        "--no-triage", action="store_true", help="queue the new terms directly (skip triage)"
    )
    importer.add_argument(
        "--commit", action="store_true", help="import the clear lines with the default choices"
    )
    enrich = library_commands.add_parser(
        "enrich", help="generate usage sheets for the terms waiting for one (AI)"
    )
    enrich.add_argument("--deck-id", type=int, help="only the terms of this deck")
    enrich.add_argument(
        "--item-id",
        type=int,
        action="append",
        default=[],
        dest="item_ids",
        metavar="N",
        help="only this term (repeatable; any status but archived)",
    )
    enrich.add_argument(
        "--include-incomplete",
        action="store_true",
        help="also retry the sheets left to complete (needs_completion)",
    )
    enrich.add_argument(
        "--dry-run", action="store_true", help="only list the terms waiting for a sheet"
    )
    extend = library_commands.add_parser(
        "extend", help="ask the AI for related terms for a deck (they wait for triage)"
    )
    extend.add_argument("deck_id", type=int, help="the deck to extend")
    extend.add_argument(
        "--count", type=_count, default=20, help="how many suggestions (10-30, default 20)"
    )

    errors = commands.add_parser("errors", help="error log (module E)")
    errors_commands = errors.add_subparsers(dest="errors_command", required=True)
    listing = errors_commands.add_parser("list", help="your errors, newest first")
    listing.add_argument("--category", help="a code prefix, e.g. grammar.preposition")
    listing.add_argument("--source", choices=[source.value for source in ErrorSource])
    listing.add_argument("--item-id", type=int, help="errors linked to this term")
    listing.add_argument("--text", help="search the sentence, wrong form, correction, rule")
    listing.add_argument("--page", type=_positive, default=1)
    listing.add_argument("--page-size", type=_positive, default=20, help="1 to 100")
    show = errors_commands.add_parser("show", help="one error in full")
    show.add_argument("error_id", type=int)
    add = errors_commands.add_parser("add", help="record an error by hand (source manual)")
    add.add_argument("--wrong", required=True, help="the wrong form")
    add.add_argument("--correction", required=True)
    add.add_argument("--category", required=True, help="an active code, see `errors categories`")
    add.add_argument("--original", help="the whole sentence (must contain the wrong form)")
    add.add_argument("--alt", action="append", default=[], help="a natural alternative (at most 2)")
    add.add_argument("--explanation", default="", help="the rule in one sentence")
    add.add_argument("--item-id", type=int, help="link the error to this term")
    card = errors_commands.add_parser("card", help="make a term and a review card from an error")
    card.add_argument("error_id", type=int)
    card.add_argument("--term", help="the term to learn (default: the correction)")
    card.add_argument("--sentence", help="a sentence that uses the correction (default: yours)")
    suggestions = errors_commands.add_parser(
        "suggestions", help="recurring errors that could become cards"
    )
    suggestions.add_argument("--min-count", type=_positive, default=2)
    suggestions.add_argument("--limit", type=_positive, default=20, help="1 to 50")
    dismiss = errors_commands.add_parser("dismiss", help="stop suggesting a recurring error")
    dismiss.add_argument("key", help="the key printed by `errors suggestions`")
    categories = errors_commands.add_parser("categories", help="the error taxonomy with counts")
    categories.add_argument(
        "--proposed", action="store_true", help="only the categories the AI proposed"
    )
    write = commands.add_parser("write", help="written productions (module E)")
    write_commands = write.add_subparsers(dest="write_command", required=True)
    correct = write_commands.add_parser(
        "correct", help="record a text, have the AI correct it and log its errors"
    )
    correct.add_argument("--file", type=Path, required=True, help="a UTF-8 text file")
    correct.add_argument("--prompt", help="the task or topic the text answers (500 characters)")
    transcript = commands.add_parser("transcript", help="conversation transcripts (module E)")
    transcript_commands = transcript.add_subparsers(dest="transcript_command", required=True)
    analyse = transcript_commands.add_parser(
        "analyse", help="record your turns of a transcript and have the AI find your errors"
    )
    analyse.add_argument("--file", type=Path, required=True, help="a UTF-8 text file")
    who = analyse.add_mutually_exclusive_group()
    who.add_argument("--speaker", help="the label of your turns (default: the suggested one)")
    who.add_argument(
        "--mode",
        choices=["alternating-user-first", "alternating-user-second", "all-mine"],
        help="which turns are yours when there are no labels",
    )
    analyse.add_argument(
        "--preview", action="store_true", help="show the turns and problems, write nothing"
    )
    drill = commands.add_parser("drill", help="targeted drills on one error category (module E)")
    drill_commands = drill.add_subparsers(dest="drill_command", required=True)
    new = drill_commands.add_parser("new", help="have the AI write a drill (no solutions shown)")
    new.add_argument("category_code", help="a level-2 code or deeper, see `errors categories`")
    new.add_argument(
        "--count",
        type=int,
        default=10,
        choices=range(5, 16),
        metavar="N",
        help="number of items, 5 to 15 (default 10)",
    )
    drill_commands.add_parser("list", help="your drills, newest first, with their scores")

    curriculum = commands.add_parser(
        "curriculum", help="general English tracks: NGSL, NAWL and speaking scenarios (module H)"
    )
    curriculum_commands = curriculum.add_subparsers(dest="curriculum_command", required=True)
    curriculum_commands.add_parser("tracks", help="the tracks and where you are in each")
    k_show = curriculum_commands.add_parser("show", help="the units of one track, 25 per page")
    k_show.add_argument("code")
    k_show.add_argument("--page", type=_positive, default=1, help="page number (default 1)")
    k_start = curriculum_commands.add_parser("start", help="start a track (creates its deck)")
    k_start.add_argument("code")
    k_open = curriculum_commands.add_parser(
        "open", help="open a unit: its words wait in the triage queue"
    )
    k_open.add_argument("code")
    k_open.add_argument("number", type=_positive)
    k_generate = curriculum_commands.add_parser(
        "generate", help="have the AI write a scenario unit (a few seconds; needs a key)"
    )
    k_generate.add_argument("code")
    k_generate.add_argument("number", type=_positive)
    k_unit = curriculum_commands.add_parser("unit", help="print a unit with its steps")
    k_unit.add_argument("unit_id", type=_positive)
    k_unit.add_argument("--json", action="store_true", help="the content as JSON")
    k_step = curriculum_commands.add_parser(
        "step", help="mark the formulas or the dialogue as done"
    )
    k_step.add_argument("unit_id", type=_positive)
    k_step.add_argument("step", choices=["formulas", "dialogue"])
    k_terms = curriculum_commands.add_parser(
        "terms", help="put the formulas of a unit in the triage queue"
    )
    k_terms.add_argument("unit_id", type=_positive)
    k_terms.add_argument(
        "--indices", type=int, nargs="+", help="formulas to add, 0-based (default: all)"
    )
    k_edit = curriculum_commands.add_parser(
        "edit", help="replace parts of a unit's content from a JSON file"
    )
    k_edit.add_argument("unit_id", type=_positive)
    k_edit.add_argument("--file", type=Path, required=True)

    stats_parser = commands.add_parser(
        "stats", help="statistics and CSV export (module I, read-only)"
    )
    stats_commands = stats_parser.add_subparsers(dest="stats_command", required=True)
    for name, help_text in (
        ("errors", "error rates per 100 words, top 5 recurring errors, lasting trends"),
        ("memory", "retention, success by exercise type, lapses, time before consolidation"),
    ):
        stats_command = stats_commands.add_parser(name, help=help_text)
        stats_command.add_argument(
            "--from", dest="start", type=_iso_date, help="first study day (YYYY-MM-DD)"
        )
        stats_command.add_argument("--to", dest="end", type=_iso_date, help="last study day")
        stats_command.add_argument(
            "--granularity", choices=[g.value for g in Granularity], default="day"
        )
    stats_commands.add_parser("summary", help="the headline figures (last 28 and 7 study days)")
    s_export = stats_commands.add_parser(
        "export", help="all event tables as CSV in a zip archive, for pandas"
    )
    s_export.add_argument(
        "--out", type=Path, help="target .zip (default: data/exports/vocab-coach-export-DATE.zip)"
    )
    s_export.add_argument("--force", action="store_true", help="replace an existing file")

    backup_parser = commands.add_parser(
        "backup", help="full backup and restore: all data and recordings in a zip (module J)"
    )
    backup_commands = backup_parser.add_subparsers(dest="backup_command", required=True)
    b_create = backup_commands.add_parser("create", help="write a full backup archive")
    b_create.add_argument(
        "--out",
        type=Path,
        help="target .zip (default: data/backups/vocab-coach-backup-DATE-TIME.zip)",
    )
    b_create.add_argument("--force", action="store_true", help="replace an existing file")
    b_verify = backup_commands.add_parser("verify", help="check an archive, writing nothing")
    b_verify.add_argument("archive", type=Path)
    b_restore = backup_commands.add_parser(
        "restore", help="restore an archive into an empty database (stop the app first)"
    )
    b_restore.add_argument("archive", type=Path)
    b_restore.add_argument(
        "--replace",
        action="store_true",
        help="replace a database that holds data (the old one is kept as *.bak-DATE-TIME)",
    )
    b_restore.add_argument("--yes", action="store_true", help="confirm --replace")
    backup_commands.add_parser("auto", help="make the automatic copy into the chosen folder now")

    consolidation = commands.add_parser(
        "consolidation", help="consolidation tasks: use your solid terms in a talk (module G)"
    )
    consolidation_commands = consolidation.add_subparsers(
        dest="consolidation_command", required=True
    )
    consolidation_commands.add_parser("status", help="the decks, ready or not and why")
    c_new = consolidation_commands.add_parser(
        "new", help="have the AI write a task for a ready deck (a template without AI)"
    )
    c_new.add_argument("deck_id", type=_positive)
    c_new.add_argument(
        "--type",
        choices=["talk", "speech", "interview_answer"],
        default="talk",
        help="the kind of task (default talk)",
    )
    c_new.add_argument(
        "--count",
        type=int,
        default=None,
        choices=range(8, 16),
        metavar="N",
        help="number of terms, 8 to 15 (default 12)",
    )
    c_show = consolidation_commands.add_parser("show", help="one task in full")
    c_show.add_argument("task_id", type=_positive)
    c_write = consolidation_commands.add_parser(
        "write", help="submit your written text for a task, have it corrected and check the terms"
    )
    c_write.add_argument("task_id", type=_positive)
    c_write.add_argument("--file", type=Path, required=True, help="a UTF-8 text file")
    c_speak = consolidation_commands.add_parser(
        "speak", help="submit your recorded talk (20 to 240 s) for a task"
    )
    c_speak.add_argument("task_id", type=_positive)
    c_speak.add_argument(
        "--file", type=Path, required=True, help="the clip (.m4a, .webm, .ogg, .wav, .mp3)"
    )
    c_speak.add_argument(
        "--duration", type=float, default=None, help="seconds; measured by Groq when omitted"
    )
    c_export = consolidation_commands.add_parser(
        "export", help="the Markdown page to paste into a voice chat with a tutor"
    )
    c_export.add_argument("task_id", type=_positive)
    c_export.add_argument("--lang", choices=["en", "fr"], default="en")
    c_export.add_argument("--out", type=Path, default=None, help="write to this file")

    speech = commands.add_parser("speech", help="recordings and speech recognition (module F)")
    speech_commands = speech.add_subparsers(dest="speech_command", required=True)
    shadow = speech_commands.add_parser(
        "shadow", help="store a recording of a sentence, transcribe it and compare it"
    )
    shadow.add_argument(
        "--file", type=Path, required=True, help="the clip (.m4a, .webm, .ogg, .wav, .mp3)"
    )
    shadow.add_argument("--target", required=True, help="the sentence you repeated")
    shadow.add_argument("--item", type=_positive, help="the id of the term worked on")
    shadow.add_argument(
        "--unit", type=_positive, help="the scenario unit this take belongs to (module H)"
    )
    shadow.add_argument(
        "--duration",
        type=float,
        help="length in seconds (without it, the duration measured by Groq is used)",
    )
    shadow.add_argument(
        "--assess",
        action="store_true",
        help="then score the pronunciation with Azure (needs the pronunciation_assessment setting)",
    )
    assess = speech_commands.add_parser(
        "assess",
        help="score a stored shadowing with Azure, word by word (the recording goes to Microsoft)",
    )
    assess.add_argument("production_id", type=_positive)
    transcribe = speech_commands.add_parser(
        "transcribe", help="transcribe again a recording that has no transcription yet"
    )
    transcribe.add_argument("production_id", type=_positive)
    compare = speech_commands.add_parser(
        "compare", help="compare a sentence with what was heard, word by word (no AI)"
    )
    compare.add_argument("target", help="the sentence to say")
    compare.add_argument("heard", help="what speech recognition wrote")
    speak = speech_commands.add_parser(
        "speak", help="store free speaking (5 to 180 s), transcribe it and correct what was heard"
    )
    speak.add_argument(
        "--file", type=Path, required=True, help="the clip (.m4a, .webm, .ogg, .wav, .mp3)"
    )
    speak.add_argument("--prompt", help="the topic you spoke about (at most 500 characters)")
    speak.add_argument(
        "--unit",
        type=_positive,
        help="the final task of this scenario unit (module H): its prompt and terms are used",
    )
    speak.add_argument(
        "--duration",
        type=float,
        help="length in seconds (without it, the duration measured by Groq is used)",
    )
    speak.add_argument(
        "--no-correct",
        action="store_true",
        help="transcribe only; correct it later with `speech correct <id>`",
    )
    correct = speech_commands.add_parser(
        "correct", help="have the AI correct a transcribed free speaking (or a spoken answer)"
    )
    correct.add_argument("production_id", type=_positive)
    return parser


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a date (YYYY-MM-DD)") from None


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _count(value: str) -> int:
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if not 10 <= count <= 30:
        raise argparse.ArgumentTypeError("--count must be between 10 and 30")
    return count


def _days(value: str) -> int:
    try:
        days = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number of days") from None
    if not 1 <= days <= 90:
        raise argparse.ArgumentTypeError("--days must be between 1 and 90")
    return days


def _ai(args: argparse.Namespace, settings: Settings) -> int:
    if args.ai_command == "simulate":
        # A throwaway database: the personal one is never opened.
        from app.ai.simulate import run_simulation

        return run_simulation()

    from app import cli_ai
    from app.ai.providers import build_providers
    from app.ai.redact import clean_message

    # A transcript or an error message may hold a character the console cannot show: replace it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    # `ai usage --demo` reads the demo database's log (M3.b: `library enrich --demo` fills it).
    if args.demo and args.ai_command == "test":
        print(
            f"`ai {args.ai_command}` works on your personal database (D-033, D-064): run it "
            "without --demo.",
            file=sys.stderr,
        )
        return cli_ai.EXIT_USAGE
    url = settings.resolved_database_url
    try:
        providers = build_providers(settings)
        if args.ai_command == "status":
            return cli_ai.run_ai_status(url, settings, providers)
        if args.ai_command == "test":
            return cli_ai.run_ai_test(
                url, settings, providers, provider=args.provider, audio=args.audio
            )
        return cli_ai.run_ai_usage(url, cli_ai.UsageOptions(days=args.days))
    except cli_ai.AiCommandError as exc:
        print(str(exc), file=sys.stderr)
        return cli_ai.EXIT_USAGE
    except Exception as exc:
        message = clean_message(str(exc), settings.secret_values(), cli_ai.MESSAGE_LIMIT)
        print(f"ai {args.ai_command} failed ({type(exc).__name__}): {message}", file=sys.stderr)
        return cli_ai.EXIT_FAILED


def _errors(args: argparse.Namespace, url: str) -> int:
    from app import cli_errors

    if args.errors_command == "list":
        return cli_errors.run_errors_list(
            url,
            category=args.category,
            source=ErrorSource(args.source) if args.source else None,
            item_id=args.item_id,
            text=args.text,
            page=args.page,
            page_size=args.page_size,
        )
    if args.errors_command == "show":
        return cli_errors.run_errors_show(url, args.error_id)
    if args.errors_command == "add":
        return cli_errors.run_errors_add(
            url,
            wrong=args.wrong,
            correction=args.correction,
            category=args.category,
            original=args.original,
            alternatives=args.alt,
            explanation=args.explanation,
            item_id=args.item_id,
        )
    if args.errors_command == "card":
        return cli_errors.run_errors_card(
            url, args.error_id, term=args.term, sentence=args.sentence
        )
    if args.errors_command == "suggestions":
        return cli_errors.run_errors_suggestions(url, min_count=args.min_count, limit=args.limit)
    if args.errors_command == "dismiss":
        return cli_errors.run_errors_dismiss(url, args.key)
    return cli_errors.run_errors_categories(url, proposed_only=args.proposed)


def _demo_seed(args: argparse.Namespace, settings: Settings) -> int:
    # Imported here: the simulation pulls in every service, which other commands do not need.
    from app.demo.seed import DemoSeedError, check_target, is_seeded, render_summary, seed_demo
    from app.speech.audio_store import AudioStore

    demo_file = settings.demo_database_file

    if args.if_missing and is_seeded(demo_file):
        print(f"Demo database already seeded ({demo_file}).")
        return 0
    try:
        check_target(demo_file, reset=args.reset)  # refuse before announcing anything
        print(f"Generating the demo database ({demo_file})...", flush=True)
        summary = seed_demo(
            demo_file,
            seed=args.seed,
            days=args.days,
            anchor=args.anchor,
            reset=args.reset,
            audio_dir=AudioStore.demo(settings).root,
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
        return _demo_seed(args, settings)
    if args.command == "ai":
        return _ai(args, settings)
    url = settings.resolved_database_url
    if args.command == "backup":
        from app import cli_backup

        if args.backup_command == "create":
            return cli_backup.run_backup_create(url, settings, args.out, force=args.force)
        if args.backup_command == "verify":
            return cli_backup.run_backup_verify(args.archive)
        if args.backup_command == "restore":
            return cli_backup.run_backup_restore(
                settings, args.archive, replace=args.replace, yes=args.yes
            )
        return cli_backup.run_backup_auto(url, settings)
    if args.command == "library":
        from app import cli_library

        if args.library_command == "enrich":
            return cli_library.run_library_enrich(
                url,
                settings,
                deck_id=args.deck_id,
                item_ids=args.item_ids,
                include_incomplete=args.include_incomplete,
                dry_run=args.dry_run,
            )
        if args.library_command == "extend":
            return cli_library.run_library_extend(url, settings, args.deck_id, count=args.count)
        return cli_library.run_library_import(
            url, args.file, deck_id=args.deck_id, no_triage=args.no_triage, commit=args.commit
        )
    if args.command == "errors":
        return _errors(args, url)
    if args.command == "write":
        from app import cli_write

        return cli_write.run_write_correct(url, settings, args.file, prompt=args.prompt)
    if args.command == "drill":
        from app import cli_drill

        if args.drill_command == "new":
            return cli_drill.run_drill_new(url, settings, args.category_code, count=args.count)
        return cli_drill.run_drill_list(url)
    if args.command == "curriculum":
        from app import cli_curriculum

        if args.curriculum_command == "tracks":
            return cli_curriculum.run_curriculum_tracks(url)
        if args.curriculum_command == "show":
            return cli_curriculum.run_curriculum_show(url, args.code, args.page)
        if args.curriculum_command == "start":
            return cli_curriculum.run_curriculum_start(url, args.code)
        if args.curriculum_command == "generate":
            return cli_curriculum.run_curriculum_generate(url, settings, args.code, args.number)
        if args.curriculum_command == "unit":
            return cli_curriculum.run_curriculum_unit(url, args.unit_id, as_json=args.json)
        if args.curriculum_command == "step":
            return cli_curriculum.run_curriculum_step(url, args.unit_id, args.step)
        if args.curriculum_command == "terms":
            return cli_curriculum.run_curriculum_terms(url, args.unit_id, args.indices)
        if args.curriculum_command == "edit":
            return cli_curriculum.run_curriculum_edit(url, args.unit_id, args.file)
        return cli_curriculum.run_curriculum_open(url, args.code, args.number)
    if args.command == "stats":
        from app import cli_stats

        if args.stats_command == "summary":
            return cli_stats.run_stats_summary(url)
        if args.stats_command == "export":
            return cli_stats.run_stats_export(
                url, settings.resolved_data_dir, args.out, force=args.force
            )
        run = (
            cli_stats.run_stats_errors
            if args.stats_command == "errors"
            else cli_stats.run_stats_memory
        )
        return run(url, args.start, args.end, Granularity(args.granularity))
    if args.command == "consolidation":
        from app import cli_consolidation
        from app.domain.consolidation import TaskType

        if args.consolidation_command == "status":
            return cli_consolidation.run_consolidation_status(url)
        if args.consolidation_command == "new":
            return cli_consolidation.run_consolidation_new(
                url, settings, args.deck_id, task_type=TaskType(args.type), count=args.count
            )
        if args.consolidation_command == "show":
            return cli_consolidation.run_consolidation_show(url, args.task_id)
        if args.consolidation_command in ("write", "speak"):
            from app import cli_consolidation_attempts as attempts

            if args.consolidation_command == "write":
                return attempts.run_consolidation_write(url, settings, args.task_id, args.file)
            return attempts.run_consolidation_speak(
                url, settings, args.task_id, args.file, duration=args.duration
            )
        return cli_consolidation.run_consolidation_export(
            url, args.task_id, lang=args.lang, out=args.out
        )
    if args.command == "speech":
        from app import cli_speech

        if args.speech_command == "compare":
            return cli_speech.run_speech_compare(args.target, args.heard)
        if args.speech_command == "transcribe":
            return cli_speech.run_speech_transcribe(url, settings, args.production_id)
        if args.speech_command == "speak":
            return cli_speech.run_speech_speak(
                url,
                settings,
                args.file,
                prompt=args.prompt,
                duration=args.duration,
                correct=not args.no_correct,
                unit_id=args.unit,
            )
        if args.speech_command == "correct":
            return cli_speech.run_speech_correct(url, settings, args.production_id)
        if args.speech_command == "assess":
            return cli_speech.run_speech_assess(url, settings, args.production_id)
        return cli_speech.run_speech_shadow(
            url,
            settings,
            args.file,
            target=args.target,
            item_id=args.item,
            duration=args.duration,
            assess=args.assess,
            unit_id=args.unit,
        )
    if args.command == "transcript":
        from app import cli_transcript

        return cli_transcript.run_transcript_analyse(
            url,
            settings,
            args.file,
            speaker=args.speaker,
            mode=args.mode,
            preview=args.preview,
        )
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
