"""`python -m app speech shadow | transcribe | compare` (module F, M6.a1).

`shadow --file <clip> --target "<sentence>" [--item <id>] [--duration <s>]` stores the recording
under `data/audio/` (`data/audio-demo/` with `--demo`), transcribes it with Groq Whisper and prints
the words that were not recognised. Without `--duration` the clip is transcribed first and Groq's
measure is used; with no provider (or no duration in its answer) nothing is stored and the command
asks for `--duration`. `transcribe <id>` runs the transcription again; `compare "<target>"
"<heard>"` is the pure comparison, without AI.

Exit codes, in the spirit of D-053: 0 done (silence included), 1 the transcription is unavailable
(the recording is kept: `speech transcribe <id>` later), 2 usage error (no database, unreadable or
refused clip, invalid sentence, unknown production, already transcribed).
"""

import sys
from pathlib import Path
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
from app.domain.enums import ProductionKind
from app.domain.speech_compare import Comparison, Op, compare
from app.domain.speech_rules import MAX_HEARD_CHARS
from app.services import productions, speech
from app.services.library import LibraryError
from app.speech.audio_store import AudioStore

if TYPE_CHECKING:
    from app.config import Settings

# File extension -> media type of the upload.
FILE_TYPES = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}
NOT_A_JUDGE = (
    "Speech recognition is not a pronunciation judge: a word it did not recognise is a possible "
    "intelligibility issue, nothing more."
)


# --- Rendering -----------------------------------------------------------------------------------


def _marked(comparison: Comparison) -> str:
    parts: list[str] = []
    for step in comparison.steps:
        if step.op is Op.MATCH:
            parts.append(step.target or "")
        elif step.op is Op.CLOSE:
            parts.append(f"{step.target}(~{step.heard})")
        elif step.op is Op.SUBSTITUTED:
            parts.append(f"[{step.target} -> {step.heard}]")
        elif step.op is Op.MISSING:
            parts.append(f"[{step.target} -> ---]")
        else:
            parts.append(f"(+{step.heard})")
    return " ".join(parts)


def render_comparison(target: str, heard: str, comparison: Comparison) -> str:
    total = comparison.target_word_count
    lines = [
        f"Target: {target}",
        f"Heard:  {heard}",
        f"        {_marked(comparison)}",
        f"Recognised {comparison.recognized_count} of {total} words "
        f"({comparison.word_accuracy:.0%}).",
    ]
    if comparison.unrecognized:
        lines.append("Not recognised (possible intelligibility issues):")
        for word in comparison.unrecognized:
            what = f"heard {word.heard!r}" if word.heard is not None else "not heard"
            lines.append(f"  word {word.position + 1}: {word.word!r}, {what}")
    close = [step for step in comparison.steps if step.op is Op.CLOSE]
    if close:
        listed = ", ".join(f"{step.target} ~ {step.heard}" for step in close)
        lines.append(f"Close spellings, counted as recognised: {listed}")
    extra = [step.heard for step in comparison.steps if step.op is Op.EXTRA]
    if extra:
        lines.append(f"Extra words heard: {', '.join(word or '' for word in extra)}")
    lines.append(NOT_A_JUDGE)
    return "\n".join(lines)


def _report(result: speech.SpeechResult, target: str, file: Path | None) -> int:
    seconds = f"{result.audio_seconds:g} s" if result.audio_seconds is not None else "length ?"
    print(f"Production #{result.production_id} ({seconds}).")
    if file is not None:
        print(f"Recording: {file}")
    outcome = result.transcription
    if outcome.status == "unavailable":
        print(
            f"Transcription unavailable ({outcome.reason}). The recording is kept: run "
            f"`python -m app speech transcribe {result.production_id}` later.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    if outcome.status == "silence":
        print("Nothing was heard (silence): no comparison.")
        return EXIT_OK
    if outcome.comparison is not None:
        print(render_comparison(target, outcome.text or "", outcome.comparison))
    else:
        print(f"Heard: {outcome.text}")
    return EXIT_OK


# --- Commands ------------------------------------------------------------------------------------


def run_speech_compare(target: str, heard: str) -> int:
    _console_safe()
    try:
        target = speech.check_target(target)
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    if len(heard) > MAX_HEARD_CHARS:
        print(f"The heard text has more than {MAX_HEARD_CHARS} characters.", file=sys.stderr)
        return EXIT_USAGE
    print(render_comparison(target, heard.strip(), compare(target, heard)))
    return EXIT_OK


def run_speech_shadow(
    url: str,
    settings: "Settings",
    file: Path,
    *,
    target: str,
    item_id: int | None = None,
    duration: float | None = None,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    content_type = FILE_TYPES.get(file.suffix.lower())
    if content_type is None:
        print(
            f"{file.name}: not an accepted recording. Use one of {', '.join(FILE_TYPES)}.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        data = file.read_bytes()
    except OSError as exc:
        print(f"Cannot read {file}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:  # refuse before any AI call
        extension = speech.check_audio(data, content_type)
        target = speech.check_target(target)
        if duration is not None:
            speech.check_duration(ProductionKind.SHADOWING, duration)
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
            print("No --duration: transcribing first to measure the recording...", flush=True)
            first = speech.transcribe_clip(gateway, data, extension)
            measured = first.data.duration_s if first.ok and first.data is not None else None
            if measured is None:
                why = "no duration in the answer" if first.ok else str(first.reason or "failed")
                print(
                    f"Groq could not measure the recording ({why}). Nothing was stored. Give its "
                    "length with --duration <seconds>.",
                    file=sys.stderr,
                )
                return EXIT_USAGE
        else:
            print("Transcribing...", flush=True)
        try:
            result = speech.record_shadowing(
                factory,
                gateway,
                store,
                data=data,
                content_type=content_type,
                target_text=target,
                duration_s=duration,
                item_id=item_id,
                transcription=first,
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        with factory() as session:
            audio_path = productions.get_production(session, result.production_id).audio_path
        return _report(result, target, store.root / audio_path if audio_path else None)
    finally:
        engine.dispose()


def run_speech_transcribe(
    url: str,
    settings: "Settings",
    production_id: int,
    *,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    store = AudioStore.for_settings(settings)
    try:
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        try:
            result = speech.transcribe_production(factory, gateway, store, production_id)
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        with factory() as session:
            target = productions.get_production(session, production_id).prompt_text or ""
        return _report(result, target, None)
    finally:
        engine.dispose()
