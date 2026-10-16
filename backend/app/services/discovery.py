"""Starting and completing the discovery of a term (module B): the two cards are born here."""

from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Card, Deck, DeckItem, LexicalItem
from app.db.settings_store import get_setting
from app.domain.deck_queue import SUPPLYING_STATUSES
from app.domain.enums import CardDirection, DeckStatus, ItemStatus
from app.domain.events import CardCreated, DiscoveryCompleted
from app.domain.fsrs_engine import default_engine_factory
from app.domain.item_status import TransitionKind
from app.domain.srs import EngineFactory, Rating
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.services.decks import change_deck_status
from app.services.items import set_item_status
from app.services.reviews import apply_card_state, record_review

DISCOVERY_EXERCISE_TYPE = "discovery"


class DiscoveryError(ValueError):
    """The term cannot start or complete discovery through this deck."""


def start_discovery(
    session: Session,
    item: LexicalItem,
    via_deck: Deck | None,
    at: datetime,
    *,
    study_session_id: int | None = None,
) -> None:
    """Queued -> discovering. A queued deck becomes active with its first discovered term."""
    at = as_utc(at)
    if via_deck is not None:
        linked = session.scalar(
            select(
                exists().where(DeckItem.deck_id == via_deck.id, DeckItem.lexical_item_id == item.id)
            )
        )
        if not linked:
            raise DiscoveryError(f"item {item.id} is not in deck {via_deck.id}")
        if via_deck.status not in SUPPLYING_STATUSES:
            raise DiscoveryError(f"deck {via_deck.id} is {via_deck.status}: no new terms")
    set_item_status(
        session,
        item,
        ItemStatus.DISCOVERING,
        at,
        TransitionKind.START_DISCOVERY,
        study_session_id=study_session_id,
    )
    if via_deck is not None and via_deck.status == DeckStatus.QUEUED:
        change_deck_status(session, via_deck, DeckStatus.ACTIVE, at)


def complete_discovery(
    session: Session,
    item: LexicalItem,
    at: datetime,
    initial_ratings: Mapping[CardDirection, Rating] | None = None,
    duration_ms: int | None = None,
    *,
    study_session_id: int | None = None,
    engine_factory: EngineFactory = default_engine_factory,
) -> tuple[Card, Card]:
    """Discovering -> learning; creates the receptive and productive cards.

    With `initial_ratings`, the first review of each rated card is recorded at once. Without, the
    cards stay `new` and are due at the start of the next study day.
    Returns (receptive, productive).
    """
    at = as_utc(at)
    if session.scalar(select(exists().where(Card.lexical_item_id == item.id))):
        raise DiscoveryError(f"item {item.id} already has cards")
    set_item_status(
        session,
        item,
        ItemStatus.LEARNING,
        at,
        TransitionKind.COMPLETE_DISCOVERY,
        study_session_id=study_session_id,
    )
    item.discovered_at = at

    tz = ZoneInfo(get_setting(session, "timezone"))
    day_start_hour = get_setting(session, "day_start_hour")
    _, next_day_start = study_day_bounds(study_day_of(at, tz, day_start_hour), tz, day_start_hour)
    engine = engine_factory(get_setting(session, "target_retention"))

    cards: list[Card] = []
    for direction in (CardDirection.RECEPTIVE, CardDirection.PRODUCTIVE):
        card = Card(lexical_item_id=item.id, direction=direction, due=next_day_start)
        session.add(card)
        session.flush()
        apply_card_state(card, engine.initial_state(card.id, next_day_start), engine.algorithm)
        record_event(
            session,
            CardCreated(card_id=card.id, lexical_item_id=item.id, direction=direction),
            occurred_at=at,
            study_session_id=study_session_id,
        )
        cards.append(card)
    record_event(
        session,
        DiscoveryCompleted(lexical_item_id=item.id, duration_ms=duration_ms),
        occurred_at=at,
        study_session_id=study_session_id,
    )

    for card in cards:
        rating = (initial_ratings or {}).get(CardDirection(card.direction))
        if rating is not None:
            record_review(
                session,
                card,
                rating,
                at,
                None,
                DISCOVERY_EXERCISE_TYPE,
                study_session_id=study_session_id,
                engine_factory=engine_factory,
            )
    session.flush()
    return cards[0], cards[1]
