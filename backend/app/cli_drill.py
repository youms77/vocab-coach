"""`python -m app drill new <category_code> [--count N]` and `drill list` (module E, M5.a2).

`drill new` has the AI write a targeted drill and prints the rule and the items **without their
solutions** (active recall: answer them through the API or, later, the drill screen). `drill list`
shows the drills, newest first, with their scores.

Exit codes, in the spirit of D-053: 0 done, 1 the AI could not write the drill (nothing stored), 2
usage error (unknown or refused category, no database, `--demo` for an AI call).
"""

import sys
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.cli_errors import _console_safe
from app.cli_library import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    GatewayFactory,
    _build_gateway,
    _open,
)
from app.db.models import ProductionAttempt
from app.domain import drills as rules
from app.services import drills
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.config import Settings


def render_drill(attempt: ProductionAttempt) -> str:
    feedback = attempt.ai_feedback or {}
    lines = [
        f"Drill #{attempt.id} on {feedback['category_code']} ({len(feedback['items'])} items).",
        "",
        f"Rule: {feedback['rule_en']}",
        f"      {feedback['rule_fr']}",
        "",
    ]
    for index, item in enumerate(feedback["items"]):
        public = rules.public_item(attempt.id, index, item)
        lines.append(f"{index:>3}. {public['sentence']}")
        if public["options"]:
            choices = "   ".join(f"[{n}] {option}" for n, option in enumerate(public["options"]))
            lines.append(f"     {choices}")
    lines += [
        "",
        f"Answer with POST /api/drills/{attempt.id}/items/<index>/answer "
        "(the solution comes after each answer).",
    ]
    return "\n".join(lines)


def run_drill_new(
    url: str,
    settings: "Settings",
    category_code: str,
    *,
    count: int = rules.DEFAULT_ITEMS,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    if settings.demo:
        print(
            "drill new calls the AI and is refused on the demo database; run it without --demo.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        print(f"Asking the AI for {count} items on {category_code}...", flush=True)
        try:
            result = drills.generate_drill(factory, gateway, category_code, count=count)
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        if result.drill_id is None:
            reason = f" ({result.reason.value})" if result.reason else ""
            print(
                f"The AI could not write the drill: {result.status}{reason}. Nothing was stored; "
                "try again later.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        with factory() as session:
            print(render_drill(drills.get_drill(session, result.drill_id)))
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def run_drill_list(url: str, *, limit: int = 20) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            page, total = drills.list_drills(session, limit=limit)
            if not page:
                print("No drill yet. Start one with `drill new <category_code>`.")
                return EXIT_OK
            print(f"{total} drill(s), newest first:")
            for attempt in page:
                feedback = attempt.ai_feedback or {}
                score = rules.score(len(feedback["items"]), feedback.get("answers", []))
                state = "done" if score["answered"] == score["total"] else "in progress"
                print(
                    f"#{attempt.id:<5} {attempt.created_at.date().isoformat()}  "
                    f"{feedback['category_code']:<45} {score['correct']}/{score['total']} "
                    f"correct, {score['answered']} answered ({state})"
                )
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()
