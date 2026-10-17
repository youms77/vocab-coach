"""The error log (module E): error events and the error taxonomy as the user sees them.

An error comes from a corrected production, a review (a lexical confusion) or manual entry. Every
change writes an event (`error.recorded`, `error.updated`, `error.deleted`), so statistics can
rebuild the history even after a deletion (D-017). Categories form the taxonomy tree: built-in ones
come from `content/error_taxonomy.yaml` (D-016), the user may add their own, and the AI may
propose a subcategory (`<parent>.<slug>`, status `proposed`) that the user accepts or rejects.
A rejection moves the category's errors to its parent.

Like every service, these functions work in the caller's transaction and never commit (D-023).
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import ErrorCategory, ErrorEvent, EventLog, LexicalItem, ProductionAttempt
from app.domain.enums import ErrorCategoryStatus, ErrorSource
from app.domain.events import (
    ErrorCategoryCreated,
    ErrorCategoryProposed,
    ErrorCategoryResolved,
    ErrorDeleted,
    ErrorRecorded,
    ErrorUpdated,
    EventType,
)
from app.domain.sentences import find_fragment
from app.domain.study_day import as_utc
from app.domain.taxonomy import parent_code
from app.services.library import LibraryError, get_item

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
MAX_ALTERNATIVES = 2
MAX_PAGE_SIZE = 100
RECENT_DAYS = 14


class ErrorNotFound(LibraryError):
    status, code = 404, "error_not_found"


class CategoryNotFound(LibraryError):
    status, code = 404, "category_not_found"


class UnknownCategory(LibraryError):
    """A category code that does not exist or is not active."""

    status, code = 422, "unknown_category"


class InvalidError(LibraryError):
    status, code = 422, "invalid_error"


class CategoryExists(LibraryError):
    code = "category_exists"


class CategoryNotProposed(LibraryError):
    code = "category_not_proposed"


# --- Categories ----------------------------------------------------------------------------------


def category_by_code(session: Session, code: str) -> ErrorCategory | None:
    return session.scalar(select(ErrorCategory).where(ErrorCategory.code == code))


def active_category(session: Session, code: str) -> ErrorCategory:
    """The active category `code` (raises UnknownCategory)."""
    category = category_by_code(session, code)
    if category is None or category.status != ErrorCategoryStatus.ACTIVE:
        raise UnknownCategory(f"{code!r} is not an active error category.", category_code=code)
    return category


def active_categories(session: Session) -> list[ErrorCategory]:
    """Active categories, parents before children, in the taxonomy's order."""
    rows = session.scalars(
        select(ErrorCategory).where(ErrorCategory.status == ErrorCategoryStatus.ACTIVE)
    )
    return _tree_order(list(rows))


def _tree_order(categories: list[ErrorCategory]) -> list[ErrorCategory]:
    children: dict[int | None, list[ErrorCategory]] = {}
    ids = {category.id for category in categories}
    for category in categories:
        parent = category.parent_id if category.parent_id in ids else None
        children.setdefault(parent, []).append(category)
    ordered: list[ErrorCategory] = []

    def walk(parent: int | None) -> None:
        for category in sorted(children.get(parent, []), key=lambda c: (c.sort_order, c.code)):
            ordered.append(category)
            walk(category.id)

    walk(None)
    return ordered


def _check_slug(slug: str) -> None:
    if not SLUG.match(slug):
        raise InvalidError(
            "A category name is 2 to 41 lower-case letters, digits or underscores, starting with "
            "a letter.",
            slug=slug,
        )


def create_category(
    session: Session,
    *,
    parent: str | None,
    slug: str,
    label_en: str,
    label_fr: str,
    description_en: str,
    description_fr: str,
    at: datetime,
) -> ErrorCategory:
    """A category added by the user, active at once (the taxonomy is extensible)."""
    _check_slug(slug)
    parent_category = active_category(session, parent) if parent is not None else None
    code = f"{parent}.{slug}" if parent is not None else slug
    if category_by_code(session, code) is not None:
        raise CategoryExists(f"The category {code!r} already exists.", category_code=code)
    at = as_utc(at)
    category = ErrorCategory(
        code=code,
        parent_id=parent_category.id if parent_category is not None else None,
        label_en=label_en,
        label_fr=label_fr,
        description_en=description_en,
        description_fr=description_fr,
        examples=[],
        is_builtin=False,
        status=ErrorCategoryStatus.ACTIVE,
        sort_order=_next_sort_order(session, parent_category),
        created_at=at,
        updated_at=at,
    )
    session.add(category)
    session.flush()
    record_event(
        session,
        ErrorCategoryCreated(error_category_id=category.id, code=code, parent_code=parent),
        occurred_at=at,
    )
    return category


