"""`python -m app consolidation status | new | show | export` (module G, M7.a1).

`status` lists the decks, ready or not and why. `new <deck_id>` has the AI write a task (a talk, a
speech or an interview answer using 8 to 15 terms of the deck); without AI it is made from a
template and says so. `show <id>` prints a task, `export <id>` writes the Markdown page for a voice
tutor. `--demo` (before the command) works on the demo database.

Exit codes, in the spirit of D-053: 0 done, 2 usage error (unknown or not ready deck, no database,
unwritable file). Creating a task never fails because of the AI (a template takes over).
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.cli_errors import _console_safe
from app.cli_library import (
    EXIT_OK,
    EXIT_USAGE,
    GatewayFactory,
    _build_gateway,
    _open,
)
from app.domain import consolidation as rules
from app.domain.consolidation import TaskType
from app.services import consolidation
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.config import Settings

REASONS = {
    "excluded_kind": "an error-drill deck",
    "deck_done": "the deck is done",
    "task_open": "a task is already open",
    "no_productive_cards": "no productive card yet",
    "below_ratio": "not enough stable cards",
    "not_enough_candidates": f"fewer than {rules.MIN_TERMS} consolidated terms",
    "candidates_changed": "the terms of the deck changed, try again",
}


def run_consolidation_status(url: str) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            states = consolidation.deck_overview(session)
            if not states:
                print("No deck yet.")
                return EXIT_OK
            print(f"{'id':>4}  {'ready':<5}  {'stable':>9}  {'terms':>5}  deck")
            for state in states:
                readiness = state.readiness
                share = f"{readiness.stable_cards}/{readiness.productive_cards}"
                note = (
                    "" if readiness.ready else f"  -- {REASONS[readiness.reason.value]}"  # type: ignore[union-attr]
                )
                if state.open_task_id is not None:
                    note += f" (task {state.open_task_id})"
                print(
                    f"{state.deck.id:>4}  {'yes' if readiness.ready else 'no':<5}  {share:>9}  "
                    f"{len(readiness.candidates):>5}  {state.deck.name}{note}"
                )
            first = states[0]
            print(
                f"\nReady = at least {first.threshold_ratio:.0%} of the productive cards stable "
                f"({first.min_stability_days} days or more) and {rules.MIN_TERMS} consolidated "
                "terms."
            )
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def render_task(session: Session, task_id: int) -> str:
    from app.api.consolidation import task_out

    task = task_out(session, consolidation.get_task(session, task_id))
    lines = [
        f"Task #{task.id}: {task.title.en}",
        f"                {task.title.fr}",
        f"Deck: {task.deck.name}   Type: {task.task_type.value}   Status: {task.status.value}   "
        f"Written by: {task.source}",
        "",
        f"Prompt: {task.prompt.en}",
        f"        {task.prompt.fr}",
        f"Audience: {task.audience.en}   Target: {task.target_minutes} min",
        "",
        "Structure:",
    ]
    term_of = {t.item_id: t.term for t in task.targets}
    for number, section in enumerate(task.sections, start=1):
        terms = ", ".join(term_of[i] for i in section.item_ids if i in term_of)
        lines.append(f"  {number}. {section.heading.en}: {section.guidance.en}")
        lines.append(f"     terms: {terms}")
    lines += ["", f"Terms ({len(task.targets)}):"]
    lines += [f"  - {t.term} [{t.item_status}]" for t in task.targets]
    return "\n".join(lines)


def run_consolidation_new(
    url: str,
    settings: "Settings",
    deck_id: int,
    *,
    task_type: TaskType = TaskType.TALK,
    count: int | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        print(f"Asking the AI for a {task_type.value.replace('_', ' ')}...", flush=True)
        try:
            result = consolidation.create_task(
                factory, gateway, deck_id, task_type, term_count=count
            )
        except LibraryError as exc:
            reason = exc.extra.get("reason")
            detail = f" ({REASONS.get(reason, reason)})" if reason else ""
            if exc.code == "task_open":
                detail = f" (task {exc.extra.get('task_id')})"
            print(f"{exc.message}{detail}", file=sys.stderr)
            return EXIT_USAGE
        if result.source == "template":
            print(
                f"The AI could not write the task ({result.reason}): it was made from a "
                "template instead.",
                flush=True,
            )
        with factory() as session:
            print(render_task(session, result.task_id))
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_consolidation_show(url: str, task_id: int) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                print(render_task(session, task_id))
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_consolidation_export(
    url: str, task_id: int, *, lang: str = "en", out: Path | None = None
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            try:
                task = consolidation.get_task(session, task_id)
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            text = consolidation.export_markdown(session, task, "fr" if lang == "fr" else "en")
            session.rollback()
        if out is None:
            print(text, end="")
            return EXIT_OK
        try:
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"Cannot write {out}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        print(f"Written to {out}.")
        return EXIT_OK
    finally:
        engine.dispose()
