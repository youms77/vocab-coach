"""`python -m app write correct --file <txt> [--prompt ...]` (module E, M5.a1).

Records the text as a writing production, has the AI correct it and prints the errors (also logged:
`errors list`) and the naturalness notes. Exit codes, in the spirit of D-053: 0 corrected, 1 the AI
could not correct (the production is kept: correct it later with
`POST /api/productions/<id>/correct`), 2 usage error (no database, unreadable file, refused text).
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli_errors import _console_safe, render_error_line
from app.cli_library import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    GatewayFactory,
    _build_gateway,
    _open,
)
from app.db.base import utcnow
from app.db.models import ErrorEvent
from app.domain.enums import ErrorSource
from app.services import corrections, error_log, productions
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.config import Settings


def run_write_correct(
    url: str,
    settings: "Settings",
    file: Path,
    *,
    prompt: str | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Cannot read {file}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        with factory() as session:
            try:
                attempt = productions.create_writing(
                    session,
                    text=text,
                    prompt=prompt,
                    target_item_ids=[],
                    study_session_id=None,
                    at=utcnow(),
                )
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
            attempt_id, words = attempt.id, attempt.word_count
        print(f"Production #{attempt_id} recorded ({words} words). Asking the AI...", flush=True)
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        try:
            result = corrections.correct_production(
                factory, gateway, attempt_id, source=ErrorSource.WRITING
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        if result.status != "ok":
            reason = f" ({result.reason.value})" if result.reason else ""
            print(
                f"The AI could not correct this text: {result.status}{reason}. Production "
                f"#{attempt_id} is kept; correct it later with "
                f"POST /api/productions/{attempt_id}/correct.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        with factory() as session:
            print(_render(session, attempt_id, result))
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def _render(session: Session, attempt_id: int, result: corrections.CorrectionResult) -> str:
    attempt = productions.get_production(session, attempt_id)
    feedback = attempt.ai_feedback or {}
    output = feedback.get("output") or {}
    errors = list(
        session.scalars(
            select(ErrorEvent).where(ErrorEvent.id.in_(result.error_ids)).order_by(ErrorEvent.id)
        )
    )
    categories = error_log.categories_of(session, errors)
    terms = error_log.terms_of(session, errors)
    lines = [f"Corrected: {len(errors)} error(s)."]
    for error in errors:
        code = categories[error.category_id].code
        lines += render_error_line(error, code, terms.get(error.lexical_item_id or 0))
        if error.explanation:
            lines.append(f"       rule: {error.explanation}")
    notes = output.get("naturalness_notes") or []
    if notes:
        lines.append("")
        lines.append(f"{len(notes)} naturalness note(s) (not errors):")
        for note in notes:
            lines.append(f"  - {note['text']}  ->  {note['suggestion']}")
            if note.get("note"):
                lines.append(f"    {note['note']}")
    if output.get("corrected_text"):
        lines += ["", "Corrected text:", f"  {output['corrected_text']}"]
    if output.get("natural_text"):
        lines += ["", "More natural:", f"  {output['natural_text']}"]
    if output.get("overall_comment"):
        lines += ["", output["overall_comment"]]
    if result.proposed_category_ids:
        lines += [
            "",
            f"{len(result.proposed_category_ids)} new category(ies) proposed by the AI: "
            "see `errors categories --proposed`.",
        ]
    return "\n".join(lines)
