"""Cards made from errors and suggestions for recurring errors (module E, M5.a3, D-163).

`create_card_from_error` turns one error of the log into a term of the library: a `learning` term
in the deck "Error cards" (kind `error_drill`) with a small sheet made from the error, one gap-fill
exercise, and **one productive card** (departure from "two cards per term", approved with the
plan: a grammar rule has no receptive exercise without an AI). The card is due at the start of the
next study day, like the cards of a discovery. No AI call: the card works in degraded mode.

`list_suggestions` groups the identical (wrong form, correction) pairs of the log, leaves out the
ones the user dismissed or that already are in the library, and says which can become a card.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    Card,
    Deck,
    ErrorCategory,
    ErrorEvent,
    EventLog,
    LexicalItem,
)
from app.db.settings_store import get_setting
from app.domain import error_cards as rules
from app.domain import exercises as ex
from app.domain.enums import (
    CardDirection,
    ContentOrigin,
    DeckKind,
    DeckStatus,
    ErrorSource,
    ItemStatus,
)
from app.domain.error_cards import ErrorRow, NotCardable, Suggestion
from app.domain.events import (
    CardCreated,
    ErrorCardCreated,
    ErrorSuggestionDismissed,
    EventType,
    ItemOrigin,
)
from app.domain.fsrs_engine import default_engine_factory
from app.domain.item_status import TransitionKind
from app.domain.normalize import normalize_term
from app.domain.srs import EngineFactory
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.domain.usage_sheet import UsageSheet
from app.services import error_log
from app.services.decks import change_deck_status
from app.services.enrichment import Provenance, add_templates, store_generated_sheet
from app.services.items import set_item_status
from app.services.library import (
    InvalidTerm,
    LibraryError,
    add_item_to_deck,
    create_deck,
    create_item,
)
from app.services.reviews import apply_card_state

DECK_NAME = "Error cards"
DECK_DESCRIPTION = (
    "Terms made from your own errors: the correct form, with the sentence it came from."
)
PROVENANCE = Provenance("error", None, "error-card-v1")
MAX_SUGGESTIONS = 50


class CardExists(LibraryError):
    status, code = 409, "card_exists"


class NotCardableError(LibraryError):
    status, code = 422, "not_cardable"


class SuggestionNotFound(LibraryError):
    status, code = 404, "suggestion_not_found"


# --- Reading the log -----------------------------------------------------------------------------


def _rows(session: Session) -> list[ErrorRow]:
    """The errors that can recur. A drill's own mistakes are left out (D-137): they are sentences
    chosen by the generator, not habits."""
    return [
        ErrorRow(error_id, wrong, right, code, occurred_at)
        for error_id, wrong, right, code, occurred_at in session.execute(
            select(
                ErrorEvent.id,
                ErrorEvent.erroneous_text,
                ErrorEvent.correction,
                ErrorCategory.code,
                ErrorEvent.occurred_at,
            )
            .join(ErrorCategory, ErrorCategory.id == ErrorEvent.category_id)
            .where(ErrorEvent.source != ErrorSource.DRILL)
            .order_by(ErrorEvent.id)
        )
    ]


def recurrence_of(session: Session, error: ErrorEvent) -> int:
    key = rules.pair_key(error.erroneous_text, error.correction)
    return sum(1 for r in _rows(session) if rules.pair_key(r.erroneous_text, r.correction) == key)


def dismissed_keys(session: Session) -> set[str]:
    payloads = session.scalars(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.ERROR_SUGGESTION_DISMISSED.value
        )
    )
    return {str(payload["key"]) for payload in payloads}


def item_of_error(session: Session, error_id: int) -> LexicalItem | None:
    return session.scalar(
        select(LexicalItem)
        .where(LexicalItem.origin_error_event_id == error_id)
        .order_by(LexicalItem.id)
        .limit(1)
    )


def cards_of(session: Session, errors: Sequence[ErrorEvent]) -> dict[int, LexicalItem]:
    """error id -> the term made from it, for the errors that have one."""
    if not errors:
        return {}
    return {
        item.origin_error_event_id: item
        for item in session.scalars(
            select(LexicalItem)
            .where(LexicalItem.origin_error_event_id.in_([error.id for error in errors]))
            .order_by(LexicalItem.id.desc())
        )
        if item.origin_error_event_id is not None
    }


def _carded_keys(session: Session) -> set[str]:
    """The pairs that already gave a card."""
    return {
        rules.pair_key(wrong, right)
        for wrong, right in session.execute(
            select(ErrorEvent.erroneous_text, ErrorEvent.correction).join(
                LexicalItem, LexicalItem.origin_error_event_id == ErrorEvent.id
            )
        )
    }


def _term_in_library(session: Session, term: str) -> LexicalItem | None:
    return session.scalar(
        select(LexicalItem)
        .where(LexicalItem.normalized_form == normalize_term(term))
        .order_by(LexicalItem.id)
        .limit(1)
    )


# --- Creating the card ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardMade:
    item: LexicalItem
    card: Card
    deck: Deck
    plan: rules.CardPlan


def _plan(error: ErrorEvent, term: str | None, sentence: str | None) -> rules.CardPlan:
    try:
        return rules.plan_card(
            erroneous_text=error.erroneous_text,
            correction=error.correction,
            original_text=error.original_text,
            explanation=error.explanation,
            term=term,
            sentence=sentence,
        )
    except NotCardable as exc:
        raise NotCardableError(str(exc), reason=exc.reason) from exc


def error_cards_deck(session: Session, at: datetime) -> Deck:
    """The deck of the cards made from errors, created and activated with the first one."""
    deck = session.scalar(
        select(Deck).where(Deck.kind == DeckKind.ERROR_DRILL).order_by(Deck.id).limit(1)
    )
    if deck is None:
        deck = create_deck(
            session, name=DECK_NAME, at=at, description=DECK_DESCRIPTION, kind=DeckKind.ERROR_DRILL
        )
        change_deck_status(session, deck, DeckStatus.ACTIVE, at)
    return deck


def create_card_from_error(
    session: Session,
    error_id: int,
    *,
    at: datetime,
    term: str | None = None,
    sentence: str | None = None,
    engine_factory: EngineFactory = default_engine_factory,
) -> CardMade:
    """Raises ErrorNotFound, CardExists, NotCardableError. In the caller's transaction."""
    at = as_utc(at)
    error = error_log.get_error(session, error_id)
    existing = item_of_error(session, error.id)
    if existing is not None:
        raise CardExists(f"'{existing.term}' already is a card of this error.", item_id=existing.id)
    plan = _plan(error, term, sentence)
    duplicate = _term_in_library(session, plan.term)
    if duplicate is not None:
        raise CardExists(f"'{duplicate.term}' already is in your library.", item_id=duplicate.id)
    category = session.get_one(ErrorCategory, error.category_id)
    deck = error_cards_deck(session, at)
    try:
        item = create_item(
            session,
            term=plan.term,
            at=at,
            origin=ItemOrigin.ERROR,
            sentence=plan.sentence,
            deck_id=deck.id,
        )
    except InvalidTerm as exc:
        raise NotCardableError(exc.message, reason="invalid_term") from exc
    item.origin_error_event_id = error.id
    add_item_to_deck(session, deck, item, at, context_sentence=plan.sentence)
    set_item_status(session, item, ItemStatus.LEARNING, at, TransitionKind.FROM_ERROR)
    item.discovered_at = at
    store_generated_sheet(session, item.id, UsageSheet.model_validate(plan.sheet), at, PROVENANCE)
    add_templates(
        session,
        item.id,
        [(ex.GAP_FILL, plan.gap_fill)],
        at,
        origin=ContentOrigin.USER,
        prompt_version=PROVENANCE.prompt_version,
    )

    tz = ZoneInfo(get_setting(session, "timezone"))
    day_start_hour = get_setting(session, "day_start_hour")
    _, next_day_start = study_day_bounds(study_day_of(at, tz, day_start_hour), tz, day_start_hour)
    engine = engine_factory(get_setting(session, "target_retention"))
    card = Card(lexical_item_id=item.id, direction=CardDirection.PRODUCTIVE, due=next_day_start)
    session.add(card)
    session.flush()
    apply_card_state(card, engine.initial_state(card.id, next_day_start), engine.algorithm)
    record_event(
        session,
        CardCreated(card_id=card.id, lexical_item_id=item.id, direction=CardDirection.PRODUCTIVE),
        occurred_at=at,
    )
    record_event(
        session,
        ErrorCardCreated(
            error_event_id=error.id,
            lexical_item_id=item.id,
            card_id=card.id,
            deck_id=deck.id,
            category_code=category.code,
            source=ErrorSource(error.source),
            recurrence=recurrence_of(session, error),
        ),
        occurred_at=at,
    )
    session.flush()
    return CardMade(item=item, card=card, deck=deck, plan=plan)


