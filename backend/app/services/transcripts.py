"""Pasted conversation transcripts: recording and AI analysis (module E, M5.a2).

Recording (`record_transcript`): the server parses the pasted text again
(`app/domain/transcript_import.py`) and stores **only the user's turns** (joined by a blank line)
as a `transcript_analysis` production, modality `oral`. The raw paste and the other speaker's
turns are never stored. `production.recorded` (version 3) has `origin: transcript`, the turn and
word counts and the day of the conversation, never any text.

Analysis (`analyse_transcript`), D-038 and D-134:

1. a short read session: the stored text is cut into units (one per user turn, a long turn cut on
   sentence ends) and the units into chunks; the session is closed;
2. one AI call per chunk, in order, with no session open. The other speaker's turn before a unit
   that opens a turn is sent as a separate `data` placeholder marked as context, cut to 300
   characters, and only when the client sends the transcript again (`TranscriptSource`): it is not
   stored, so a retry without it checks the units without context;
3. every call must succeed before anything is written: one failed chunk (`incomplete` or
   `unavailable`) and nothing is written, the production can be analysed again;
4. one write transaction that checks the production is still there and not analysed, then writes
   the errors (source `transcript`, `occurred_at` = the start of the conversation's study day when
   the user gave it), the merged feedback (`format: "transcript-1"`, with the `correction-1` keys so
   the screens reuse the highlighted view) and `production.corrected`.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.transcript_analysis import (
    TranscriptAnalysisOutput,
    TranscriptError,
    TranscriptNote,
    transcript_context,
)
from app.ai.tasks import transcript_output_budget
from app.ai.types import AiStatus
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import EventLog, ProductionAttempt, StudySession
from app.db.settings_store import get_setting
from app.domain.enums import ErrorSource, Modality, ProductionKind
from app.domain.events import (
    EventType,
    ProductionCorrected,
    ProductionOrigin,
    ProductionRecorded,
)
from app.domain.sentences import find_fragment
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.domain.transcript_import import (
    ProblemCode,
    Severity,
    TranscriptParse,
    Unit,
    UserDesignation,
    chunk_units,
    parse_transcript,
    split_units,
)
from app.services import error_log, productions
from app.services.corrections import (
    DESCRIPTION_MAX_CHARS,
    AlreadyCorrected,
    CorrectionResult,
    Written,
    _one_line,
    category_for,
)
from app.services.library import LibraryError
from app.services.productions import ProductionNotFound, TextTooLongError
from app.services.study_sessions import SessionNotFound

TASK = "transcript_analysis"
FEEDBACK_FORMAT = "transcript-1"
MAX_TITLE_CHARS = 200
# Spelling is the speech recognition's, and pronunciation cannot be judged from a transcript.
EXCLUDED_CODE_PREFIXES = ("spelling", "pronunciation")

SessionFactory = Callable[[], Session]


class InvalidTranscript(LibraryError):
    """No usable user turn: `codes` are the parser's error codes."""

    status, code = 422, "invalid_transcript"


class TranscriptMismatch(LibraryError):
    """The transcript sent with `/correct` does not give the stored user turns."""

    status, code = 409, "transcript_mismatch"


class NotATranscript(LibraryError):
    status, code = 422, "invalid_production"


# --- Recording -----------------------------------------------------------------------------------


def _refusal(parsed: TranscriptParse) -> None:
    errors = [p for p in parsed.problems if p.severity is Severity.ERROR]
    if not errors:
        return
    if any(p.code is ProblemCode.TOO_LARGE for p in errors):
        message = next(p.message for p in errors if p.code is ProblemCode.TOO_LARGE)
        raise TextTooLongError(message, codes=[str(p.code) for p in errors])
    raise InvalidTranscript(errors[0].message, codes=[str(p.code) for p in errors])


def _day_start(session: Session, day: date) -> datetime:
    tz = ZoneInfo(get_setting(session, "timezone"))
    return study_day_bounds(day, tz, get_setting(session, "day_start_hour"))[0]