def _next_sort_order(session: Session, parent: ErrorCategory | None) -> int:
    condition = (
        ErrorCategory.parent_id == parent.id
        if parent is not None
        else ErrorCategory.parent_id.is_(None)
    )
    highest = session.scalar(select(func.max(ErrorCategory.sort_order)).where(condition))
    return (highest or 0) + 1


@dataclass(frozen=True)
class Proposal:
    parent_code: str
    slug: str
    label_en: str
    label_fr: str
    description_en: str


@dataclass(frozen=True)
class ProposalOutcome:
    category: ErrorCategory  # where the error goes
    proposed: bool  # a new `proposed` category was created by this call


def propose_category(
    session: Session,
    proposal: Proposal,
    *,
    at: datetime,
    production_attempt_id: int | None = None,
) -> ProposalOutcome:
    """The category an AI-proposed subcategory resolves to.

    - The code already exists and is active (built-in, the user's, or accepted): that category.
    - It is already proposed: the same pending category (one proposal, many errors).
    - It was rejected: the parent (the user said no once; the AI does not ask again).
    - Otherwise a new `proposed` category under the parent, and `error_category.proposed`.
    The parent must be active (raises UnknownCategory).
    """
    parent = active_category(session, proposal.parent_code)
    _check_slug(proposal.slug)
    code = f"{proposal.parent_code}.{proposal.slug}"
    existing = category_by_code(session, code)
    if existing is not None:
        if existing.status == ErrorCategoryStatus.REJECTED:
            return ProposalOutcome(parent, proposed=False)
        return ProposalOutcome(existing, proposed=False)
    at = as_utc(at)
    category = ErrorCategory(
        code=code,
        parent_id=parent.id,
        label_en=proposal.label_en,
        label_fr=proposal.label_fr,
        description_en=proposal.description_en,
        description_fr="",
        examples=[],
        is_builtin=False,
        status=ErrorCategoryStatus.PROPOSED,
        sort_order=_next_sort_order(session, parent),
        created_at=at,
        updated_at=at,
    )
    session.add(category)
    session.flush()
    record_event(
        session,
        ErrorCategoryProposed(
            error_category_id=category.id,
            code=code,
            parent_code=proposal.parent_code,
            production_attempt_id=production_attempt_id,
        ),
        occurred_at=at,
    )
    return ProposalOutcome(category, proposed=True)


@dataclass(frozen=True)
class Resolution:
    category: ErrorCategory
    reassigned: list[int]  # error ids moved to the parent (rejection)


def resolve_category(
    session: Session,
    category_id: int,
    decision: Literal["accept", "reject"],
    *,
    at: datetime,
    label_en: str | None = None,
    label_fr: str | None = None,
) -> Resolution:
    """Accept a proposed category (optionally renamed), or reject it: its errors move to the
    parent, one `error.updated` each, and it stays as `rejected` (never proposed again)."""
    category = session.get(ErrorCategory, category_id)
    if category is None:
        raise CategoryNotFound(f"There is no error category {category_id}.")
    if category.status != ErrorCategoryStatus.PROPOSED:
        raise CategoryNotProposed(
            f"The category {category.code!r} is {category.status}, not proposed.",
            category_status=str(category.status),
        )
    at = as_utc(at)
    parent = session.get_one(ErrorCategory, category.parent_id)
    reassigned: list[int] = []
    if decision == "accept":
        category.status = ErrorCategoryStatus.ACTIVE
        if label_en:
            category.label_en = label_en
        if label_fr:
            category.label_fr = label_fr
    else:
        category.status = ErrorCategoryStatus.REJECTED
        errors = session.scalars(
            select(ErrorEvent).where(ErrorEvent.category_id == category.id).order_by(ErrorEvent.id)
        )
        for error in errors:
            error.category_id = parent.id
            error.updated_at = at
            reassigned.append(error.id)
            record_event(
                session,
                ErrorUpdated(
                    error_event_id=error.id,
                    source=error.source,
                    changed=["category"],
                    old_category_code=category.code,
                    new_category_code=parent.code,
                    old_lexical_item_id=error.lexical_item_id,
                    new_lexical_item_id=error.lexical_item_id,
                    reason="category_rejected",
                ),
                occurred_at=at,
            )
    category.updated_at = at
    record_event(
        session,
        ErrorCategoryResolved(
            error_category_id=category.id,
            code=category.code,
            parent_code=parent.code,
            decision=decision,
            reassigned_errors=len(reassigned),
        ),
        occurred_at=at,
    )
    session.flush()
    return Resolution(category, reassigned)


