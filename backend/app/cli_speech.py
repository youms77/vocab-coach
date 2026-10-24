"""`python -m app speech shadow | transcribe | compare | speak | correct | assess` (module F,
M6.a1, M6.a2a, M6.c1).

`shadow --file <clip> --target "<sentence>" [--item <id>] [--duration <s>]` stores the recording
under `data/audio/` (`data/audio-demo/` with `--demo`), transcribes it with Groq Whisper and prints
the words that were not recognised. Without `--duration` the clip is transcribed first and Groq's
measure is used; with no provider (or no duration in its answer) nothing is stored and the command
asks for `--duration`. `transcribe <id>` runs the transcription again; `compare "<target>"
"<heard>"` is the pure comparison, without AI.

`speak --file <clip> [--prompt TEXT] [--duration S] [--no-correct]` stores free speaking (5 to 180
s), transcribes it, then has the AI correct what was heard (`speaking_correction`): the errors
(also in `errors list`, source `speaking`), the notes, the natural version and the comment on the
structure. Without `--duration`, Groq measures the clip first, as for `shadow`. `correct <id>`
corrects a stored spoken production again (after a failure, or `--no-correct`).

`assess <id>` scores a stored shadowing with Azure (word by word, phoneme by phoneme; the recording
is sent to Microsoft); `shadow ... --assess` does it right after recording. Both need the
`pronunciation_assessment` setting to be `azure` (and an Azure key and region in `.env`).

Exit codes, in the spirit of D-053: 0 done (silence included), 1 the transcription or the
correction is unavailable (the recording is kept: the message gives the command to run later), 2
usage error (no database, unreadable or refused clip, invalid sentence or topic, unknown
production, already transcribed or corrected, not transcribed yet).
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas import TranscriptionOutput
from app.ai.types import AiResult
from app.cli_errors import _console_safe
from app.cli_library import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    GatewayFactory,
    _build_gateway,
    _open,
)
from app.cli_write import render_correction
from app.db.settings_store import get_setting
from app.domain import pronunciation as pa
from app.domain.enums import ProductionKind
from app.domain.speech_compare import Comparison, Op, compare
from app.domain.speech_rules import MAX_HEARD_CHARS, RecordingKind
from app.services import productions, pronunciation, speaking, speech
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
WHAT_WAS_HEARD = (
    "This correction is about what speech recognition heard: it may have smoothed over a mistake "
    "or misheard a word. Listen to your recording if an error looks wrong: any error can be edited "
    "or deleted in the error log."
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
    print(f"Production #{result.production_id} ({seconds}).", flush=True)
    if file is not None:
        print(f"Recording: {file}", flush=True)
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


ESTIMATE = "These scores are an automatic estimate, not a teacher's judgment."


def render_assessment(scores: dict[str, object]) -> str:
    """The stored `azure-pa-1` document as text: global scores, each word, the weakest phonemes."""
    overall: dict[str, object] = scores.get("overall") or {}  # type: ignore[assignment]

    def shown(value: object) -> str:
        return f"{value:g}" if isinstance(value, int | float) else "-"

    words = [w for w in scores.get("words") or [] if isinstance(w, dict)]
    lines = []
    if scores.get("status") == "silence":
        lines.append("Pronunciation: nothing was heard (silence), no score.")
    else:
        lines.append(
            "Pronunciation (0-100): "
            f"overall {shown(overall.get('pronunciation'))}, "
            f"accuracy {shown(overall.get('accuracy'))}, "
            f"fluency {shown(overall.get('fluency'))}, "
            f"completeness {shown(overall.get('completeness'))}"
        )
        for word in words:
            error = word.get("error_type")
            flag = f"  [{error}]" if error not in (None, "None") else ""
            lines.append(f"  {word.get('word')}: {shown(word.get('accuracy'))}{flag}")
        weakest = pa.weakest_phonemes(words, 5)
        if weakest:
            listed = ", ".join(
                f"{p['phoneme']} ({p['word']}, {shown(p['accuracy'])})" for p in weakest
            )
            lines.append(f"Weakest sounds: {listed}")
        counts = pa.summarize(words)
        lines.append(
            f"Mispronounced {counts['mispronounced']}, omitted {counts['omitted']}, "
            f"inserted {counts['inserted']}."
        )
    lines.append(f"Scored by {scores.get('provider')} ({scores.get('model')}).")
    lines.append(ESTIMATE)
    return "\n".join(lines)


def _assessment_enabled(factory: speech.SessionFactory) -> bool:
    with factory() as session:
        enabled = get_setting(session, "pronunciation_assessment") != "off"
        session.rollback()
    return enabled


DISABLED = (
    "Pronunciation assessment is off. Turn the `pronunciation_assessment` setting to `azure` "
    "(after saving an Azure key and region, see the README) to use it."
)


def _assess_and_report(
    factory: speech.SessionFactory, gateway: Gateway, store: AudioStore, production_id: int
) -> int:
    print("Sending the recording to Azure for a pronunciation assessment...", flush=True)
    try:
        outcome = pronunciation.assess(factory, gateway, store, production_id)
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    if outcome.scores is None:
        reason = f" ({outcome.reason})" if outcome.reason else ""
        print(
            f"Pronunciation assessment unavailable{reason}. Nothing was stored: run "
            f"`python -m app speech assess {production_id}` later.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    print(render_assessment(outcome.scores))
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


def _read_clip(file: Path) -> tuple[bytes, str] | None:
    """The bytes and the media type of a clip, or None (the message is printed)."""
    content_type = FILE_TYPES.get(file.suffix.lower())
    if content_type is None:
        print(
            f"{file.name}: not an accepted recording. Use one of {', '.join(FILE_TYPES)}.",
            file=sys.stderr,
        )
        return None
    try:
        return file.read_bytes(), content_type
    except OSError as exc:
        print(f"Cannot read {file}: {exc}", file=sys.stderr)
        return None


def _measure_first(
    gateway: Gateway, data: bytes, extension: str
) -> AiResult[TranscriptionOutput] | None:
    """Transcribe before storing, to take Groq's duration (D-176); None when it cannot."""
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
        return None
    return first