def study_today(session: Session, now: datetime) -> date:
    tz = ZoneInfo(get_setting(session, "timezone"))
    return study_day_of(now, tz, get_setting(session, "day_start_hour"))


def record_transcript(
    session: Session,
    *,
    text: str,
    user: UserDesignation,
    title: str | None,
    occurred_on: date | None,
    study_session_id: int | None,
    at: datetime,
) -> ProductionAttempt:
    """Store the user's turns of a pasted transcript (not analysed yet). Raises
    InvalidTranscript, TextTooLongError, InvalidTranscript (`future_date`), SessionNotFound. In
    the caller's transaction."""
    at = as_utc(at)
    parsed = parse_transcript(text, user)
    _refusal(parsed)
    title = (title or "").strip() or None
    if title is not None and len(title) > MAX_TITLE_CHARS:
        raise InvalidTranscript(
            f"The title has more than {MAX_TITLE_CHARS} characters.", codes=["title_too_long"]
        )
    if occurred_on is not None and occurred_on > study_today(session, at):
        raise InvalidTranscript(
            "The date of the conversation is in the future.", codes=["future_date"]
        )
    if study_session_id is not None and session.get(StudySession, study_session_id) is None:
        raise SessionNotFound(f"There is no study session {study_session_id}.")
    attempt = ProductionAttempt(
        kind=ProductionKind.TRANSCRIPT_ANALYSIS,
        modality=Modality.ORAL,
        prompt_text=title,
        text=parsed.user_text,
        word_count=parsed.user_words,
        ai_feedback=None,
        study_session_id=study_session_id,
        created_at=at,
        updated_at=at,
    )
    session.add(attempt)
    session.flush()
    record_event(
        session,
        ProductionRecorded(
            production_attempt_id=attempt.id,
            kind=ProductionKind.TRANSCRIPT_ANALYSIS,
            modality=Modality.ORAL,
            word_count=attempt.word_count,
            origin=ProductionOrigin.TRANSCRIPT,
            turns_total=len(parsed.turns),
            turns_user=len(parsed.user_turns),
            words_user=parsed.user_words,
            occurred_on=occurred_on,
        ),
        occurred_at=_day_start(session, occurred_on) if occurred_on is not None else at,
        study_session_id=study_session_id,
    )
    session.flush()
    return attempt


def occurred_on_of(session: Session, attempt_id: int) -> date | None:
    """The day of the conversation, as recorded in `production.recorded`."""
    payload = session.scalar(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.PRODUCTION_RECORDED.value,
            EventLog.entity_type == "production_attempt",
            EventLog.entity_id == attempt_id,
        )
    )
    value = payload.get("occurred_on") if payload else None
    return date.fromisoformat(value) if value else None


# --- Analysis: reading (step 1) ------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptSource:
    """The pasted transcript sent again with `/correct`, only to give the AI the other speaker's
    turns as context (they are never stored)."""

    text: str
    user: UserDesignation


@dataclass(frozen=True)
class Prepared:
    attempt_id: int
    units: list[Unit]
    contexts: dict[int, str]  # unit index -> the other speaker's turn before it
    taxonomy: dict[str, str]
    errors_at: datetime | None  # start of the conversation's study day, if the user gave it


def allowed_taxonomy(session: Session) -> dict[str, str]:
    """Active codes with a one-line description, without spelling and pronunciation."""
    return {
        category.code: _one_line(
            category.description_en or category.label_en, DESCRIPTION_MAX_CHARS
        )
        for category in error_log.active_categories(session)
        if not any(
            category.code == prefix or category.code.startswith(prefix + ".")
            for prefix in EXCLUDED_CODE_PREFIXES
        )
    }