# --- Suggestions ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SuggestionView:
    suggestion: Suggestion
    error_id: int  # the error to make the card from: the newest one that can become a card
    term: str | None
    cardable: bool
    reason: str | None  # why not (a stable code of NotCardable)


def _view(session: Session, suggestion: Suggestion) -> SuggestionView | None:
    """None when the proposed term already is in the library."""
    first_failure: tuple[int, str] | None = None
    for error_id in suggestion.error_ids:
        error = session.get(ErrorEvent, error_id)
        if error is None:
            continue
        try:
            plan = _plan(error, None, None)
        except NotCardableError as exc:
            if first_failure is None:
                first_failure = (error_id, str(exc.extra["reason"]))
            continue
        if _term_in_library(session, plan.term) is not None:
            return None
        return SuggestionView(suggestion, error_id, plan.term, True, None)
    error_id, reason = first_failure or (suggestion.latest_error_id, "no_correction")
    return SuggestionView(suggestion, error_id, None, False, reason)


def current_suggestions(
    session: Session, *, min_count: int = rules.MIN_RECURRENCE, include_dismissed: bool = False
) -> list[Suggestion]:
    found = rules.group_recurring(_rows(session), min_count)
    hidden = _carded_keys(session)
    if not include_dismissed:
        hidden |= dismissed_keys(session)
    return rules.without_keys(found, hidden)


def list_suggestions(
    session: Session, *, min_count: int = rules.MIN_RECURRENCE, limit: int = 20
) -> list[SuggestionView]:
    limit = max(1, min(limit, MAX_SUGGESTIONS))
    views: list[SuggestionView] = []
    for suggestion in current_suggestions(session, min_count=min_count):
        view = _view(session, suggestion)
        if view is not None:
            views.append(view)
        if len(views) == limit:
            break
    return views


def dismiss_suggestion(session: Session, key: str, *, at: datetime) -> bool:
    """The user does not want a card for this recurring error. True if it was dismissed now, False
    if it already was. Raises SuggestionNotFound (no such recurring error)."""
    at = as_utc(at)
    if key in dismissed_keys(session):
        return False
    found = next((s for s in current_suggestions(session) if s.key == key), None)
    if found is None:
        raise SuggestionNotFound("There is no such recurring error to dismiss.")
    record_event(
        session,
        ErrorSuggestionDismissed(
            error_event_id=found.latest_error_id, key=found.key, count=found.count
        ),
        occurred_at=at,
    )
    session.flush()
    return True
