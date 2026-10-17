"""Error log endpoints (module E, M5.a1): error events and the error taxonomy.

The module is named `error_log` because `app/api/errors.py` holds the API's error format (D-063).
Routes stay thin: one service call in one transaction, then commit. No AI call here: everything
works in degraded mode.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.db.models import ErrorCategory, ErrorEvent
from app.domain.enums import ErrorSource
from app.services import error_log

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
Short = Annotated[str, Field(min_length=1, max_length=300)]
Alternative = Annotated[str, Field(min_length=1, max_length=300)]
Alternatives = Annotated[list[Alternative], Field(max_length=error_log.MAX_ALTERNATIVES)]
Explanation = Annotated[str, Field(max_length=1000)]
Label = Annotated[str, Field(min_length=1, max_length=200)]


# --- Shapes --------------------------------------------------------------------------------------


class CategoryRef(BaseModel):
    code: str
    label_en: str
    label_fr: str
    status: str


class TermRef(BaseModel):
    id: int
    term: str


class ErrorOut(BaseModel):
    id: int
    source: ErrorSource
    original_text: str
    erroneous_text: str
    correction: str
    alternatives: list[str]
    explanation: str
    explanation_fr: str | None  # the AI's translation, while the explanation is still the AI's
    category: CategoryRef
    term: TermRef | None
    production_attempt_id: int | None
    review_log_id: int | None
    occurred_at: datetime
    updated_at: datetime


def errors_out(session: Session, errors: list[ErrorEvent]) -> list[ErrorOut]:
    categories = error_log.categories_of(session, errors)
    terms = error_log.terms_of(session, errors)
    french = error_log.french_explanations(session, errors)
    out = []
    for error in errors:
        category = categories[error.category_id]
        item_id = error.lexical_item_id
        out.append(
            ErrorOut(
                id=error.id,
                source=error.source,
                original_text=error.original_text,
                erroneous_text=error.erroneous_text,
                correction=error.correction,
                alternatives=list(error.alternatives),
                explanation=error.explanation,
                explanation_fr=french.get(error.id),
                category=_category_ref(category),
                term=TermRef(id=item_id, term=terms[item_id])
                if item_id is not None and item_id in terms
                else None,
                production_attempt_id=error.production_attempt_id,
                review_log_id=error.review_log_id,
                occurred_at=error.occurred_at,
                updated_at=error.updated_at,
            )
        )
    return out


def _category_ref(category: ErrorCategory) -> CategoryRef:
    return CategoryRef(
        code=category.code,
        label_en=category.label_en,
        label_fr=category.label_fr,
        status=str(category.status),
    )


class FacetOut(BaseModel):
    code: str
    label_en: str
    label_fr: str
    count: int


class ErrorPageOut(BaseModel):
    errors: list[ErrorOut]
    total: int
    page: int
    page_size: int
    facets: list[FacetOut]  # per level-2 category, over the whole filtered set


# --- Errors --------------------------------------------------------------------------------------


class ManualErrorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: Annotated[str, Field(max_length=1000)] | None = None
    erroneous_text: Short
    correction: Short
    alternatives: Alternatives = []
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    explanation: Explanation = ""
    lexical_item_id: int | None = None


@router.post("/errors", status_code=201, tags=["errors"])
def add_error(body: ManualErrorRequest, session: SessionDep, now: NowDep) -> ErrorOut:
    """An error typed by the user (source `manual`)."""
    error = error_log.add_manual_error(
        session,
        original_text=body.original_text,
        erroneous_text=body.erroneous_text,
        correction=body.correction,
        alternatives=body.alternatives,
        category_code=body.category_code,
        explanation=body.explanation,
        lexical_item_id=body.lexical_item_id,
        at=now,
    )
    session.commit()
    return errors_out(session, [error])[0]


@router.get("/errors", tags=["errors"])
def list_errors(
    session: SessionDep,
    category: Annotated[str | None, Query(max_length=200)] = None,
    source: ErrorSource | None = None,
    item_id: int | None = None,
    production_id: int | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    q: Annotated[str | None, Query(max_length=300)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=error_log.MAX_PAGE_SIZE)] = 20,
) -> ErrorPageOut:
    """Newest first. `category` is a code prefix (`grammar.preposition` includes its
    subcategories); `occurred_to` is exclusive; `q` searches the texts."""
    result = error_log.list_errors(
        session,
        error_log.ErrorFilter(
            category=category,
            source=source,
            lexical_item_id=item_id,
            production_attempt_id=production_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            text=q,
        ),
        page=page,
        page_size=page_size,
    )
    return ErrorPageOut(
        errors=errors_out(session, result.errors),
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        facets=[FacetOut(**vars(facet)) for facet in result.facets],
    )


@router.get("/errors/{error_id}", tags=["errors"])
def get_error(error_id: int, session: SessionDep) -> ErrorOut:
    return errors_out(session, [error_log.get_error(session, error_id)])[0]


class ErrorPatch(BaseModel):
    """Only the fields sent are changed; `lexical_item_id: null` unlinks the term."""

    model_config = ConfigDict(extra="forbid")

    correction: Short | None = None
    alternatives: Alternatives | None = None
    explanation: Explanation | None = None
    category_code: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    lexical_item_id: int | None = None


@router.patch("/errors/{error_id}", tags=["errors"])
def update_error(error_id: int, body: ErrorPatch, session: SessionDep, now: NowDep) -> ErrorOut:
    changes: dict[str, Any] = {}
    for name in body.model_fields_set:
        value = getattr(body, name)
        if name == "category_code":
            if value is not None:
                changes["category"] = value
        elif name == "lexical_item_id" or value is not None:
            changes[name] = value
    error = error_log.update_error(session, error_id, changes, at=now)
    session.commit()
    return errors_out(session, [error])[0]


@router.delete("/errors/{error_id}", status_code=204, tags=["errors"])
def delete_error(error_id: int, session: SessionDep, now: NowDep) -> Response:
    error_log.delete_error(session, error_id, at=now)
    session.commit()
    return Response(status_code=204)


# --- Categories ----------------------------------------------------------------------------------


class CategoryNodeOut(BaseModel):
    id: int
    code: str
    parent_code: str | None
    label_en: str
    label_fr: str
    description_en: str
    description_fr: str
    status: str
    origin: Literal["builtin", "user", "ai"]
    count: int  # errors in this category and its subcategories
    count_recent: int  # the same, over the last 14 days
    children: list["CategoryNodeOut"]


def _node_out(node: error_log.CategoryNode) -> CategoryNodeOut:
    return CategoryNodeOut(
        id=node.id,
        code=node.code,
        parent_code=node.parent_code,
        label_en=node.label_en,
        label_fr=node.label_fr,
        description_en=node.description_en,
        description_fr=node.description_fr,
        status=node.status,
        origin=node.origin,
        count=node.count,
        count_recent=node.count_recent,
        children=[_node_out(child) for child in node.children],
    )


@router.get("/error-categories", tags=["errors"])
def category_tree(session: SessionDep, now: NowDep) -> list[CategoryNodeOut]:
    """The taxonomy tree, every status (active, proposed, rejected), with error counts."""
    return [_node_out(node) for node in error_log.category_tree(session, now)]


class CategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_code: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    slug: Annotated[str, Field(min_length=1, max_length=41)]
    label_en: Label
    label_fr: Label
    description_en: Explanation = ""
    description_fr: Explanation = ""


@router.post("/error-categories", status_code=201, tags=["errors"])
def create_category(body: CategoryRequest, session: SessionDep, now: NowDep) -> CategoryNodeOut:
    """A category of the user's own, active at once; its code is `<parent_code>.<slug>`."""
    category = error_log.create_category(
        session,
        parent=body.parent_code,
        slug=body.slug,
        label_en=body.label_en,
        label_fr=body.label_fr,
        description_en=body.description_en,
        description_fr=body.description_fr,
        at=now,
    )
    session.commit()
    return _single_node(session, category.id, now)


def _single_node(session: Session, category_id: int, now: datetime) -> CategoryNodeOut:
    def find(nodes: list[error_log.CategoryNode]) -> error_log.CategoryNode | None:
        for node in nodes:
            if node.id == category_id:
                return node
            found = find(node.children)
            if found is not None:
                return found
        return None

    node = find(error_log.category_tree(session, now))
    assert node is not None  # noqa: S101 (just written)
    return _node_out(node)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "reject"]
    label_en: Label | None = None  # accept only: rename the proposal
    label_fr: Label | None = None


class ResolveOut(BaseModel):
    category: CategoryNodeOut
    reassigned_error_ids: list[int]


@router.post("/error-categories/{category_id}/resolve", tags=["errors"])
def resolve_category(
    category_id: int, body: ResolveRequest, session: SessionDep, now: NowDep
) -> ResolveOut:
    """Accept or reject a category proposed by the AI. A rejection moves its errors to the
    parent category."""
    resolution = error_log.resolve_category(
        session,
        category_id,
        body.decision,
        at=now,
        label_en=body.label_en,
        label_fr=body.label_fr,
    )
    session.commit()
    return ResolveOut(
        category=_single_node(session, resolution.category.id, now),
        reassigned_error_ids=resolution.reassigned,
    )
