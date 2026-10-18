"""Targeted drills: generation by the AI, reading, answering (module E, M5.a2).

Generation (`generate_drill`, D-038): a short read session checks the category and gathers the
inputs (the category and its active children, at most 5 recent errors of the user in that prefix,
drill errors left out), then closes; the AI is called with no session open; then one short write
transaction re-checks the category and creates a `production_attempt` (`kind = drill`,
`prompt_text` = the code, `word_count = 0`) whose `ai_feedback` holds the drill (`format:
"drill-1"`, the items with their solutions, server side only, and `answers: []`), and writes
`drill.generated`. A failed AI call writes nothing and is a result.

Answering (`answer_item`, no AI): exact grading (`app/domain/drills.py`), then in one transaction
the answer is appended to `answers` (by reassignment, D-020), `drill.item_answered` is written, a
`wrong` answer becomes an error (source `drill`), and the last answer writes `drill.completed`.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.targeted_drill import TargetedDrillOutput, drill_context
from app.ai.tasks import drill_output_budget
from app.ai.types import AiStatus, UnavailableReason
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import ErrorCategory, ErrorEvent, ProductionAttempt, StudySession
from app.domain import drills as rules
from app.domain.enums import ErrorCategoryStatus, ErrorSource, Modality, ProductionKind
from app.domain.events import DrillCompleted, DrillGenerated, DrillItemAnswered
from app.domain.study_day import as_utc
from app.services import error_log
from app.services.error_log import CategoryNotFound
from app.services.library import LibraryError
from app.services.review_flow import MAX_RESPONSE_TIME_MS
from app.services.study_sessions import SessionNotFound

TASK = "targeted_drill"
FEEDBACK_FORMAT = "drill-1"
RECENT_ERRORS = 5
CATEGORY_LINE_CHARS = 250
ERROR_FORM_CHARS = 300
MAX_PAGE_SIZE = 100

SessionFactory = Callable[[], Session]


class NotDrillable(LibraryError):
    status, code = 422, "not_drillable"


class DrillNotFound(LibraryError):
    status, code = 404, "drill_not_found"


class DrillItemNotFound(LibraryError):
    status, code = 404, "item_not_found"


class AlreadyAnswered(LibraryError):
    status, code = 409, "already_answered"


class ExerciseMismatch(LibraryError):
    status, code = 422, "exercise_mismatch"


class InvalidDrill(LibraryError):
    status, code = 422, "invalid_request"


# --- Categories ----------------------------------------------------------------------------------


def level(code: str) -> int:
    return code.count(".") + 1


def _under(code: str, prefix: str) -> bool:
    return code == prefix or code.startswith(prefix + ".")


def drillable_category(session: Session, code: str) -> ErrorCategory:
    """An active category of level 2 or more, not pronunciation. Raises CategoryNotFound,
    NotDrillable."""
    category = error_log.category_by_code(session, code)
    if category is None:
        raise CategoryNotFound(f"There is no error category {code!r}.")
    if level(code) < 2:
        raise NotDrillable("Choose a more precise category (level 2 or more).", reason="level")
    if _under(code, "pronunciation"):
        raise NotDrillable("Pronunciation cannot be drilled in writing.", reason="pronunciation")
    if category.status is not ErrorCategoryStatus.ACTIVE:
        raise NotDrillable(
            "This category is not active (proposed or rejected).", reason=str(category.status)
        )
    return category


def _family(session: Session, category: ErrorCategory) -> list[ErrorCategory]:
    """The category and its active descendants, in tree order."""
    return [c for c in error_log.active_categories(session) if _under(c.code, category.code)]


def _line(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _recent_errors(session: Session, code: str) -> list[dict[str, str]]:
    rows = session.execute(
        select(ErrorEvent.erroneous_text, ErrorEvent.correction)
        .join(ErrorCategory, ErrorCategory.id == ErrorEvent.category_id)
        .where(
            (ErrorCategory.code == code)
            | ErrorCategory.code.startswith(code + ".", autoescape=True),
            ErrorEvent.source != ErrorSource.DRILL,
        )
        .order_by(ErrorEvent.occurred_at.desc(), ErrorEvent.id.desc())
        .limit(RECENT_ERRORS)
    )
    return [
        {"wrong": _line(wrong, ERROR_FORM_CHARS), "correction": _line(right, ERROR_FORM_CHARS)}
        for wrong, right in rows
    ]


# --- Generation ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Prepared:
    code: str
    count: int
    codes: set[str]
    category_text: str
    errors: list[dict[str, str]]
    study_session_id: int | None


def prepare(session: Session, code: str, count: int, study_session_id: int | None) -> Prepared:
    """Raises CategoryNotFound, NotDrillable, InvalidDrill, SessionNotFound."""
    if not rules.MIN_ITEMS <= count <= rules.MAX_ITEMS:
        raise InvalidDrill(f"A drill has {rules.MIN_ITEMS} to {rules.MAX_ITEMS} items.")
    category = drillable_category(session, code)
    if study_session_id is not None and session.get(StudySession, study_session_id) is None:
        raise SessionNotFound(f"There is no study session {study_session_id}.")
    family = _family(session, category)
    lines = [
        _line(f"{c.code}: {c.label_en} - {c.description_en or c.label_en}", CATEGORY_LINE_CHARS)
        for c in family
    ]
    return Prepared(
        code=category.code,
        count=count,
        codes={c.code for c in family},
        category_text="\n".join(lines),
        errors=_recent_errors(session, category.code),
        study_session_id=study_session_id,
    )


def _inputs(prepared: Prepared) -> dict[str, str]:
    return {
        "category": prepared.category_text,
        "errors": "\n".join(json.dumps(e, ensure_ascii=False) for e in prepared.errors) or "(none)",
        "count": str(prepared.count),
    }


@dataclass(frozen=True)
class GenerationResult:
    status: Literal["ok", "incomplete", "unavailable"]
    reason: UnavailableReason | None
    drill_id: int | None
    detail: str | None = None


def generate_drill(
    session_factory: SessionFactory,
    gateway: Gateway,
    category_code: str,
    *,
    count: int = rules.DEFAULT_ITEMS,
    study_session_id: int | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> GenerationResult:
    """See the module docstring. Raises CategoryNotFound, NotDrillable, InvalidDrill,
    SessionNotFound. An AI failure is a result."""
    with session_factory() as session:
        prepared = prepare(session, category_code, count, study_session_id)
        session.rollback()  # nothing stays open during the AI call
    result = gateway.generate_json(
        TASK,
        _inputs(prepared),
        TargetedDrillOutput,
        validation_context=drill_context(prepared.count, prepared.codes),
        max_output_tokens=drill_output_budget(prepared.count),
    )
    if result.status is not AiStatus.OK or result.data is None:
        status: Literal["incomplete", "unavailable"] = (
            "incomplete" if result.status is AiStatus.INCOMPLETE else "unavailable"
        )
        return GenerationResult(status, result.reason, None, detail=result.detail)
    output = result.data
    at = as_utc(clock())
    with session_factory() as session:
        drillable_category(session, prepared.code)  # still active
        attempt = ProductionAttempt(
            kind=ProductionKind.DRILL,
            modality=Modality.WRITTEN,
            prompt_text=prepared.code,
            text="",
            word_count=0,
            ai_feedback={
                "format": FEEDBACK_FORMAT,
                "prompt_version": result.prompt_version,
                "provider": result.provider,
                "model": result.model,
                "category_code": prepared.code,
                "rule_en": output.rule_en,
                "rule_fr": output.rule_fr,
                "items": [item.model_dump(mode="json") for item in output.items],
                "answers": [],
            },
            ai_call_id=result.call_id,
            study_session_id=prepared.study_session_id,
            created_at=at,
            updated_at=at,
        )
        session.add(attempt)
        session.flush()
        record_event(
            session,
            DrillGenerated(
                drill_id=attempt.id,
                category_code=prepared.code,
                items=len(output.items),
                provider=result.provider or "unknown",
                model=result.model or "unknown",
                prompt_version=result.prompt_version or f"{TASK}.v1",
                ai_call_id=result.call_id,
            ),
            occurred_at=at,
            study_session_id=prepared.study_session_id,
        )
        session.commit()
        drill_id = attempt.id
    return GenerationResult("ok", None, drill_id)


# --- Reading -------------------------------------------------------------------------------------


def get_drill(session: Session, drill_id: int) -> ProductionAttempt:
    attempt = session.get(ProductionAttempt, drill_id)
    if attempt is None or attempt.kind is not ProductionKind.DRILL or not attempt.ai_feedback:
        raise DrillNotFound(f"There is no drill {drill_id}.")
    return attempt


def list_drills(
    session: Session, *, category: str | None = None, limit: int = 20, offset: int = 0
) -> tuple[list[ProductionAttempt], int]:
    """Newest first; `category` is a code prefix."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    condition = ProductionAttempt.kind == ProductionKind.DRILL
    if category:
        condition = condition & (
            (ProductionAttempt.prompt_text == category)
            | ProductionAttempt.prompt_text.startswith(category + ".", autoescape=True)
        )
    page = session.scalars(
        select(ProductionAttempt)
        .where(condition)
        .order_by(ProductionAttempt.created_at.desc(), ProductionAttempt.id.desc())
        .limit(limit)
        .offset(max(offset, 0))
    )
    total = session.scalar(select(func.count()).select_from(ProductionAttempt).where(condition))
    return list(page), total or 0


