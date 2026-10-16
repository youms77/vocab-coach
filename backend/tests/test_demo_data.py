"""The generated demo database: coverage, integrity and the plan at the anchor (D-033, D-034).

One full 60-day seed is built per test session and shared (read-only) by these tests.
"""

from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.engine import create_db_engine
from app.db.models import (
    Card,
    Deck,
    DeckItem,
    ErrorCategory,
    ErrorEvent,
    EventLog,
    LexicalItem,
    ProductionAttempt,
    ReviewLog,
    StudySession,
)
from app.db.taxonomy import load_taxonomy
from app.demo.dataset import load_dataset
from app.demo.seed import seed_demo, sqlite_url
from app.domain.enums import (
    CardDirection,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    SrsState,
)
from app.domain.events import EventType
from app.domain.planner import BlockKind
from app.domain.study_day import study_day_bounds
from app.services.planning import plan_today
from tests.demo_support import DEMO_ANCHOR, DEMO_SEED

DOUALA = ZoneInfo("Africa/Douala")
ANCHOR_START, _ = study_day_bounds(DEMO_ANCHOR, DOUALA, 4)
PRODUCTION_SOURCES = (ErrorSource.WRITING, ErrorSource.SPEAKING, ErrorSource.TRANSCRIPT)


@pytest.fixture(scope="module")
def demo_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    path: Path = tmp_path_factory.mktemp("demo") / "vocab-coach-demo.sqlite3"
    seed_demo(path, seed=DEMO_SEED, days=60, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()


@pytest.fixture
def db(demo_engine: Engine) -> Iterator[Session]:
    with Session(demo_engine) as session:
        yield session
        session.rollback()


def _events(db: Session, event_type: EventType) -> list[EventLog]:
    return list(db.scalars(select(EventLog).where(EventLog.event_type == event_type)))


# --- coverage --------------------------------------------------------------------------------


def test_every_deck_status_and_item_status_is_present(db: Session) -> None:
    assert set(db.scalars(select(Deck.status))) == set(DeckStatus)
    assert set(db.scalars(select(LexicalItem.status))) == set(ItemStatus)


def test_new_learning_review_and_relearning_cards_are_present(db: Session) -> None:
    assert set(db.scalars(select(Card.srs_state))) == set(SrsState)


def test_decks_tell_the_planned_story(db: Session) -> None:
    decks = {deck.name: deck for deck in db.scalars(select(Deck))}
    statuses = defaultdict(Counter)
    for deck_id, status in db.execute(
        select(DeckItem.deck_id, LexicalItem.status).join(
            LexicalItem, LexicalItem.id == DeckItem.lexical_item_id
        )
    ):
        statuses[deck_id][status] += 1

    causal = statuses[decks["Causal inference reading"].id]
    assert causal[ItemStatus.QUEUED] == 0 and causal[ItemStatus.ACTIVE] in range(4, 7)
    assert statuses[decks["Thesis defence"].id][ItemStatus.QUEUED] == 0
    assert decks["Thesis defence"].status == DeckStatus.DONE
    campus = statuses[decks["Campus life"].id]
    assert decks["Campus life"].status == DeckStatus.PAUSED
    assert (
        campus[ItemStatus.QUEUED] > 0
        and campus[ItemStatus.LEARNING] + campus[ItemStatus.CONSOLIDATED] > 0
    )
    interview = decks["ML interview prep"]
    assert interview.status == DeckStatus.ACTIVE
    assert (interview.deadline - DEMO_ANCHOR).days == 18
    assert statuses[interview.id][ItemStatus.TRIAGE] > 0
    assert decks["Presenting results"].status == DeckStatus.QUEUED


def test_terms_shared_between_decks(db: Session) -> None:
    shared = db.scalars(
        select(DeckItem.lexical_item_id).group_by(DeckItem.lexical_item_id).having(func.count() > 1)
    ).all()
    assert 2 <= len(shared) <= 3


def test_one_interrupted_discovery_and_one_discovery_without_ratings(db: Session) -> None:
    assert db.scalar(select(func.count()).where(LexicalItem.status == ItemStatus.DISCOVERING)) == 1
    new_cards = db.scalars(select(Card).where(Card.srs_state == SrsState.NEW)).all()
    assert len(new_cards) == 2 and len({card.lexical_item_id for card in new_cards}) == 1


def test_at_least_ten_error_codes_with_prepositions_and_tenses_on_top(db: Session) -> None:
    codes = list(
        db.scalars(
            select(ErrorCategory.code).join(ErrorEvent, ErrorEvent.category_id == ErrorCategory.id)
        )
    )
    assert len(set(codes)) >= 10
    by_category = Counter(".".join(code.split(".")[:2]) for code in codes)
    top_two = {category for category, _ in by_category.most_common(2)}
    assert top_two == {"grammar.preposition", "grammar.tense"}


def test_fixed_expression_errors_decline_per_100_words(db: Session) -> None:
    """Rate over the last 30 days < rate over the first 30, from the event log only."""
    middle = DEMO_ANCHOR.toordinal() - 30
    words = Counter()
    errors = Counter()
    for event in _events(db, EventType.PRODUCTION_RECORDED):
        half = event.occurred_at.astimezone(DOUALA).date().toordinal() >= middle
        words[half] += event.payload["word_count"]
    for event in _events(db, EventType.ERROR_RECORDED):
        if event.payload["category_code"] != "grammar.preposition.fixed_expression":
            continue
        half = event.occurred_at.astimezone(DOUALA).date().toordinal() >= middle
        errors[half] += 1
    first, last = errors[False] / words[False] * 100, errors[True] / words[True] * 100
    assert last < first


def test_productions_have_word_counts_in_range(db: Session) -> None:
    attempts = db.scalars(select(ProductionAttempt)).all()
    assert len(attempts) >= 10
    for attempt in attempts:
        assert attempt.word_count == len(attempt.text.split())
        assert attempt.word_count >= 80


def test_lexical_errors_from_failed_reviews(db: Session) -> None:
    errors = db.scalars(select(ErrorEvent).where(ErrorEvent.source == ErrorSource.REVIEW)).all()
    assert 5 <= len(errors) <= 10
    for error in errors:
        review = db.get_one(ReviewLog, error.review_log_id)
        card = db.get_one(Card, review.card_id)
        assert review.final_rating == 1
        assert card.lexical_item_id == error.lexical_item_id
        assert card.direction == CardDirection.PRODUCTIVE


def test_most_causal_inference_productive_cards_are_stable(db: Session) -> None:
    deck_id = db.scalar(select(Deck.id).where(Deck.name == "Causal inference reading"))
    stabilities = db.scalars(
        select(Card.stability)
        .join(DeckItem, DeckItem.lexical_item_id == Card.lexical_item_id)
        .where(DeckItem.deck_id == deck_id, Card.direction == CardDirection.PRODUCTIVE)
    ).all()
    assert len(stabilities) >= 25
    assert sum((s or 0) >= 7 for s in stabilities) / len(stabilities) >= 0.8


def test_sessions_follow_the_calendar(db: Session) -> None:
    sessions = db.scalars(select(StudySession)).all()
    assert 40 <= len(sessions) <= 56  # about 85 % of 60 days, minus a 3-day break
    local_hours = Counter(s.started_at.astimezone(DOUALA).hour for s in sessions)
    assert sum(n for hour, n in local_hours.items() if hour < 4) >= 1  # after midnight
    assert all(s.ended_at is not None and s.ended_at >= s.started_at for s in sessions)
    assert all(s.planned["plan"]["blocks"] is not None for s in sessions)


# --- integrity -------------------------------------------------------------------------------


def test_no_review_before_its_term_was_discovered(db: Session) -> None:
    early = db.scalar(
        select(func.count())
        .select_from(ReviewLog)
        .join(Card, Card.id == ReviewLog.card_id)
        .join(LexicalItem, LexicalItem.id == Card.lexical_item_id)
        .where(ReviewLog.reviewed_at < LexicalItem.discovered_at)
    )
    assert early == 0


def test_review_log_is_increasing_per_card(db: Session) -> None:
    last: dict[int, datetime] = {}
    for card_id, reviewed_at in db.execute(
        select(ReviewLog.card_id, ReviewLog.reviewed_at).order_by(ReviewLog.id)
    ):
        assert reviewed_at >= last.get(card_id, reviewed_at)
        last[card_id] = reviewed_at


def test_nothing_happens_after_the_start_of_the_anchor_day(db: Session) -> None:
    for column in (
        EventLog.occurred_at,
        ReviewLog.reviewed_at,
        ErrorEvent.occurred_at,
        StudySession.ended_at,
    ):
        assert db.scalar(select(func.max(column))) < ANCHOR_START


def test_every_business_row_has_its_event(db: Session) -> None:
    def entity_ids(event_type: EventType) -> set[int]:
        return {event.entity_id for event in _events(db, event_type)}

    assert set(db.scalars(select(Deck.id))) <= entity_ids(EventType.DECK_CREATED)
    assert set(db.scalars(select(LexicalItem.id))) <= entity_ids(EventType.ITEM_CREATED)
    assert set(db.scalars(select(Card.id))) <= entity_ids(EventType.CARD_CREATED)
    reviewed = {e.payload["review_log_id"] for e in _events(db, EventType.CARD_REVIEWED)}
    assert set(db.scalars(select(ReviewLog.id))) == reviewed
    assert set(db.scalars(select(ProductionAttempt.id))) <= entity_ids(
        EventType.PRODUCTION_RECORDED
    )
    assert set(db.scalars(select(ErrorEvent.id))) <= entity_ids(EventType.ERROR_RECORDED)
    sessions = set(db.scalars(select(StudySession.id)))
    assert sessions <= entity_ids(EventType.SESSION_STARTED)
    assert sessions <= entity_ids(EventType.SESSION_ENDED)
    links = {
        (e.payload["deck_id"], e.payload["lexical_item_id"])
        for e in _events(db, EventType.DECK_ITEM_ADDED)
    }
    rows = db.execute(select(DeckItem.deck_id, DeckItem.lexical_item_id))
    assert {tuple(row) for row in rows} == links


def test_status_history_matches_current_statuses(db: Session) -> None:
    latest: dict[int, str] = {}
    for event in db.scalars(
        select(EventLog)
        .where(EventLog.event_type == EventType.ITEM_STATUS_CHANGED)
        .order_by(EventLog.occurred_at, EventLog.id)
    ):
        latest[event.entity_id] = event.payload["to_status"]
    for item in db.scalars(select(LexicalItem)):
        assert latest.get(item.id, ItemStatus.DRAFT) == item.status


def test_bank_codes_exist_in_the_taxonomy() -> None:
    load_dataset().check_codes(category.code for category in load_taxonomy().categories)


def test_no_duplicate_term_in_a_deck(db: Session) -> None:
    rows = db.execute(
        select(DeckItem.deck_id, LexicalItem.normalized_form).join(
            LexicalItem, LexicalItem.id == DeckItem.lexical_item_id
        )
    ).all()
    assert len(rows) == len(set(rows))


# --- plan at the anchor ----------------------------------------------------------------------


def test_plan_at_the_anchor_has_reviews_new_terms_and_the_deadline_pace(db: Session) -> None:
    now = datetime.combine(DEMO_ANCHOR, time(19, 0), tzinfo=DOUALA)
    plan = plan_today(db, now)
    reviews = plan.block(BlockKind.REVIEWS)
    new_items = plan.block(BlockKind.NEW_ITEMS)
    assert reviews is not None and reviews.entries
    assert new_items is not None and new_items.entries
    interview_id = db.scalar(select(Deck.id).where(Deck.name == "ML interview prep"))
    assert [pace.deck_id for pace in plan.deadline_paces] == [interview_id]
    assert "deadline_triage_pending" in {warning.code for warning in plan.warnings}
