"""`python -m app curriculum tracks | show <code> [--page N] | start <code> | open <code> <n>`.

Module H, general English tracks.

`tracks` lists the general English tracks, `show` pages through a track's units (25 per page),
`start` creates the deck of a word-list track (again: the same deck), `open` puts a unit's words in
the triage queue (`library triage` is the screen for them). No AI call. `--demo` (before the
command) works on the demo database.

Exit codes, in the spirit of D-053: 0 done, 2 usage error (unknown track or unit, track not
started, word list missing, no database).
"""

import sys

from sqlalchemy.orm import Session

from app.cli_errors import _console_safe
from app.cli_library import EXIT_OK, EXIT_USAGE, _open
from app.db.base import utcnow
from app.services import curriculum
from app.services.library import LibraryError

PAGE_SIZE = curriculum.DEFAULT_LIMIT


def _track_line(track: curriculum.TrackSummary) -> str:
    if not track.available:
        state = f"unavailable ({track.reason})"
    elif track.started:
        state = f"started, {track.opened_units} opened, {track.triaged_units} triaged"
    else:
        state = "not started"
    return f"{track.code:<20} {track.kind.value:<9} {track.unit_count:>4} units  {state}"


def run_curriculum_tracks(url: str) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                tracks = curriculum.list_tracks(session)
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            for track in tracks:
                print(_track_line(track))
                print(f"{'':<20} {track.title.en}")
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_show(url: str, code: str, page: int) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                detail = curriculum.track_detail(
                    session, code, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
                )
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            track = detail.track
            pages = max(1, -(-detail.total_units // PAGE_SIZE))
            print(
                f"{track.title.en} ({track.code}), {detail.total_units} units, page {page}/{pages}"
            )
            if track.reason:
                print(f"Unavailable: {track.reason}", file=sys.stderr)
            for unit in detail.units:
                print(f"{unit.number:>4}  {unit.code:<22} {unit.state:<10} {unit.title}")
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_start(url: str, code: str) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                result = curriculum.start_track(session, code, utcnow())
            except LibraryError as exc:
                session.rollback()
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
        deck = result.track.deck_id
        print(
            f"Track '{code}' started"
            + (f": deck {deck}" if deck else "")
            + (" (created)." if result.created else " (already started).")
        )
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_open(url: str, code: str, number: int) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                result = curriculum.open_unit(session, code, number, utcnow())
            except LibraryError as exc:
                session.rollback()
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
        unit = result.unit
        if result.created:
            print(
                f"Unit {unit.code} opened: {result.imported} new, {result.attached} already in "
                f"the library, {result.skipped} skipped. They wait in the triage queue."
            )
        else:
            print(f"Unit {unit.code} was already open ({unit.state}); nothing changed.")
        print(", ".join(term.term for term in unit.terms))
        return EXIT_OK
    finally:
        engine.dispose()
