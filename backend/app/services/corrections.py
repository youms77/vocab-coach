"""AI correction of a written production (module E, M5.a1).

Order of operations (D-038): a short read session, closed before the call; the AI call with no
session open; then **one short write transaction**:

1. read the production, its target terms and the active taxonomy, split the text into numbered
   sentences, then close the session;
2. call the gateway (`production_correction`);
3. `ok`: in one transaction check the production is still there and not yet corrected
   (`AlreadyCorrected`, 409), then write the feedback, the target checks, one error event per
   error, the categories the AI proposed, and `production.corrected`;
4. `incomplete` or `unavailable`: nothing is written, the production stays uncorrected and can be
   corrected again. This is the degraded mode, and a result, not an HTTP error (D-081).

`ai_feedback` (`format: "correction-1"`) keeps the validated output as is, the position of each
`wrong` in the original text (`spans`, in Unicode code points), the id of the error event of each
error (`error_event_ids`, same order as `output.errors`) and the check of each target.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.production_correction import (
    CorrectionError,
    ProductionCorrectionOutput,
    TargetCheck,
    correction_context,
)
from app.ai.schemas.transcript_analysis import TranscriptError
from app.ai.tasks import correction_output_budget
from app.ai.types import AiStatus, UnavailableReason
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import ErrorCategory, EventLog, ProductionAttempt
from app.domain import exercises as ex
from app.domain.enums import ErrorSource, Modality, ProductionKind
from app.domain.events import EventType, ProductionCorrected, ProductionOrigin
from app.domain.sentences import Sentence, TextTooLong, find_fragment, split_sentences
from app.domain.study_day import as_utc
from app.domain.usage_sheet import read_sheet
from app.services import error_log, productions
from app.services.enrichment import current_sheet
from app.services.library import LibraryError
from app.services.productions import ProductionNotFound, TextTooLongError

TASK = "production_correction"
FEEDBACK_FORMAT = "correction-1"
PROMPT_MAX_CHARS = productions.MAX_PROMPT_CHARS
DESCRIPTION_MAX_CHARS = 200  # one line of the taxonomy in the prompt

SessionFactory = Callable[[], Session]
Mode = Literal["paragraph", "sentence"]


class AlreadyCorrected(LibraryError):
    code = "already_corrected"


class NotCorrectable(LibraryError):
    status, code = 422, "not_correctable"


# --- Reading (step 1) ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    ref: int  # position among the production's targets, sent to the AI
    item_id: int
    term: str
    item_type: str
    definition_simple: str


@dataclass(frozen=True)
class Prepared:
    attempt_id: int
    text: str
    prompt: str
    source: ErrorSource
    sentences: list[Sentence]
    targets: list[Target]
    taxonomy: dict[str, str]  # active code -> one-line description


def _one_line(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def source_of(session: Session, attempt_id: int) -> ErrorSource:
    """Where the errors of a production come from, which follows its context: `review` for a
    sentence production checked in a review (`production.recorded` has `origin: review`), else
    `writing` (free writing, and the personal sentence of a discovery: `ErrorSource` has no
    separate value for it)."""
    payload = session.scalar(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.PRODUCTION_RECORDED.value,
            EventLog.entity_type == "production_attempt",
            EventLog.entity_id == attempt_id,
        )
    )
    if payload is not None and payload.get("origin") == ProductionOrigin.REVIEW.value:
        return ErrorSource.REVIEW
    return ErrorSource.WRITING


def prepare(session: Session, attempt_id: int) -> Prepared:
    """Everything the call needs. Raises ProductionNotFound, AlreadyCorrected, NotCorrectable,
    TextTooLongError."""
    attempt = productions.get_production(session, attempt_id)
    if attempt.kind is not ProductionKind.WRITING or attempt.modality != Modality.WRITTEN:
        raise NotCorrectable("Only a written production can be corrected here.")
    if attempt.ai_feedback is not None:
        raise AlreadyCorrected("This production was already corrected.")
    try:
        sentences = split_sentences(attempt.text)
    except TextTooLong as exc:
        raise TextTooLongError(str(exc)) from exc
    if not sentences:
        raise NotCorrectable("There is nothing to correct: the text is empty.")
    targets: list[Target] = []
    for ref, (_, item) in enumerate(productions.targets_of(session, attempt.id)):
        sheet = current_sheet(session, item.id)
        definition = read_sheet(dict(sheet.content)).definition_simple if sheet else None
        targets.append(
            Target(ref, item.id, item.term, str(item.item_type), _one_line(definition or "", 200))
        )
    taxonomy = {
        category.code: _one_line(
            category.description_en or category.label_en, DESCRIPTION_MAX_CHARS
        )
        for category in error_log.active_categories(session)
    }
    return Prepared(
        attempt_id=attempt.id,
        text=attempt.text,
        prompt=_one_line(attempt.prompt_text or "", PROMPT_MAX_CHARS),
        source=source_of(session, attempt.id),
        sentences=sentences,
        targets=targets,
        taxonomy=taxonomy,
    )


def _json_lines(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def _inputs(prepared: Prepared, mode: Mode) -> dict[str, str]:
    return {
        "mode": mode,
        "sentences": _json_lines([{"index": s.index, "text": s.text} for s in prepared.sentences]),
        "prompt": prepared.prompt or "(none)",
        "targets": _json_lines(
            [
                {
                    "ref": t.ref,
                    "term": t.term,
                    "item_type": t.item_type,
                    "definition_simple": t.definition_simple,
                }
                for t in prepared.targets
            ]
        )
        or "(none)",
        "taxonomy": "\n".join(f"{code}: {text}" for code, text in prepared.taxonomy.items()),
    }


# --- Writing (step 3) ----------------------------------------------------------------------------


def spans_of(
    sentences: list[Sentence], errors: list[CorrectionError]
) -> list[dict[str, int | None]]:
    """Where each `wrong` is in the original text: `start` and `end` in Unicode code points (the
    sentence offset plus the position found inside the sentence), None if it cannot be found
    (the validator makes that impossible for a validated output). One entry per error, in order."""
    by_index = {s.index: s for s in sentences}
    spans: list[dict[str, int | None]] = []
    for i, error in enumerate(errors):
        sentence = by_index.get(error.sentence_index)
        found = find_fragment(sentence.text, error.wrong) if sentence is not None else None
        spans.append(
            {
                "error": i,
                "sentence_index": error.sentence_index,
                "start": sentence.start + found[0] if sentence and found else None,
                "end": sentence.start + found[1] if sentence and found else None,
            }
        )
    return spans


def _check_targets(
    attempt: ProductionAttempt, session: Session, checks: list[TargetCheck], text: str
) -> list[dict[str, Any]]:
    """Fill `production_target.used` (deterministic) and `used_correctly` (from the AI) and
    describe the checks, noting where the AI disagrees with the deterministic result."""
    by_ref = {check.ref: check for check in checks}
    report: list[dict[str, Any]] = []
    for ref, (target, item) in enumerate(productions.targets_of(session, attempt.id)):
        used = ex.contains_term(item.term, text)
        check = by_ref.get(ref)
        if not used:
            correct: bool | None = False
        else:
            correct = check.used_correctly if check is not None else None
        target.used = used
        target.used_correctly = correct
        report.append(
            {
                "ref": ref,
                "lexical_item_id": item.id,
                "used": used,
                "used_correctly": correct,
                "ai_used": check.used if check is not None else None,
                "comment": check.comment if check is not None else None,
                "disagreement": check is not None and check.used != used,
            }
        )
    return report


@dataclass
class Written:
    error_ids: list[int] = field(default_factory=list)
    proposed_ids: list[int] = field(default_factory=list)


def category_for(
    session: Session,
    error: "CorrectionError | TranscriptError",
    attempt_id: int,
    at: datetime,
    written: "Written",
) -> ErrorCategory:
    """The category of an AI error: the listed code, or the subcategory it proposes (created
    `proposed`, or reused)."""
    proposal = error.proposed_subcategory
    if proposal is None:
        return error_log.active_category(session, error.category_code)
    outcome = error_log.propose_category(
        session,
        error_log.Proposal(
            parent_code=proposal.parent_code,
            slug=proposal.slug,
            label_en=proposal.label_en,
            label_fr=proposal.label_fr,
            description_en=proposal.description_en,
        ),
        at=at,
        production_attempt_id=attempt_id,
    )
    if outcome.proposed:
        written.proposed_ids.append(outcome.category.id)
    return outcome.category


def _write(
    session_factory: SessionFactory,
    prepared: Prepared,
    output: ProductionCorrectionOutput,
    *,
    source: ErrorSource,
    provenance: tuple[str | None, str | None, str | None],
    ai_call_id: int | None,
    at: datetime,
) -> Written:
    """The one write transaction. Raises ProductionNotFound, AlreadyCorrected."""
    provider, model, prompt_version = provenance
    written = Written()
    with session_factory() as session:
        attempt = session.get(ProductionAttempt, prepared.attempt_id)
        if attempt is None:
            raise ProductionNotFound(f"There is no production {prepared.attempt_id}.")
        if attempt.ai_feedback is not None:
            raise AlreadyCorrected("This production was already corrected.")
        sentence_text = {s.index: s.text for s in prepared.sentences}
        ref_item = {t.ref: t.item_id for t in prepared.targets}
        for error in output.errors:
            category = category_for(session, error, attempt.id, at, written)
            event = error_log.record_error(
                session,
                source=source,
                category=category,
                erroneous_text=error.wrong,
                correction=error.correction,
                at=at,
                original_text=sentence_text[error.sentence_index],
                alternatives=error.alternatives,
                explanation=error.explanation_en,
                lexical_item_id=ref_item.get(error.target_ref)
                if error.target_ref is not None
                else None,
                production_attempt_id=attempt.id,
                study_session_id=attempt.study_session_id,
            )
            written.error_ids.append(event.id)
        target_report = _check_targets(attempt, session, output.targets, prepared.text)
        attempt.ai_feedback = {
            "format": FEEDBACK_FORMAT,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
            "output": output.model_dump(mode="json"),
            "spans": spans_of(prepared.sentences, output.errors),
            "error_event_ids": list(written.error_ids),
            "targets": target_report,
        }
        attempt.ai_call_id = ai_call_id
        attempt.updated_at = at
        record_event(
            session,
            ProductionCorrected(
                production_attempt_id=attempt.id,
                word_count=attempt.word_count,
                sentence_count=len(prepared.sentences),
                error_count=len(output.errors),
                naturalness_note_count=len(output.naturalness_notes),
                targets=len(target_report),
                targets_used_correctly=sum(1 for t in target_report if t["used_correctly"]),
                provider=provider or "unknown",
                model=model or "unknown",
                prompt_version=prompt_version or f"{TASK}.v1",
                ai_call_id=ai_call_id,
            ),
            occurred_at=at,
            study_session_id=attempt.study_session_id,
        )
        session.commit()
    return written


# --- Entry point ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrectionResult:
    status: Literal["ok", "incomplete", "unavailable"]
    reason: UnavailableReason | None
    attempt_id: int
    error_ids: list[int] = field(default_factory=list)
    proposed_category_ids: list[int] = field(default_factory=list)
    detail: str | None = None


def correct_production(
    session_factory: SessionFactory,
    gateway: Gateway,
    attempt_id: int,
    *,
    source: ErrorSource | None = None,
    mode: Mode | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> CorrectionResult:
    """Correct a production (see the module docstring). Raises ProductionNotFound,
    AlreadyCorrected, NotCorrectable, TextTooLongError. An AI failure is a result."""
    with session_factory() as session:
        prepared = prepare(session, attempt_id)
        session.rollback()  # nothing stays open during the AI call
    mode = mode or ("sentence" if len(prepared.sentences) == 1 else "paragraph")
    result = gateway.generate_json(
        TASK,
        _inputs(prepared, mode),
        ProductionCorrectionOutput,
        validation_context=correction_context(
            {s.index: s.text for s in prepared.sentences},
            set(prepared.taxonomy),
            {t.ref for t in prepared.targets},
        ),
        max_output_tokens=correction_output_budget(len(prepared.sentences)),
    )
    if result.status is not AiStatus.OK or result.data is None:
        status: Literal["incomplete", "unavailable"] = (
            "incomplete" if result.status is AiStatus.INCOMPLETE else "unavailable"
        )
        return CorrectionResult(status, result.reason, attempt_id, detail=result.detail)
    written = _write(
        session_factory,
        prepared,
        result.data,
        source=source or prepared.source,
        provenance=(result.provider, result.model, result.prompt_version),
        ai_call_id=result.call_id,
        at=as_utc(clock()),
    )
    return CorrectionResult(
        "ok",
        None,
        attempt_id,
        error_ids=written.error_ids,
        proposed_category_ids=written.proposed_ids,
    )