@dataclass
class CategoryNode:
    id: int
    code: str
    parent_code: str | None
    label_en: str
    label_fr: str
    description_en: str
    description_fr: str
    status: str
    origin: Literal["builtin", "user", "ai"]
    count: int  # errors in this category and its descendants
    count_recent: int  # the same, over the last RECENT_DAYS days
    children: list["CategoryNode"] = field(default_factory=list)


def category_tree(session: Session, now: datetime) -> list[CategoryNode]:
    """The whole taxonomy (every status), with error counts aggregated by code prefix (D-016)."""
    categories = _tree_order(list(session.scalars(select(ErrorCategory))))
    since = as_utc(now) - timedelta(days=RECENT_DAYS)
    own: Counter[int] = Counter()
    recent: Counter[int] = Counter()
    rows = session.execute(select(ErrorEvent.category_id, ErrorEvent.occurred_at))
    for category_id, occurred_at in rows:
        own[category_id] += 1
        if as_utc(occurred_at) >= since:
            recent[category_id] += 1
    proposed_ids = set(
        session.scalars(
            select(EventLog.entity_id).where(
                EventLog.event_type == EventType.ERROR_CATEGORY_PROPOSED.value
            )
        )
    )
    nodes: dict[int, CategoryNode] = {}
    roots: list[CategoryNode] = []
    for category in categories:
        origin: Literal["builtin", "user", "ai"] = (
            "builtin" if category.is_builtin else "ai" if category.id in proposed_ids else "user"
        )
        node = CategoryNode(
            id=category.id,
            code=category.code,
            parent_code=parent_code(category.code),
            label_en=category.label_en,
            label_fr=category.label_fr,
            description_en=category.description_en,
            description_fr=category.description_fr,
            status=str(category.status),
            origin=origin,
            count=own[category.id],
            count_recent=recent[category.id],
        )
        nodes[category.id] = node
        parent = nodes.get(category.parent_id) if category.parent_id is not None else None
        (parent.children if parent is not None else roots).append(node)

    def total(node: CategoryNode) -> tuple[int, int]:
        for child in node.children:
            count, count_recent = total(child)
            node.count += count
            node.count_recent += count_recent
        return node.count, node.count_recent

    for root in roots:
        total(root)
    return roots


# --- Error events --------------------------------------------------------------------------------


def _check_alternatives(alternatives: Sequence[str]) -> list[str]:
    cleaned = [a.strip() for a in alternatives if a.strip()]
    if len(cleaned) > MAX_ALTERNATIVES:
        raise InvalidError(f"At most {MAX_ALTERNATIVES} alternatives.")
    return cleaned


def record_error(
    session: Session,
    *,
    source: ErrorSource,
    category: ErrorCategory,
    erroneous_text: str,
    correction: str,
    at: datetime,
    original_text: str = "",
    alternatives: Sequence[str] = (),
    explanation: str = "",
    lexical_item_id: int | None = None,
    production_attempt_id: int | None = None,
    review_log_id: int | None = None,
    study_session_id: int | None = None,
) -> ErrorEvent:
    """Add one error event and `error.recorded`. The callers check their own inputs."""
    at = as_utc(at)
    error = ErrorEvent(
        production_attempt_id=production_attempt_id,
        review_log_id=review_log_id,
        source=source,
        original_text=original_text,
        erroneous_text=erroneous_text,
        correction=correction,
        alternatives=list(alternatives),
        explanation=explanation,
        category_id=category.id,
        lexical_item_id=lexical_item_id,
        occurred_at=at,
        created_at=at,
        updated_at=at,
    )
    session.add(error)
    session.flush()
    record_event(
        session,
        ErrorRecorded(
            error_event_id=error.id,
            category_code=category.code,
            source=source,
            lexical_item_id=lexical_item_id,
        ),
        occurred_at=at,
        study_session_id=study_session_id,
    )
    return error


def add_manual_error(
    session: Session,
    *,
    original_text: str | None,
    erroneous_text: str,
    correction: str,
    alternatives: Sequence[str],
    category_code: str,
    explanation: str,
    lexical_item_id: int | None,
    at: datetime,
) -> ErrorEvent:
    """An error typed by the user (source `manual`)."""
    erroneous_text, correction = erroneous_text.strip(), correction.strip()
    if not erroneous_text or not correction:
        raise InvalidError("The wrong form and the correction are both required.")
    if erroneous_text == correction:
        raise InvalidError("The correction must differ from the wrong form.")
    original = (original_text or "").strip()
    if original and find_fragment(original, erroneous_text) is None:
        raise InvalidError("The original sentence must contain the wrong form.")
    category = active_category(session, category_code)
    if lexical_item_id is not None:
        get_item(session, lexical_item_id)
    return record_error(
        session,
        source=ErrorSource.MANUAL,
        category=category,
        erroneous_text=erroneous_text,
        correction=correction,
        at=at,
        original_text=original,
        alternatives=_check_alternatives(alternatives),
        explanation=explanation.strip(),
        lexical_item_id=lexical_item_id,
    )