def prepare(session: Session, attempt_id: int, source: TranscriptSource | None) -> Prepared:
    """Raises ProductionNotFound, NotATranscript, AlreadyCorrected, TranscriptMismatch."""
    attempt = productions.get_production(session, attempt_id)
    if attempt.kind is not ProductionKind.TRANSCRIPT_ANALYSIS:
        raise NotATranscript("Only a transcript takes a transcript body.")
    if attempt.ai_feedback is not None:
        raise AlreadyCorrected("This transcript was already analysed.")
    units = split_units(attempt.text)
    contexts: dict[int, str] = {}
    if source is not None:
        parsed = parse_transcript(source.text, source.user)
        if parsed.has_errors or parsed.user_text != attempt.text:
            raise TranscriptMismatch(
                "This transcript does not give the turns stored for this production."
            )
        by_turn = parsed.user_contexts()
        for unit in units:
            context = by_turn[unit.turn] if unit.opens_turn else None
            if context:
                contexts[unit.index] = context
    occurred_on = occurred_on_of(session, attempt.id)
    return Prepared(
        attempt_id=attempt.id,
        units=units,
        contexts=contexts,
        taxonomy=allowed_taxonomy(session),
        errors_at=_day_start(session, occurred_on) if occurred_on is not None else None,
    )