def answers_by_index(feedback: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {answer["index"]: answer for answer in feedback.get("answers", [])}


# --- Answering -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerResult:
    result: dict[str, Any]
    error_event_id: int | None


def _error_category(session: Session, item_code: str, drill_code: str) -> ErrorCategory:
    for code in (item_code, drill_code):
        category = error_log.category_by_code(session, code)
        if category is not None and category.status is ErrorCategoryStatus.ACTIVE:
            return category
    return error_log.active_category(session, drill_code)  # raises UnknownCategory


def answer_item(
    session: Session,
    drill_id: int,
    index: int,
    *,
    answer: str | None,
    choice_index: int | None,
    response_time_ms: int,
    at: datetime,
) -> AnswerResult:
    """Grade one item and record it. Raises DrillNotFound, DrillItemNotFound, AlreadyAnswered,
    ExerciseMismatch. In the caller's transaction."""
    at = as_utc(at)
    attempt = get_drill(session, drill_id)
    feedback = dict(attempt.ai_feedback or {})
    items: list[dict[str, Any]] = feedback["items"]
    if not 0 <= index < len(items):
        raise DrillItemNotFound(f"Drill {drill_id} has no item {index}.")
    if index in answers_by_index(feedback):
        raise AlreadyAnswered("This item was already answered.")
    item = items[index]
    shown = (
        rules.options_order(drill_id, index, item["options"])
        if item["kind"] == "choice" and item.get("options")
        else None
    )
    if item["kind"] == "choice":
        if answer is not None and answer.strip():
            raise ExerciseMismatch("A choice item is answered with `choice_index`.")
        if choice_index is not None and (shown is None or not 0 <= choice_index < len(shown)):
            raise ExerciseMismatch("`choice_index` is not one of the options.")
    elif choice_index is not None:
        raise ExerciseMismatch("A gap-fill item is answered with `answer`, not `choice_index`.")
    graded = rules.grade_item(item, shown, answer=answer, choice_index=choice_index)
    elapsed = max(0, min(response_time_ms, MAX_RESPONSE_TIME_MS))
    drill_code = feedback["category_code"]
    error_id: int | None = None
    if graded.outcome == "wrong":
        accepted = [form for form in item.get("accepted", [])][: error_log.MAX_ALTERNATIVES]
        event = error_log.record_error(
            session,
            source=ErrorSource.DRILL,
            category=_error_category(session, item["category_code"], drill_code),
            erroneous_text=rules.fill_gap(item["sentence"], graded.given),
            correction=rules.fill_gap(item["sentence"], item["answer"]),
            at=at,
            original_text=item["sentence"],
            alternatives=[rules.fill_gap(item["sentence"], form) for form in accepted],
            explanation=item["explanation_en"],
            production_attempt_id=attempt.id,
            study_session_id=attempt.study_session_id,
        )
        error_id = event.id
    answers = [
        *feedback.get("answers", []),
        {
            "index": index,
            "given": graded.given,
            "choice_index": choice_index,
            "outcome": graded.outcome,
            "response_time_ms": elapsed,
            "error_event_id": error_id,
            "answered_at": at.isoformat(),
        },
    ]
    attempt.ai_feedback = {**feedback, "answers": answers}  # reassignment (D-020)
    attempt.updated_at = at
    record_event(
        session,
        DrillItemAnswered(
            drill_id=attempt.id,
            index=index,
            category_code=item["category_code"],
            outcome=graded.outcome,
            response_time_ms=elapsed,
        ),
        occurred_at=at,
        study_session_id=attempt.study_session_id,
    )
    if len(answers) == len(items):
        total = rules.score(len(items), answers)
        record_event(
            session,
            DrillCompleted(
                drill_id=attempt.id,
                category_code=drill_code,
                items=len(items),
                correct=total["correct"],
                wrong=total["wrong"],
                empty=total["empty"],
            ),
            occurred_at=at,
            study_session_id=attempt.study_session_id,
        )
    session.flush()
    return AnswerResult(
        rules.item_result(drill_id, index, item, outcome=graded.outcome, given=graded.given),
        error_id,
    )