def get_error(session: Session, error_id: int) -> ErrorEvent:
    error = session.get(ErrorEvent, error_id)
    if error is None:
        raise ErrorNotFound(f"There is no error {error_id}.")
    return error


_EDITABLE = ("correction", "alternatives", "explanation", "category", "lexical_item_id")


def update_error(
    session: Session, error_id: int, changes: dict[str, Any], *, at: datetime
) -> ErrorEvent:
    """Edit an error. `changes` holds only the fields the user sent (keys of `_EDITABLE`;
    `category` is a code, `lexical_item_id` may be None to unlink the term). Writes
    `error.updated` with the fields that really changed; nothing when none did."""
    unknown = set(changes) - set(_EDITABLE)
    if unknown:
        raise InvalidError(f"These fields cannot be edited: {', '.join(sorted(unknown))}.")
    error = get_error(session, error_id)
    old_category = session.get_one(ErrorCategory, error.category_id)
    new_category = old_category
    old_item = error.lexical_item_id
    changed: list[str] = []
    if "correction" in changes:
        correction = str(changes["correction"]).strip()
        if not correction or correction == error.erroneous_text:
            raise InvalidError("The correction must be given and differ from the wrong form.")
        if correction != error.correction:
            error.correction = correction
            changed.append("correction")
    if "alternatives" in changes:
        alternatives = _check_alternatives(changes["alternatives"])
        if alternatives != list(error.alternatives):
            error.alternatives = alternatives
            changed.append("alternatives")
    if "explanation" in changes:
        explanation = str(changes["explanation"]).strip()
        if explanation != error.explanation:
            error.explanation = explanation
            changed.append("explanation")
    if "category" in changes and changes["category"] != old_category.code:
        new_category = active_category(session, str(changes["category"]))
        error.category_id = new_category.id
        changed.append("category")
    if "lexical_item_id" in changes and changes["lexical_item_id"] != old_item:
        item_id = changes["lexical_item_id"]
        if item_id is not None:
            get_item(session, item_id)
        error.lexical_item_id = item_id
        changed.append("lexical_item_id")
    if changed:
        at = as_utc(at)
        error.updated_at = at
        record_event(
            session,
            ErrorUpdated(
                error_event_id=error.id,
                source=error.source,
                changed=changed,
                old_category_code=old_category.code,
                new_category_code=new_category.code,
                old_lexical_item_id=old_item,
                new_lexical_item_id=error.lexical_item_id,
            ),
            occurred_at=at,
        )
        session.flush()
    return error


def delete_error(session: Session, error_id: int, *, at: datetime) -> None:
    """Delete the row; `error.deleted` keeps its trace (the log is append-only, D-017)."""
    error = get_error(session, error_id)
    category = session.get_one(ErrorCategory, error.category_id)
    record_event(
        session,
        ErrorDeleted(error_event_id=error.id, category_code=category.code, source=error.source),
        occurred_at=as_utc(at),
    )
    session.delete(error)
    session.flush()


# --- Listing -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorFilter:
    category: str | None = None  # a code prefix: the category and its descendants
    source: ErrorSource | None = None
    lexical_item_id: int | None = None
    production_attempt_id: int | None = None
    occurred_from: datetime | None = None  # inclusive
    occurred_to: datetime | None = None  # exclusive
    text: str | None = None  # in the original text, wrong form, correction or explanation


@dataclass(frozen=True)
class Facet:
    code: str  # a level-2 code (or a level-1 code without children, such as `spelling`)
    label_en: str
    label_fr: str
    count: int


