"""`python -m app curriculum tracks | show | start | open | generate | unit | step | terms | edit`.

Module H, general English tracks.

`tracks` lists the general English tracks, `show <code> [--page N]` pages through a track's units
(25 per page), `start <code>` creates the deck of a word-list track (again: the same deck), `open
<code> <n>` puts a word unit's words in the triage queue (`library triage` is the screen for them).

Scenario units (M8.a2): `generate <code> <n>` has the AI write a unit (formulas, model dialogue,
shadowing sentences, final speaking task; a few seconds); `unit <id>` prints it with its steps;
`step <id> formulas|dialogue` marks a step done; `terms <id> [--indices 0 1]` puts formulas in the
triage queue; `edit <id> --file parts.json` replaces parts of the content (`formulas`, `dialogue`,
`shadowing`, `final_task`, positions 0-based, the keys of `unit <id> --json`). The shadowing and the
final talk go through `speech shadow ... --unit <id>` and `speech speak ... --unit <id>`.
`--demo` (before the command) works on the demo database.

Exit codes, in the spirit of D-053: 0 done, 1 the AI could not write the unit (nothing was written,
try again), 2 usage error (unknown track or unit, track not started, word list missing, content
refused, no database).
"""

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.cli_errors import _console_safe
from app.cli_library import EXIT_FAILED, EXIT_OK, EXIT_USAGE, GatewayFactory, _build_gateway, _open
from app.db.base import utcnow
from app.services import curriculum, curriculum_units
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.config import Settings

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


def run_curriculum_generate(
    url: str,
    settings: "Settings",
    code: str,
    number: int,
    *,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        print(f"Asking the AI to write unit {number} of '{code}'...", flush=True)
        try:
            result = curriculum_units.generate_unit(factory, gateway, code, number)
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        if result.status != "ok" or result.unit is None:
            print(
                f"The AI could not write the unit ({result.reason or result.status}). Nothing was "
                "written: run the same command again later.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        print(render_unit(result.unit))
        return EXIT_OK
    finally:
        engine.dispose()


def render_unit(unit: curriculum.UnitOut) -> str:
    """A unit as text: its content when it has one, then its steps."""
    scenario = unit.scenario
    head = f"Unit #{unit.id} {unit.code} - {unit.title} ({unit.content_status}, {unit.progress})"
    if scenario is None:
        return head
    lines = [head, ""]
    lines.append(f"Revision {scenario.revision}, written by {scenario.provider or 'unknown'}")
    lines.append("")
    lines.append("Formulas:")
    for f in scenario.formulas:
        mark = f" [term #{f.item_id}]" if f.item_id else ""
        lines.append(f"  {f.index:>2}. {f.text}  ({f.item_type}, {f.style}){mark}")
        lines.append(f"      {f.function_en} / {f.function_fr}")
    dialogue = scenario.dialogue
    lines += ["", f"Dialogue: {dialogue['setting_en']}"]
    for i, line in enumerate(dialogue["lines"]):
        lines.append(f"  {i:>2}. {line['speaker']}: {line['text']}")
    lines += ["", "Shadowing:"]
    for s in scenario.shadowing:
        lines.append(f"  line {s.line_index}: {s.take_count} take(s) - {s.text}")
    task = scenario.final_task
    lines += ["", f"Final task ({task.minutes} min): {task.prompt_en}"]
    lines.append(f"  {task.prompt_fr}")
    lines += ["", "Steps:"]
    for step, done in scenario.steps.items():
        lines.append(f"  [{'x' if done else ' '}] {step}")
    lines.append(f"Next: {scenario.next_step or 'nothing, the unit is done'}")
    return "\n".join(lines)


def run_curriculum_unit(url: str, unit_id: int, *, as_json: bool = False) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                unit = curriculum.get_unit(session, unit_id)
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            if as_json and unit.scenario is not None:
                print(json.dumps(unit.scenario.model_dump(by_alias=True), indent=2))
            else:
                print(render_unit(unit))
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_step(url: str, unit_id: int, step: str) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                result = curriculum_units.mark_step(session, unit_id, step, utcnow())
            except LibraryError as exc:
                session.rollback()
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
        scenario = result.unit.scenario
        print(
            f"Step '{step}' "
            + ("marked done." if result.changed else "was already done.")
            + f" Unit: {result.unit.progress}."
            + (f" Next: {scenario.next_step}." if scenario and scenario.next_step else "")
        )
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_terms(url: str, unit_id: int, indices: list[int] | None) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                result = curriculum_units.add_terms(session, unit_id, indices, utcnow())
            except LibraryError as exc:
                session.rollback()
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
        print(
            f"{result.imported} formula(s) added, {result.attached} already in the library, "
            f"{result.skipped} skipped. They wait in the triage queue."
        )
        return EXIT_OK
    finally:
        engine.dispose()


def run_curriculum_edit(url: str, unit_id: int, file: Path) -> int:
    _console_safe()
    try:
        parts = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(parts, dict):
            raise ValueError("the file must hold one JSON object")
    except (OSError, ValueError) as exc:
        print(f"Cannot read {file}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                unit = curriculum_units.get_scenario(session, unit_id)
                revision = int((unit.content or {}).get("revision", 1))
                parts = {k: v for k, v in parts.items() if k != "expected_revision"}
                edit = curriculum_units.ContentEdit.model_validate(
                    {"expected_revision": revision, **parts}
                )
                curriculum_units.edit_content(session, unit_id, edit, utcnow())
            except ValueError as exc:  # pydantic: shapes
                session.rollback()
                print(f"The content is not valid: {exc}", file=sys.stderr)
                return EXIT_USAGE
            except LibraryError as exc:
                session.rollback()
                problems = exc.extra.get("problems") or []
                print("\n".join([exc.message, *[f"  - {p}" for p in problems]]), file=sys.stderr)
                return EXIT_USAGE
            session.commit()
        print(f"Unit #{unit_id} edited (revision {revision + 1}).")
        return EXIT_OK
    finally:
        engine.dispose()
