"""Small builders for database tests (fictional data only)."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Card, Deck, DeckItem, Enrichment, ErrorCategory, LexicalItem, ReviewLog
from app.domain.enums import CardDirection, EnrichmentStatus, ItemStatus, SrsState
from app.domain.usage_sheet import SCHEMA_VERSION, skeleton_sheet

NOW = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)


def add_item(
    session: Session, term: str = "shed light on", status: ItemStatus = ItemStatus.DRAFT
) -> LexicalItem:
    item = LexicalItem(term=term, normalized_form=term.lower(), status=status)
    session.add(item)
    session.flush()
    return item


def add_sheet(
    session: Session, item: LexicalItem, *, usable: bool = True, is_current: bool = True
) -> Enrichment:
    """A hand-typed sheet (French translation only), or a `needs_completion` skeleton."""
    sheet = Enrichment(
        lexical_item_id=item.id,
        content=(
            {"schema_version": SCHEMA_VERSION, "translation_fr": ["terme fictif"]}
            if usable
            else skeleton_sheet()
        ),
        schema_version=SCHEMA_VERSION,
        status=EnrichmentStatus.COMPLETE if usable else EnrichmentStatus.NEEDS_COMPLETION,
        is_current=is_current,
    )
    session.add(sheet)
    session.flush()
    return sheet


def add_deck(session: Session, name: str = "Causal inference reading") -> Deck:
    deck = Deck(name=name)
    session.add(deck)
    session.flush()
    return deck


def link(session: Session, deck: Deck, item: LexicalItem) -> DeckItem:
    deck_item = DeckItem(deck_id=deck.id, lexical_item_id=item.id)
    session.add(deck_item)
    session.flush()
    return deck_item


def add_card(
    session: Session, item: LexicalItem, direction: CardDirection = CardDirection.PRODUCTIVE
) -> Card:
    card = Card(lexical_item_id=item.id, direction=direction, due=NOW)
    session.add(card)
    session.flush()
    return card


def add_review(session: Session, card: Card, final_rating: int = 3) -> ReviewLog:
    review = ReviewLog(
        card_id=card.id,
        reviewed_at=NOW,
        exercise_type="typed_recall",
        final_rating=final_rating,
        state_before=SrsState.NEW,
        state_after=SrsState.LEARNING,
        due_after=NOW,
        scheduled_days=0.0,
        srs_algorithm="test",
    )
    session.add(review)
    session.flush()
    return review


def add_category(session: Session, code: str = "test.category") -> ErrorCategory:
    category = ErrorCategory(code=code, label_en=code, label_fr=code)
    session.add(category)
    session.flush()
    return category