@dataclass(frozen=True)
class ErrorPage:
    errors: list[ErrorEvent]
    total: int
    page: int
    page_size: int
    facets: list[Facet]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filtered(filters: ErrorFilter) -> Any:
    query = select(ErrorEvent).join(ErrorCategory, ErrorCategory.id == ErrorEvent.category_id)
    if filters.category:
        prefix = filters.category.strip()
        query = query.where(
            or_(
                ErrorCategory.code == prefix,
                ErrorCategory.code.like(_escape_like(prefix) + ".%", escape="\\"),
            )
        )
    if filters.source is not None:
        query = query.where(ErrorEvent.source == filters.source)
    if filters.lexical_item_id is not None:
        query = query.where(ErrorEvent.lexical_item_id == filters.lexical_item_id)
    if filters.production_attempt_id is not None:
        query = query.where(ErrorEvent.production_attempt_id == filters.production_attempt_id)
    if filters.occurred_from is not None:
        query = query.where(ErrorEvent.occurred_at >= as_utc(filters.occurred_from))
    if filters.occurred_to is not None:
        query = query.where(ErrorEvent.occurred_at < as_utc(filters.occurred_to))
    if filters.text and filters.text.strip():
        pattern = "%" + _escape_like(filters.text.strip()) + "%"
        query = query.where(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        ErrorEvent.original_text,
                        ErrorEvent.erroneous_text,
                        ErrorEvent.correction,
                        ErrorEvent.explanation,
                    )
                )
            )
        )
    return query


def level_two(code: str) -> str:
    return ".".join(code.split(".")[:2])


def list_errors(
    session: Session, filters: ErrorFilter, *, page: int = 1, page_size: int = 20
) -> ErrorPage:
    """Errors matching `filters`, newest first, and the counts per level-2 category of the whole
    filtered set (not only the page)."""
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise InvalidError(f"`page` starts at 1 and `page_size` is 1 to {MAX_PAGE_SIZE}.")
    query = _filtered(filters)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    errors = list(
        session.scalars(
            query.order_by(ErrorEvent.occurred_at.desc(), ErrorEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    counts: Counter[str] = Counter()
    sub = query.subquery()
    grouped = (
        select(ErrorCategory.code, func.count())
        .join(sub, sub.c.category_id == ErrorCategory.id)
        .group_by(ErrorCategory.code)
    )
    for code, count in session.execute(grouped):
        counts[level_two(code)] += count
    labels = {
        c.code: c
        for c in session.scalars(select(ErrorCategory).where(ErrorCategory.code.in_(counts)))
    }
    facets = [
        Facet(
            code=code,
            label_en=labels[code].label_en if code in labels else code,
            label_fr=labels[code].label_fr if code in labels else code,
            count=count,
        )
        for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return ErrorPage(errors, total, page, page_size, facets)


# --- Reading helpers for the API and the CLI ----------------------------------------------------


def categories_of(session: Session, errors: Sequence[ErrorEvent]) -> dict[int, ErrorCategory]:
    ids = {error.category_id for error in errors}
    rows = session.scalars(select(ErrorCategory).where(ErrorCategory.id.in_(ids))) if ids else []
    return {category.id: category for category in rows}


def terms_of(session: Session, errors: Sequence[ErrorEvent]) -> dict[int, str]:
    ids = {error.lexical_item_id for error in errors if error.lexical_item_id is not None}
    if not ids:
        return {}
    rows = session.execute(select(LexicalItem.id, LexicalItem.term).where(LexicalItem.id.in_(ids)))
    return {item_id: term for item_id, term in rows}


def french_explanations(session: Session, errors: Sequence[ErrorEvent]) -> dict[int, str]:
    """The AI's French explanation of each error that came from a correction or a drill, while
    the English one is still the AI's (an edited explanation has no translation)."""
    ids = {e.production_attempt_id for e in errors if e.production_attempt_id is not None}
    if not ids:
        return {}
    rows = session.execute(
        select(ProductionAttempt.id, ProductionAttempt.ai_feedback).where(
            ProductionAttempt.id.in_(ids)
        )
    )
    feedback = {attempt_id: data for attempt_id, data in rows}
    found: dict[int, str] = {}
    for error in errors:
        data = feedback.get(error.production_attempt_id) if error.production_attempt_id else None
        if not data:
            continue
        if data.get("format") == "drill-1":
            french = _drill_french(data, error)
            if french:
                found[error.id] = french
            continue
        output_errors = (data.get("output") or {}).get("errors") or []
        error_ids = data.get("error_event_ids") or []
        if error.id not in error_ids or error_ids.index(error.id) >= len(output_errors):
            continue
        entry = output_errors[error_ids.index(error.id)]
        if entry.get("explanation_en") == error.explanation and entry.get("explanation_fr"):
            found[error.id] = entry["explanation_fr"]
    return found


def _drill_french(data: dict[str, Any], error: ErrorEvent) -> str | None:
    """The French explanation of the drill item whose wrong answer gave `error`."""
    items = data.get("items") or []
    for answer in data.get("answers") or []:
        if answer.get("error_event_id") != error.id or not 0 <= answer["index"] < len(items):
            continue
        item = items[answer["index"]]
        if item.get("explanation_en") == error.explanation:
            return item.get("explanation_fr") or None
    return None
