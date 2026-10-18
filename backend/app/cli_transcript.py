"""`python -m app transcript analyse --file <txt> [--speaker LABEL | --mode ...] [--preview]`
(module E, M5.a2).

`--preview` parses the transcript and prints the turns, the labels and the problems: it writes
nothing and needs no database. Without it, the user's turns are recorded, then analysed by the AI
(the transcript is passed along, so the AI gets the other speaker's turns as context) and the
errors are printed (also logged: `errors list`). Without `--speaker` or `--mode`, the suggested
label is used ("You", "Me"...).

Exit codes, in the spirit of D-053: 0 done, 1 the AI could not analyse (the production is kept:
analyse it later with `POST /api/productions/<id>/correct`), 2 usage error (unreadable file,
refused transcript, no database, `--demo` for an AI call).
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
from app.domain.transcript_import import (
    TranscriptParse,
    UserByLabel,
    UserByMode,
    UserDesignation,
    parse_transcript,
)
from app.services import error_log, productions, transcripts
from app.services.library import LibraryError

if TYPE_CHECKING:
    from app.config import Settings

PREVIEW_CHARS = 70


def designation(speaker: str | None, mode: str | None) -> UserDesignation | None:
    if speaker:
        return UserByLabel(label=speaker)
    if mode:
        return UserByMode(mode=mode.replace("-", "_"))  # type: ignore[arg-type]
    return None


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 3] + "..."


def render_preview(parsed: TranscriptParse) -> str:
    lines = [f"{len(parsed.turns)} turn(s)."]
    if parsed.labels:
        lines.append("Speaker labels:")
        for label in parsed.labels:
            known = f" ({label.known})" if label.known else ""
            lines.append(
                f"  {label.label}{known}: {label.turns} turn(s), {label.words} word(s), "
                f"{label.chars} character(s)"
            )
    else:
        lines.append("No speaker labels.")
    lines.append(f"Suggested user label: {parsed.suggested_user_label or '(none)'}")
    lines.append("")
    for turn in parsed.turns:
        mine = {True: "*", False: " ", None: "?"}[turn.is_user]
        label = turn.speaker_label or "-"
        lines.append(
            f"{mine} {turn.index:>3}  line {turn.line_start:<4} {label:<12} {_short(turn.text)}"
        )
    if parsed.designation is not None:
        lines += [
            "",
            f"Your turns (*): {len(parsed.user_turns)}, {parsed.user_words} word(s), "
            f"{parsed.user_chars} character(s).",
        ]
    if parsed.problems:
        lines += ["", "Problems:"]
        for problem in parsed.problems:
            where = f"line {problem.line}: " if problem.line else ""
            lines.append(f"  [{problem.severity}] {problem.code}: {where}{problem.message}")
    return "\n".join(lines)


def run_transcript_analyse(
    url: str,
    settings: "Settings",
    file: Path,
    *,
    speaker: str | None = None,
    mode: str | None = None,
    preview: bool = False,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Cannot read {file}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    user = designation(speaker, mode)
    if preview:
        print(render_preview(parse_transcript(text, user)))
        return EXIT_OK
    if settings.demo:
        print(
            "transcript analyse calls the AI and is refused on the demo database; run it without "
            "--demo (or use --preview).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    parsed = parse_transcript(text, user)
    if parsed.designation is None:
        print(
            "Say which turns are yours: --speaker LABEL or --mode alternating-user-first | "
            "alternating-user-second | all-mine (see --preview).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    try:
        with factory() as session:
            try:
                attempt = transcripts.record_transcript(
                    session,
                    text=text,
                    user=parsed.designation,
                    title=file.stem,
                    occurred_on=None,
                    study_session_id=None,
                    at=utcnow(),
                )
            except LibraryError as exc:
                codes = exc.extra.get("codes") or []
                suffix = f" ({', '.join(codes)})" if codes else ""
                print(f"{exc.message}{suffix}", file=sys.stderr)
                return EXIT_USAGE
            session.commit()
            attempt_id, words = attempt.id, attempt.word_count
        print(
            f"Transcript #{attempt_id} recorded ({len(parsed.user_turns)} turn(s) of yours, "
            f"{words} words). Asking the AI...",
            flush=True,
        )
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        try:
            result = transcripts.analyse_transcript(
                factory,
                gateway,
                attempt_id,
                source=transcripts.TranscriptSource(text, parsed.designation),
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        if result.status != "ok":
            reason = f" ({result.reason.value})" if result.reason else ""
            print(
                f"The AI could not analyse this transcript: {result.status}{reason}. Transcript "
                f"#{attempt_id} is kept; analyse it later with "
                f"POST /api/productions/{attempt_id}/correct.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        with factory() as session:
            print(_render(session, attempt_id, result.error_ids, result.proposed_category_ids))
            session.rollback()
        return EXIT_OK
    finally:
        engine.dispose()


def _render(
    session: Session, attempt_id: int, error_ids: list[int], proposed_ids: list[int]
) -> str:
    attempt = productions.get_production(session, attempt_id)
    output = (attempt.ai_feedback or {}).get("output") or {}
    errors = list(
        session.scalars(
            select(ErrorEvent).where(ErrorEvent.id.in_(error_ids)).order_by(ErrorEvent.id)
        )
    )
    categories = error_log.categories_of(session, errors)
    lines = [f"Analysed: {len(errors)} error(s) in your turns."]
    for error in errors:
        lines += render_error_line(error, categories[error.category_id].code, None)
        if error.explanation:
            lines.append(f"       rule: {error.explanation}")
    notes = output.get("naturalness_notes") or []
    if notes:
        lines += ["", f"{len(notes)} naturalness note(s) (not errors):"]
        for note in notes:
            lines.append(f"  - {note['text']}  ->  {note['suggestion']}")
    if output.get("overall_comment"):
        lines += ["", output["overall_comment"]]
    if proposed_ids:
        lines += [
            "",
            f"{len(proposed_ids)} new category(ies) proposed by the AI: "
            "see `errors categories --proposed`.",
        ]
    return "\n".join(lines)
