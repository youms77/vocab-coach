"""`python -m app errors list | show | add | categories` (module E, M5.a1).

Everything here works without an AI key. Exit codes, in the spirit of D-053: 0 done, 1 refused
(an invalid error or category), 2 usage error (no database, unknown id).
"""

import sys
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.cli_library import EXIT_FAILED, EXIT_OK, EXIT_USAGE, _open
from app.db.base import utcnow
from app.db.models import ErrorEvent
from app.domain.enums import ErrorSource
from app.services import error_log
from app.services.library import LibraryError


def _console_safe() -> None:
    # A learner's sentence may hold a character the Windows console cannot show: replace it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _short(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def render_error_line(error: ErrorEvent, code: str, term: str | None) -> list[str]:
    day = error.occurred_at.date().isoformat()
    lines = [f"#{error.id:<5} {day}  {error.source:<8} {code}"]
    detail = f"       {error.erroneous_text} -> {error.correction}"
    if term:
        detail += f"   [term: {term}]"
    lines.append(detail)
    if error.original_text:
        lines.append(f"       in: {_short(error.original_text)}")
    return lines


def run_errors_list(
    url: str,
    *,
    category: str | None = None,
    source: ErrorSource | None = None,
    item_id: int | None = None,
    text: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            result = error_log.list_errors(
                session,
                error_log.ErrorFilter(
                    category=category, source=source, lexical_item_id=item_id, text=text
                ),
                page=page,
                page_size=page_size,
            )
            categories = error_log.categories_of(session, result.errors)
            terms = error_log.terms_of(session, result.errors)
            if not result.total:
                print("No error matches.")
                return EXIT_OK
            first = (result.page - 1) * result.page_size + 1
            last = first + len(result.errors) - 1
            print(f"Errors {first}-{last} of {result.total} (newest first):")
            for error in result.errors:
                term = terms.get(error.lexical_item_id) if error.lexical_item_id else None
                for line in render_error_line(error, categories[error.category_id].code, term):
                    print(line)
            print("By category:")
            for facet in result.facets:
                print(f"  {facet.count:>4}  {facet.code}  ({facet.label_en})")
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    finally:
        engine.dispose()
    return EXIT_OK


def run_errors_show(url: str, error_id: int) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            error = error_log.get_error(session, error_id)
            category = error_log.categories_of(session, [error])[error.category_id]
            term = error_log.terms_of(session, [error]).get(error.lexical_item_id or 0)
            french = error_log.french_explanations(session, [error]).get(error.id)
            print(f"Error #{error.id} ({error.source}, {error.occurred_at.isoformat()})")
            print(f"  category:    {category.code} ({category.label_en}, {category.status})")
            if error.original_text:
                print(f"  sentence:    {error.original_text}")
            print(f"  wrong:       {error.erroneous_text}")
            print(f"  correction:  {error.correction}")
            if error.alternatives:
                print(f"  also:        {' | '.join(error.alternatives)}")
            if error.explanation:
                print(f"  rule:        {error.explanation}")
            if french:
                print(f"  rule (FR):   {french}")
            if term:
                print(f"  term:        #{error.lexical_item_id} {term}")
            if error.production_attempt_id:
                print(f"  production:  #{error.production_attempt_id}")
            if error.review_log_id:
                print(f"  review:      #{error.review_log_id}")
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    finally:
        engine.dispose()
    return EXIT_OK


def run_errors_add(
    url: str,
    *,
    wrong: str,
    correction: str,
    category: str,
    original: str | None = None,
    alternatives: Sequence[str] = (),
    explanation: str = "",
    item_id: int | None = None,
    now: datetime | None = None,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            error = error_log.add_manual_error(
                session,
                original_text=original,
                erroneous_text=wrong,
                correction=correction,
                alternatives=alternatives,
                category_code=category,
                explanation=explanation,
                lexical_item_id=item_id,
                at=now or utcnow(),
            )
            session.commit()
            print(f"Error #{error.id} recorded ({category}).")
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE if exc.status == 404 else EXIT_FAILED
    finally:
        engine.dispose()
    return EXIT_OK


def _render_node(node: error_log.CategoryNode, depth: int, lines: list[str]) -> None:
    mark = "" if node.status == "active" else f"  [{node.status}, #{node.id}]"
    origin = "" if node.origin == "builtin" else f"  ({node.origin})"
    lines.append(
        f"{'  ' * depth}{node.code:<{48 - 2 * depth}} {node.count:>4} {node.count_recent:>4}"
        f"{origin}{mark}"
    )
    for child in node.children:
        _render_node(child, depth + 1, lines)


def _proposed(nodes: list[error_log.CategoryNode]) -> list[error_log.CategoryNode]:
    found = []
    for node in nodes:
        if node.status == "proposed":
            found.append(node)
        found += _proposed(node.children)
    return found


def run_errors_categories(url: str, *, proposed_only: bool = False) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with Session(engine) as session:
            tree = error_log.category_tree(session, utcnow())
    finally:
        engine.dispose()
    if proposed_only:
        proposed = _proposed(tree)
        if not proposed:
            print("No category waits for your decision.")
            return EXIT_OK
        print("Categories proposed by the AI (accept or reject them in the app or with")
        print("POST /api/error-categories/{id}/resolve):")
        for node in proposed:
            print(f"  #{node.id:<4} {node.code}  {node.label_en} / {node.label_fr}  ({node.count})")
            if node.description_en:
                print(f"        {node.description_en}")
        return EXIT_OK
    if not tree:
        print("The taxonomy is empty. Run `python -m app db upgrade`.")
        return EXIT_FAILED
    lines = [f"{'code':<48} {'all':>4} {'14 d':>4}"]
    for root in tree:
        _render_node(root, 0, lines)
    print("\n".join(lines))
    return EXIT_OK