def run_speech_shadow(
    url: str,
    settings: "Settings",
    file: Path,
    *,
    target: str,
    item_id: int | None = None,
    duration: float | None = None,
    assess: bool = False,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    clip = _read_clip(file)
    if clip is None:
        return EXIT_USAGE
    data, content_type = clip
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
        if assess and not _assessment_enabled(factory):  # before anything is stored
            print(DISABLED, file=sys.stderr)
            return EXIT_USAGE
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        first = None
        if duration is None:
            first = _measure_first(gateway, data, extension)
            if first is None:
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
        code = _report(result, target, store.root / audio_path if audio_path else None)
        if assess and result.transcription.status != "unavailable":
            print("")
            return max(code, _assess_and_report(factory, gateway, store, result.production_id))
        if assess:
            print(
                "Not assessed: the transcription failed. Run "
                f"`python -m app speech assess {result.production_id}` later.",
                file=sys.stderr,
            )
        return code
    finally:
        engine.dispose()


def run_speech_assess(
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
        return _assess_and_report(factory, gateway, store, production_id)
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


# --- Free speaking (M6.a2a) ----------------------------------------------------------------------


def _structure_lines(output: dict[str, object]) -> list[str]:
    structure = output.get("structure")
    if not isinstance(structure, dict):
        return []
    lines = ["", "Structure:", f"  {structure.get('comment_en', '')}"]
    connectors = structure.get("connectors_used") or []
    if connectors:
        lines.append(f"  Connectors you used: {', '.join(str(c) for c in connectors)}")
    for suggestion in structure.get("suggestions") or []:
        lines.append(f"  - {suggestion.get('text_en', '')}")
    return lines


def _report_correction(
    factory: speech.SessionFactory,
    gateway: Gateway,
    production_id: int,
) -> int:
    print("Asking the AI to correct what was heard...", flush=True)
    try:
        result = speaking.correct_speaking(factory, gateway, production_id)
    except LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return EXIT_USAGE
    if result.status != "ok":
        reason = f" ({result.reason.value})" if result.reason else ""
        print(
            f"The AI could not correct this recording: {result.status}{reason}. Production "
            f"#{production_id} is kept; run `python -m app speech correct {production_id}` later.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    with factory() as session:
        attempt = productions.get_production(session, production_id)
        output = (attempt.ai_feedback or {}).get("output") or {}
        print(render_correction(session, production_id, result))
        print("\n".join(_structure_lines(output)))
        session.rollback()
    print("")
    print(WHAT_WAS_HEARD)
    return EXIT_OK


def run_speech_speak(
    url: str,
    settings: "Settings",
    file: Path,
    *,
    prompt: str | None = None,
    duration: float | None = None,
    correct: bool = True,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    _console_safe()
    clip = _read_clip(file)
    if clip is None:
        return EXIT_USAGE
    data, content_type = clip
    try:  # refuse before any AI call
        extension = speech.check_audio(data, content_type)
        prompt = speaking.check_prompt(prompt)
        if duration is not None:
            speech.check_duration(RecordingKind.SPEAKING, duration)
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
            result = speaking.record_speaking(
                factory,
                gateway,
                store,
                data=data,
                content_type=content_type,
                duration_s=duration,
                prompt_text=prompt,
                transcription=first,
            )
        except LibraryError as exc:
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        with factory() as session:
            audio_path = productions.get_production(session, result.production_id).audio_path
        seconds = f"{result.audio_seconds:g} s" if result.audio_seconds is not None else "length ?"
        print(f"Production #{result.production_id} ({seconds}).", flush=True)
        if audio_path:
            print(f"Recording: {store.root / audio_path}", flush=True)
        outcome = result.transcription
        if outcome.status == "unavailable":
            print(
                f"Transcription unavailable ({outcome.reason}). The recording is kept: run "
                f"`python -m app speech transcribe {result.production_id}`, then "
                f"`python -m app speech correct {result.production_id}` later.",
                file=sys.stderr,
            )
            return EXIT_FAILED
        if outcome.status == "silence":
            print("Nothing was heard (silence): nothing to correct.")
            return EXIT_OK
        print(f"Heard: {outcome.text}", flush=True)
        if not correct:
            print(f"Not corrected yet: run `python -m app speech correct {result.production_id}`.")
            return EXIT_OK
        return _report_correction(factory, gateway, result.production_id)
    finally:
        engine.dispose()


def run_speech_correct(
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
    try:
        try:
            with factory() as session:
                text = speaking.prepare_speaking(session, production_id).correction.text
                session.rollback()
        except LibraryError as exc:  # refused before building a gateway
            print(exc.message, file=sys.stderr)
            return EXIT_USAGE
        print(f"Heard: {text}", flush=True)
        gateway = (gateway_factory or (lambda e: _build_gateway(e, settings)))(engine)
        return _report_correction(factory, gateway, production_id)
    finally:
        engine.dispose()
