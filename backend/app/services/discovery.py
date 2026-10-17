"""Starting and completing the discovery of a term (module B): the two cards are born here."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Card, Deck, DeckItem, Enrichment, ExerciseTemplate, LexicalItem
from app.db.settings_store import get_setting
from app.domain import exercises as ex
from app.domain.deck_queue import SUPPLYING_STATUSES
from app.domain.enums import CardDirection, DeckStatus, ItemStatus
from app.domain.events import CardCreated, DiscoveryCompleted, DiscoveryExerciseResult
from app.domain.fsrs_engine import default_engine_factory
from app.domain.grading import GradeWarning
from app.domain.item_status import TransitionKind
from app.domain.srs import EngineFactory, Rating
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.domain.usage_sheet import UsageSheet, is_usable, read_sheet
from app.services.decks import change_deck_status
from app.services.items import set_item_status
from app.services.library import LibraryError
from app.services.productions import DISCOVERY_SENTENCE_PROMPT, record_written_production
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
    guess: str | None = None,
    exercise_results: Sequence[DiscoveryExerciseResult] = (),
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
        DiscoveryCompleted(
            lexical_item_id=item.id,
            duration_ms=duration_ms,
            guess=guess,
            exercise_results=list(exercise_results),
        ),
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


# --- Discovery from the user's side (M4) ---------------------------------------------------------


class SheetRequired(LibraryError):
    code = "sheet_required"


class AlreadyDiscovered(LibraryError):
    code = "already_discovered"


def usable_sheet(session: Session, item_id: int) -> UsageSheet | None:
    """The current sheet if it can carry a discovery (D-092 content rule, not a skeleton)."""
    sheet = session.scalar(
        select(Enrichment).where(Enrichment.lexical_item_id == item_id, Enrichment.is_current)
    )
    if sheet is None or not is_usable(sheet.status, dict(sheet.content)):
        return None
    return read_sheet(dict(sheet.content))


def _has_cards(session: Session, item_id: int) -> bool:
    return bool(session.scalar(select(exists().where(Card.lexical_item_id == item_id))))


@dataclass(frozen=True)
class FirstSentence:
    text: str
    source: str  # origin | example


@dataclass(frozen=True)
class DiscoveryStart:
    item: LexicalItem
    resumed: bool
    sentence: FirstSentence | None


def begin_discovery(
    session: Session,
    item: LexicalItem,
    via_deck: Deck | None,
    at: datetime,
    *,
    study_session_id: int,
) -> DiscoveryStart:
    """Step 1: the term goes to `discovering` (unless it already is) and the first sentence is
    returned: the original one, else the sheet's first example. Never the sheet itself."""
    if _has_cards(session, item.id):
        raise AlreadyDiscovered(f"Term {item.id} was already discovered.")
    sheet = usable_sheet(session, item.id)
    if sheet is None:
        raise SheetRequired(
            "This term needs a usage sheet before its discovery: generate one or type it."
        )
    resumed = item.status == ItemStatus.DISCOVERING
    if not resumed:
        start_discovery(session, item, via_deck, at, study_session_id=study_session_id)
    if item.origin_sentence and item.origin_sentence.strip():
        sentence = FirstSentence(item.origin_sentence, "origin")
    elif sheet.examples:
        sentence = FirstSentence(sheet.examples[0].sentence, "example")
    else:
        sentence = None
    return DiscoveryStart(item=item, resumed=resumed, sentence=sentence)


@dataclass(frozen=True)
class DiscoveryEnd:
    cards: tuple[Card, Card]
    production_attempt_id: int | None
    warnings: list[str]


def finish_discovery(
    session: Session,
    item: LexicalItem,
    at: datetime,
    *,
    study_session_id: int,
    duration_ms: int | None,
    guess: str | None,
    exercise_results: Sequence[DiscoveryExerciseResult],
    personal_sentence: str | None,
    engine_factory: EngineFactory = default_engine_factory,
) -> DiscoveryEnd:
    """Steps 2 to 5: the cards are created **without initial ratings** (they stay `new`, due at
    the start of the next study day); the personal sentence becomes a production attempt."""
    if _has_cards(session, item.id):
        raise AlreadyDiscovered(f"Term {item.id} was already discovered.")
    cards = complete_discovery(
        session,
        item,
        at,
        None,
        duration_ms,
        study_session_id=study_session_id,
        engine_factory=engine_factory,
        guess=guess,
        exercise_results=exercise_results,
    )
    warnings: list[str] = []
    attempt_id = None
    if personal_sentence is not None and personal_sentence.strip():
        forms = [
            form
            for template in session.scalars(
                select(ExerciseTemplate).where(
                    ExerciseTemplate.lexical_item_id == item.id,
                    ExerciseTemplate.exercise_type == ex.GAP_FILL,
                )
            )
            for form in (template.content.get("answer", ""), *template.content.get("accepted", []))
            if form
        ]
        used = ex.contains_term(item.term, personal_sentence, forms)
        if not used:
            warnings.append(GradeWarning.TERM_MISSING.value)
        attempt = record_written_production(
            session,
            text=personal_sentence.strip(),
            prompt=DISCOVERY_SENTENCE_PROMPT,
            targets={item.id: used},
            at=at,
            study_session_id=study_session_id,
        )
        attempt_id = attempt.id
    return DiscoveryEnd(cards=cards, production_attempt_id=attempt_id, warnings=warnings)
