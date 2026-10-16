"""Foreign keys, CHECK and UNIQUE constraints, enforced by the database itself."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Card, Enrichment, ErrorEvent, ProductionAttempt
from app.domain.enums import CardDirection, ErrorSource, Modality, ProductionKind
from tests.factories import NOW, add_card, add_category, add_deck, add_item, add_review, link


def test_card_with_unknown_item_is_refused(session: Session) -> None:
    session.add(Card(lexical_item_id=9999, direction=CardDirection.RECEPTIVE, due=NOW))
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.flush()


def test_invalid_deck_status_is_refused_by_check(session: Session) -> None:
    # Raw SQL: the ORM Enum would already refuse the value before it reaches the database.
    with pytest.raises(IntegrityError, match="CHECK constraint failed: ck_deck_deck_status"):
        session.execute(
            text(
                "INSERT INTO deck (name, kind, status, priority, created_at, updated_at) "
                "VALUES ('x', 'custom', 'archived', 0, '2026-10-16', '2026-10-16')"
            )
        )


def test_rating_5_is_refused(session: Session) -> None:
    card = add_card(session, add_item(session))
    with pytest.raises(IntegrityError, match="final_rating_range"):
        add_review(session, card, final_rating=5)


def test_error_event_cannot_point_to_attempt_and_review(session: Session) -> None:
    card = add_card(session, add_item(session))
    review = add_review(session, card)
    attempt = ProductionAttempt(kind=ProductionKind.WRITING, modality=Modality.WRITTEN, text="x")
    session.add(attempt)
    session.flush()
    session.add(
        ErrorEvent(
            production_attempt_id=attempt.id,
            review_log_id=review.id,
            source=ErrorSource.WRITING,
            erroneous_text="in campus",
            correction="on campus",
            category_id=add_category(session).id,
        )
    )
    with pytest.raises(IntegrityError, match="single_origin"):
        session.flush()


def test_two_productive_cards_for_one_item_are_refused(session: Session) -> None:
    item = add_item(session)
    add_card(session, item, CardDirection.PRODUCTIVE)
    add_card(session, item, CardDirection.RECEPTIVE)
    with pytest.raises(IntegrityError, match="UNIQUE"):
        add_card(session, item, CardDirection.PRODUCTIVE)


def _enrichment(item_id: int, *, is_current: bool) -> Enrichment:
    return Enrichment(
        lexical_item_id=item_id,
        content={"definition": "x"},
        schema_version=1,
        is_current=is_current,
    )


def test_only_one_current_enrichment_per_item(session: Session) -> None:
    item = add_item(session)
    session.add_all(
        [_enrichment(item.id, is_current=False), _enrichment(item.id, is_current=False)]
    )
    session.add(_enrichment(item.id, is_current=True))
    session.flush()  # history rows are accepted
    session.add(_enrichment(item.id, is_current=True))
    with pytest.raises(IntegrityError, match="UNIQUE"):
        session.flush()


def test_same_item_in_two_decks_keeps_one_pair_of_cards(session: Session) -> None:
    item = add_item(session)
    link(session, add_deck(session, "Deck one"), item)
    link(session, add_deck(session, "Deck two"), item)
    add_card(session, item, CardDirection.RECEPTIVE)
    add_card(session, item, CardDirection.PRODUCTIVE)
    count = session.execute(
        text("SELECT COUNT(*) FROM card WHERE lexical_item_id = :id"), {"id": item.id}
    ).scalar()
    assert count == 2


def test_same_item_twice_in_one_deck_is_refused(session: Session) -> None:
    item = add_item(session)
    deck = add_deck(session)
    link(session, deck, item)
    with pytest.raises(IntegrityError, match="UNIQUE"):
        link(session, deck, item)


def test_event_log_is_append_only(session: Session) -> None:
    session.execute(
        text(
            "INSERT INTO event_log (occurred_at, recorded_at, event_type, entity_type, payload, "
            "payload_version) VALUES ('2026-10-16', '2026-10-16', 't', 'x', '{}', 1)"
        )
    )
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text("UPDATE event_log SET event_type = 'changed'"))
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text("DELETE FROM event_log"))
