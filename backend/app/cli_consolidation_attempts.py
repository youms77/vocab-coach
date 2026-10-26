"""`python -m app consolidation write | speak` (module G, M7.a2).

`write <task_id> --file <txt>` records the text as the production of a consolidation task, has the
AI correct it and applies the result to the terms of the task: the terms used correctly become
`active`, a term used wrongly gets its review card reinforced (an Again), the others are left as
they are. `speak <task_id> --file <clip> [--duration S]` does the same with a recorded talk (20 to
240 s, transcribed by Groq Whisper first). `--demo` (before the command) works on the demo database.

Exit codes, in the spirit of D-053: 0 done (silence included), 1 the transcription or the
correction is unavailable (the production is kept and no term changed; correct it later with
`POST /api/productions/<id>/correct`), 2 usage error (no database, unreadable or refused file,
unknown or closed task, text too long).
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
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
from app.cli_speech import _measure_first, _read_clip
from app.cli_write import render_correction
from app.db.base import utcnow
from app.db.models import Card
from app.domain.speech_rules import RecordingKind
from app.services import consolidation_attempts, productions, speech
from app.services.library import LibraryError
from app.speech.audio_store import AudioStore

if TYPE_CHECKING:
    from app.ai.gateway import Gateway
    from app.config import Settings


def render_summary(session: Session, summary: dict[str, Any] | None) -> str:
    """What the correction did to the terms of the task."""
    if summary is None:
        return "The terms of the task were not checked."
    activated = set(summary["activated_item_ids"])
    reinforced = set(
        session.scalars(
            select(Card.lexical_item_id).where(Card.id.in_(summary["reinforced_card_ids"]))
        )
    )
    names: dict[str, list[str]] = {"active": [], "reinforced": [], "absent": [], "other": []}
    for target, item in productions.targets_of(session, summary["production_attempt_id"]):
        if item.id in activated:
            names["active"].append(item.term)
        elif item.id in reinforced:
            names["reinforced"].append(item.term)
        elif target.used is False:
            names["absent"].append(item.term)
        else:
            names["other"].append(item.term)
    lines = [
        f"Terms of the task: {summary['targets']}; used {summary['used']}, used correctly "
        f"{summary['used_correctly']}, used wrongly {summary['misused']}, not used "
        f"{summary['absent']}.",
        f"  now active ({len(names['active'])}): {', '.join(names['active']) or '-'}",
        f"  to work on, review card reinforced ({len(names['reinforced'])}): "
        f"{', '.join(names['reinforced']) or '-'}",
        f"  not used ({len(names['absent'])}): {', '.join(names['absent']) or '-'}",
    ]
    if names["other"]:
        lines.append(f"  unchanged ({len(names['other'])}): {', '.join(names['other'])}")
    return "\n".join(lines)


def _report(factory: Callable[[], Session], gateway: "Gateway", attempt_id: int) -> int:
    try:
        result = consolidation_attempts.correct_consolidation(factory, gateway, attempt_id)
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    if result.status != "ok":
        reason = f" ({result.reason.value})" if result.reason else ""
        print(
            f"The AI could not correct this production: {result.status}{reason}. It is kept and "
            f"no term changed: correct it later with POST /api/productions/{attempt_id}/correct.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    with factory() as session:
        print(render_correction(session, attempt_id, result))
        print()
        print(render_summary(session, result.consolidation))
        session.rollback()
    return EXIT_OK


def run_consolidation_write(
    url: str,
    settings: "Settings",
    task_id: int,
    file: Path,
    *,
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
                attempt = consolidation_attempts.record_written(
                    session, task_id, text=text, study_session_id=None, at=utcnow()
                )
            except LibraryError as exc:
                print(exc.message, file=sys.stderr)
                return EXIT_USAGE
            session.commit()
            attempt_id, words = attempt.id, attempt.word_count
        print(f"Production #{attempt_id} recorded ({words} words). Asking the AI...", flush=True)
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        return _report(factory, gateway, attempt_id)
    finally:
        engine.dispose()


def run_consolidation_speak(
    url: str,
    settings: "Settings",
    task_id: int,
    file: Path,
    *,
    duration: float | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    clip = _read_clip(file)
    if clip is None:
        return EXIT_USAGE
    data, content_type = clip
    try:  # refuse before any AI call
        extension = speech.check_audio(data, content_type)
        if duration is not None:
            speech.check_duration(RecordingKind.CONSOLIDATION, duration)
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    store = AudioStore.for_settings(settings)
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        first = None
        if duration is None:
            first = _measure_first(gateway, data, extension)
            if first is None:
                return EXIT_USAGE
        else:
            print("Transcribing...", flush=True)
        try:
            result = consolidation_attempts.record_spoken(
                factory,
                gateway,
                store,
                task_id,
                data=data,
                content_type=content_type,
                duration_s=duration,
                transcription=first,
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        seconds = f"{result.audio_seconds:g} s" if result.audio_seconds is not None else "length ?"
        print(f"Production #{result.production_id} ({seconds}).", flush=True)
        outcome = result.transcription
        if outcome.status == "unavailable":
            print(
                f"Transcription unavailable ({outcome.reason}). The recording is kept: run "
                f"`python -m app speech transcribe {result.production_id}`, then "
                f"POST /api/productions/{result.production_id}/correct.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        if outcome.status == "silence":
            print("Nothing was heard (silence): nothing to correct.")
            return EXIT_OK
        print(f"Heard: {outcome.text}", flush=True)
        return _report(factory, gateway, result.production_id)
    finally:
        engine.dispose()