def _json_lines(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def chunk_inputs(prepared: Prepared, chunk: list[Unit]) -> dict[str, str]:
    contexts = [
        {"before_unit": unit.index, "text": prepared.contexts[unit.index]}
        for unit in chunk
        if unit.index in prepared.contexts
    ]
    return {
        "units": _json_lines([{"index": unit.index, "text": unit.text} for unit in chunk]),
        "contexts": _json_lines(contexts) or "(none)",
        "taxonomy": "\n".join(f"{code}: {text}" for code, text in prepared.taxonomy.items()),
    }


# --- Analysis: merging and writing (steps 3 and 4) -----------------------------------------------


@dataclass(frozen=True)
class ChunkResult:
    output: TranscriptAnalysisOutput
    provider: str | None
    model: str | None
    prompt_version: str | None
    call_id: int | None
    units: list[Unit]


def spans_of(units: list[Unit], errors: list[TranscriptError]) -> list[dict[str, int | None]]:
    """Where each `wrong` is in the stored text (Unicode code points)."""
    by_index = {unit.index: unit for unit in units}
    spans: list[dict[str, int | None]] = []
    for i, error in enumerate(errors):
        unit = by_index.get(error.unit_index)
        found = find_fragment(unit.text, error.wrong) if unit is not None else None
        spans.append(
            {
                "error": i,
                "sentence_index": error.unit_index,
                "start": unit.start + found[0] if unit and found else None,
                "end": unit.start + found[1] if unit and found else None,
            }
        )
    return spans


def _corrected_text(units: list[Unit], corrected: dict[int, str]) -> str:
    turns: list[list[str]] = []
    for unit in units:
        if unit.opens_turn:
            turns.append([])
        turns[-1].append(corrected.get(unit.index, unit.text))
    return "\n\n".join(" ".join(parts) for parts in turns)


def _note_out(note: TranscriptNote) -> dict[str, Any]:
    data = note.model_dump(mode="json")
    data["sentence_index"] = data.pop("unit_index")
    return data


def merged_output(units: list[Unit], results: list[ChunkResult]) -> dict[str, Any]:
    """The chunks' outputs as one, with the `correction-1` keys (units as `sentences`)."""
    corrected = {u.index: u.corrected for r in results for u in r.output.units}
    errors = []
    for result in results:
        for error in result.output.errors:
            data = error.model_dump(mode="json")
            data["sentence_index"] = data.pop("unit_index")
            data["target_ref"] = None
            errors.append(data)
    return {
        "sentences": [u.model_dump(mode="json") for r in results for u in r.output.units],
        "corrected_text": _corrected_text(units, corrected),
        "natural_text": None,
        "errors": errors,
        "naturalness_notes": [
            _note_out(note) for r in results for note in r.output.naturalness_notes
        ],
        "targets": [],
        "overall_comment": " ".join(
            r.output.overall_comment.strip() for r in results if r.output.overall_comment.strip()
        ),
    }


def _write(
    session_factory: SessionFactory,
    prepared: Prepared,
    results: list[ChunkResult],
    *,
    at: datetime,
) -> Written:
    """The one write transaction. Raises ProductionNotFound, AlreadyCorrected."""
    written = Written()
    errors = [error for result in results for error in result.output.errors]
    unit_text = {unit.index: unit.text for unit in prepared.units}
    errors_at = prepared.errors_at or at
    first = results[0]
    with session_factory() as session:
        attempt = session.get(ProductionAttempt, prepared.attempt_id)
        if attempt is None:
            raise ProductionNotFound(f"There is no production {prepared.attempt_id}.")
        if attempt.ai_feedback is not None:
            raise AlreadyCorrected("This transcript was already analysed.")
        for error in errors:
            category = category_for(session, error, attempt.id, at, written)
            event = error_log.record_error(
                session,
                source=ErrorSource.TRANSCRIPT,
                category=category,
                erroneous_text=error.wrong,
                correction=error.correction,
                at=errors_at,
                original_text=unit_text[error.unit_index],
                alternatives=error.alternatives,
                explanation=error.explanation_en,
                production_attempt_id=attempt.id,
                study_session_id=attempt.study_session_id,
            )
            written.error_ids.append(event.id)
        attempt.ai_feedback = {
            "format": FEEDBACK_FORMAT,
            "prompt_version": first.prompt_version,
            "provider": first.provider,
            "model": first.model,
            "output": merged_output(prepared.units, results),
            "units": [
                {
                    "index": u.index,
                    "turn": u.turn,
                    "start": u.start,
                    "end": u.end,
                    "opens_turn": u.opens_turn,
                }
                for u in prepared.units
            ],
            "spans": spans_of(prepared.units, errors),
            "error_event_ids": list(written.error_ids),
            "targets": [],
            "context_sent": bool(prepared.contexts),
            "calls": [
                {
                    "ai_call_id": r.call_id,
                    "provider": r.provider,
                    "model": r.model,
                    "units": [r.units[0].index, r.units[-1].index],
                }
                for r in results
            ],
        }
        attempt.ai_call_id = results[-1].call_id
        attempt.updated_at = at
        record_event(
            session,
            ProductionCorrected(
                production_attempt_id=attempt.id,
                word_count=attempt.word_count,
                sentence_count=len(prepared.units),
                error_count=len(errors),
                naturalness_note_count=sum(len(r.output.naturalness_notes) for r in results),
                targets=0,
                targets_used_correctly=0,
                provider=first.provider or "unknown",
                model=first.model or "unknown",
                prompt_version=first.prompt_version or f"{TASK}.v1",
                ai_call_id=results[-1].call_id,
            ),
            occurred_at=at,
            study_session_id=attempt.study_session_id,
        )
        session.commit()
    return written


# --- Entry point ---------------------------------------------------------------------------------


def analyse_transcript(
    session_factory: SessionFactory,
    gateway: Gateway,
    attempt_id: int,
    *,
    source: TranscriptSource | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> CorrectionResult:
    """Analyse a recorded transcript (see the module docstring). Raises ProductionNotFound,
    NotATranscript, AlreadyCorrected, TranscriptMismatch. An AI failure is a result."""
    with session_factory() as session:
        prepared = prepare(session, attempt_id, source)
        session.rollback()  # nothing stays open during the AI calls
    results: list[ChunkResult] = []
    for chunk in chunk_units(prepared.units):
        result = gateway.generate_json(
            TASK,
            chunk_inputs(prepared, chunk),
            TranscriptAnalysisOutput,
            validation_context=transcript_context(
                {unit.index: unit.text for unit in chunk}, set(prepared.taxonomy)
            ),
            max_output_tokens=transcript_output_budget(len(chunk)),
        )
        if result.status is not AiStatus.OK or result.data is None:
            status: Literal["incomplete", "unavailable"] = (
                "incomplete" if result.status is AiStatus.INCOMPLETE else "unavailable"
            )
            return CorrectionResult(status, result.reason, attempt_id, detail=result.detail)
        results.append(
            ChunkResult(
                output=result.data,
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
                call_id=result.call_id,
                units=chunk,
            )
        )
    written = _write(session_factory, prepared, results, at=as_utc(clock()))
    return CorrectionResult(
        "ok",
        None,
        attempt_id,
        error_ids=written.error_ids,
        proposed_category_ids=written.proposed_ids,
    )
