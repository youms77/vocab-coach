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
from app.services import error_cards, error_log

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
    card: TermRef | None  # the term made from this error (M5.a3), if any
    production_attempt_id: int | None
    review_log_id: int | None
    occurred_at: datetime
    updated_at: datetime


def errors_out(session: Session, errors: list[ErrorEvent]) -> list[ErrorOut]:
    categories = error_log.categories_of(session, errors)
    terms = error_log.terms_of(session, errors)
    french = error_log.french_explanations(session, errors)
    cards = error_cards.cards_of(session, errors)
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
                card=TermRef(id=cards[error.id].id, term=cards[error.id].term)
                if error.id in cards
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


class SuggestionOut(BaseModel):
    key: str
    erroneous_text: str
    correction: str
    category: CategoryRef
    count: int
    first_at: datetime
    last_at: datetime
    error_id: int  # the error to make the card from (`POST /errors/{id}/card`)
    sample_error_ids: list[int]  # newest first, at most 5
    term: str | None  # the term the card would have
    cardable: bool
    reason: str | None  # why not: `no_context`, `no_correction`, `too_long`...


class SuggestionsOut(BaseModel):
    suggestions: list[SuggestionOut]


@router.get("/errors/suggestions", tags=["errors"])
def error_suggestions(
    session: SessionDep,
    min_count: Annotated[int, Query(ge=1, le=20)] = 2,
    limit: Annotated[int, Query(ge=1, le=error_cards.MAX_SUGGESTIONS)] = 20,
) -> SuggestionsOut:
    """Wrong forms that came back at least `min_count` times with the same correction, the most
    frequent first. Leaves out those with a card, in the library or dismissed. Drill errors do not
    count. No AI."""
    out = []
    for view in error_cards.list_suggestions(session, min_count=min_count, limit=limit):
        found = view.suggestion
        category = error_log.category_by_code(session, found.category_code)
        assert category is not None  # noqa: S101 (the code comes from a category row)
        out.append(
            SuggestionOut(
                key=found.key,
                erroneous_text=found.erroneous_text,
                correction=found.correction,
                category=_category_ref(category),
                count=found.count,
                first_at=found.first_at,
                last_at=found.last_at,
                error_id=view.error_id,
                sample_error_ids=list(found.error_ids),
                term=view.term,
                cardable=view.cardable,
                reason=view.reason,
            )
        )
    return SuggestionsOut(suggestions=out)


class DismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(min_length=1, max_length=700)]


@router.post("/errors/suggestions/dismiss", tags=["errors"])
def dismiss_suggestion(body: DismissRequest, session: SessionDep, now: NowDep) -> dict[str, bool]:
    """The user does not want a card for this recurring error. `dismissed` is false when it was
    dismissed before (nothing is written). 404 `suggestion_not_found`."""
    dismissed = error_cards.dismiss_suggestion(session, body.key, at=now)
    session.commit()
    return {"dismissed": dismissed}


class CardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    sentence: Annotated[str, Field(min_length=1, max_length=400)] | None = None


class CardOut(BaseModel):
    error_id: int
    item_id: int
    term: str
    card_id: int
    deck_id: int
    sentence: str  # the corrected sentence the exercise is made from
    due: datetime  # the start of the next study day


@router.post("/errors/{error_id}/card", status_code=201, tags=["errors"])
def make_card(error_id: int, body: CardRequest, session: SessionDep, now: NowDep) -> CardOut:
    """Make a term and one productive card from this error (no AI). The term is the correction
    (or `term`); the exercise is the sentence the error came from (or `sentence`) with the
    changed words blanked. 409 `card_exists`; 422 `not_cardable` with a `reason`."""
    made = error_cards.create_card_from_error(
        session, error_id, at=now, term=body.term, sentence=body.sentence
    )
    session.commit()
    return CardOut(
        error_id=error_id,
        item_id=made.item.id,
        term=made.item.term,
        card_id=made.card.id,
        deck_id=made.deck.id,
        sentence=made.plan.sentence,
        due=made.card.due,
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
