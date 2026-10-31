"""`python -m app library import | enrich | extend`.

`import <file>`: preview a Markdown, CSV or TSV list (format from the extension, or `--format`),
or import it with `--commit`.

Without `--commit` nothing is written (the connection is read-only). With `--commit` the clear
lines are imported with the default duplicate choices; ambiguous lines are left out (they need a
correction or a confirmation, which the web page offers).

Exit codes, in the spirit of D-053: 0 preview shown or import done (even with ambiguous lines);
1 the file is refused (too large, not UTF-8) or nothing could be imported; 2 usage error (missing
file, no database, unknown deck).

`enrich`: usage sheets for the terms waiting for one, batch after batch (`--dry-run` only lists
them). `extend <deck_id>`: related terms suggested by the AI, waiting for triage. Exit codes: 0
done, 1 the AI was unavailable (nothing is lost: run again later), 2 usage error.
"""

import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.engine import create_db_engine, sqlite_file
from app.db.settings_store import get_setting
from app.domain.markdown_import import (
    MAX_BYTES,
    ImportProblem,
    decode_import_bytes,
    not_utf8_problem,
    too_large_problem,
)
from app.domain.study_day import study_day_of
from app.domain.tabular_import import ImportFormat
from app.services import importing
from app.services.importing import ImportPreview, ImportTarget, PreviewRow
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.ai.gateway import Gateway
    from app.config import Settings

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


class _Usage(Exception):
    pass


def _problem_line(problem: ImportProblem, indent: str) -> str:
    where = f"line {problem.line}: " if problem.line and not indent else ""
    return f"{indent}{problem.severity.value} {problem.code.value}: {where}{problem.message}"


def _marker(row: PreviewRow) -> str:
    if row.ambiguous:
        return "?"  # needs a correction or a confirmation
    if not row.include or row.in_target_deck:
        return "-"  # skipped
    if row.default_on_duplicate == "attach":
        return "~"  # an existing term is added to the deck
    return "+"


def render_preview(preview: ImportPreview, path: Path) -> str:
    header = preview.header
    lines = [f"Import preview of {path.name} (nothing written)"]
    fields = [(name, getattr(header, name)) for name in type(header).model_fields]
    shown = [f"  {name}: {value}" for name, value in fields if value is not None]
    lines += ["Header:", *shown] if shown else ["Header: none"]
    lines += [_problem_line(problem, "") for problem in preview.problems]
    if preview.rows:
        lines.append("Lines (+ new, ~ existing term added, - skipped, ? ambiguous):")
    for row in preview.rows:
        sentence = f" | {row.sentence}" if row.sentence else ""
        lines.append(f"  {_marker(row)} L{row.line:<4} {row.term}{sentence}  [{row.item_type}]")
        lines += [_problem_line(problem, "        ") for problem in row.problems]
        for candidate in row.duplicates:
            decks = ", ".join(deck.name for deck in candidate.decks) or "no deck"
            lines.append(
                f"        {candidate.match.value} duplicate: #{candidate.id} "
                f"'{candidate.term}' ({candidate.status.value}; {decks})"
            )
    lines.append(
        f"{preview.lines_read} lines read, {preview.importable} to import, "
        f"{preview.ambiguous} ambiguous, {preview.with_duplicates} with a duplicate."
    )
    return "\n".join(lines)


def _read(path: Path) -> str:
    if not path.is_file():
        raise _Usage(f"No such file: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(_problem_line(too_large_problem(), ""))
    decoded = decode_import_bytes(path.read_bytes())
    if decoded is None:
        raise ValueError(_problem_line(not_utf8_problem(), ""))
    return decoded


def format_of(path: Path) -> ImportFormat:
    """`.csv` and `.tsv` are tables; everything else (`.md`, `.txt`...) is read as Markdown."""
    return {".csv": "csv", ".tsv": "tsv"}.get(path.suffix.lower(), "markdown")  # type: ignore[return-value]


def run_library_import(
    url: str,
    path: Path,
    *,
    fmt: ImportFormat | None = None,
    deck_id: int | None = None,
    no_triage: bool = False,
    commit: bool = False,
    now: datetime | None = None,
) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # a pasted character the console cannot show
    try:
        content = _read(path)
    except _Usage as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAILED

    db_file = sqlite_file(url)
    if db_file is not None and not db_file.exists():
        print(f"No database at {db_file}. Run `python -m app db upgrade` first.", file=sys.stderr)
        return EXIT_USAGE
    now = now or datetime.now(UTC)
    engine = create_db_engine(url)
    try:
        if not migrate.schema_status(engine).at_head:
            print(
                "The database is not up to date. Run `python -m app db upgrade`.", file=sys.stderr
            )
            return EXIT_USAGE
        with Session(engine) as session:
            session.execute(text("PRAGMA query_only = ON"))
            try:
                today = study_day_of(
                    now,
                    ZoneInfo(get_setting(session, "timezone")),
                    get_setting(session, "day_start_hour"),
                )
                preview = importing.preview(
                    session, content, today, deck_id=deck_id, fmt=fmt or format_of(path)
                )
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            finally:
                session.rollback()
                session.execute(text("PRAGMA query_only = OFF"))
        print(render_preview(preview, path))
        if preview.rejected:
            return EXIT_FAILED
        if not commit:
            print("Run again with --commit to import the lines marked + and ~.")
            return EXIT_OK
        return _commit(engine, preview, path, deck_id=deck_id, no_triage=no_triage, now=now)
    finally:
        engine.dispose()


def _commit(
    engine: Engine,
    preview: ImportPreview,
    path: Path,
    *,
    deck_id: int | None,
    no_triage: bool,
    now: datetime,
) -> int:
    rows = importing.default_rows(preview)
    if not any(row.include for row in rows):
        print("Nothing to import: every line is ambiguous or a duplicate.", file=sys.stderr)
        return EXIT_FAILED
    target = ImportTarget(deck_id=deck_id)
    if deck_id is None and not preview.header.deck:
        target = ImportTarget(new_deck_name=path.stem)  # no `deck:` in the header: the file name
    with Session(engine) as session:
        try:
            summary = importing.commit(
                session,
                header=preview.header,
                rows=rows,
                target=target,
                intake="queued" if no_triage else "triage",
                at=now,
            )
            session.commit()
        except LibraryError as exc:
            session.rollback()
            print(f"Import refused ({exc.code}): {exc.message}", file=sys.stderr)
            return EXIT_FAILED
    where = "new deck" if summary.created_deck else "deck"
    intake = "queued" if no_triage else "waiting for triage"
    print(
        f"Imported into {where} #{summary.deck_id}: {summary.imported} new ({intake}), "
        f"{summary.attached} existing added, {summary.skipped} skipped "
        f"({summary.ambiguous} ambiguous left out)."
    )
    return EXIT_OK


# --- library enrich / library extend (M3.b) ------------------------------------------------------


def _open(url: str) -> Engine | None:
    db_file = sqlite_file(url)
    if db_file is not None and not db_file.exists():
        print(f"No database at {db_file}. Run `python -m app db upgrade` first.", file=sys.stderr)
        return None
    engine = create_db_engine(url)
    if not migrate.schema_status(engine).at_head:
        engine.dispose()
        print("The database is not up to date. Run `python -m app db upgrade`.", file=sys.stderr)
        return None
    return engine


def _build_gateway(engine: Engine, settings: "Settings") -> "Gateway":
    from app.ai.gateway import Gateway
    from app.ai.providers import build_providers

    return Gateway(
        lambda: build_providers(settings),
        session_factory=lambda: Session(engine, expire_on_commit=False),
        secrets=settings.secret_values,
    )


GatewayFactory = Callable[[Engine], "Gateway"]


def run_library_enrich(
    url: str,
    settings: "Settings",
    *,
    deck_id: int | None = None,
    item_ids: Sequence[int] = (),
    include_incomplete: bool = False,
    dry_run: bool = False,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    """Run batches until nothing is left (or the AI is unavailable). Exit 0 when every batch ran,
    1 when the AI was unavailable, 2 on a usage error."""
    from app.services import enrichment

    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        with factory() as session:
            try:
                if item_ids:
                    waiting = enrichment.explicit_waiting(session, item_ids)
                else:
                    waiting = enrichment.list_pending(
                        session, deck_id=deck_id, include_incomplete=include_incomplete
                    )
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            rows = [(item.id, item.term, str(item.status)) for item in waiting]
            session.rollback()
        print(f"{len(rows)} term(s) waiting for a usage sheet.")
        for item_id, term, status in rows:
            print(f"  #{item_id:<5} {term}  [{status}]")
        if dry_run or not rows:
            return EXIT_OK
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        totals = {"generated": 0, "needs_completion": 0, "superseded": 0, "failed": 0}
        batch = 0
        while True:
            batch += 1
            report = enrichment.run_enrichment(
                factory,
                gateway,
                deck_id=deck_id,
                item_ids=list(item_ids) or None,
                include_incomplete=include_incomplete,
            )
            for key in totals:
                totals[key] += getattr(report, key)
            reason = f", {report.reason.value}" if report.reason else ""
            print(
                f"Batch {batch} ({len(report.item_ids)} terms): {report.status}{reason}; "
                f"{report.generated} sheet(s), {report.needs_completion} to complete, "
                f"{report.remaining} left."
            )
            progress = report.generated + report.needs_completion + report.superseded
            if report.status == "unavailable" or report.remaining == 0 or progress == 0:
                break
        print(
            f"Done: {totals['generated']} sheet(s) generated, {totals['needs_completion']} "
            f"to complete by hand, {totals['superseded']} dropped (changed meanwhile), "
            f"{report.remaining} still waiting."
        )
        if report.status == "unavailable":
            print(
                "The AI is unavailable"
                + (f" ({report.reason.value})" if report.reason else "")
                + ": the terms stay waiting. You can type a sheet by hand.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        return EXIT_OK
    except enrichment.EnrichmentRunning as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_FAILED
    finally:
        engine.dispose()


def run_library_extend(
    url: str,
    settings: "Settings",
    deck_id: int,
    *,
    count: int,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    """Ask the AI for related terms; they wait in triage. Exit 0 / 1 (AI failed) / 2 (usage)."""
    from app.services import extension

    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        try:
            report = extension.extend_deck(
                lambda: Session(engine, expire_on_commit=False), gateway, deck_id, count=count
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        if report.status != "ok":
            reason = f" ({report.reason.value})" if report.reason else ""
            print(f"No suggestion: the AI answer was {report.status}{reason}.", file=sys.stderr)
            return EXIT_FAILED
        with Session(engine) as session:
            from app.db.models import LexicalItem

            terms = [session.get(LexicalItem, i) for i in report.created]
            print(
                f"{len(report.created)} new term(s) waiting for triage in deck #{deck_id} "
                f"({report.suggested} suggested, {report.dropped_existing} already in the "
                f"library, {report.dropped_in_batch} repeated or extra):"
            )
            possible = {p.item_id for p in report.possible_duplicates}
            for item in terms:
                if item is not None:
                    mark = "  (possible duplicate)" if item.id in possible else ""
                    print(f"  #{item.id:<5} {item.term}{mark}")
        print("Sort them with the triage (GET /api/triage, or the library page).")
        return EXIT_OK
    finally:
        engine.dispose()
