from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    Card,
    DeckItem,
    Enrichment,
    ErrorEvent,
    EventLog,
    ExerciseTemplate,
    ReviewLog,
)
from app.domain.enums import CardDirection, ContentOrigin, ErrorSource, ItemType
from app.domain.events import ItemCreated, ItemOrigin
from tests.factories import add_card, add_category, add_deck, add_item, add_review, link


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_deleting_an_item_cascades_but_keeps_errors_and_events(session: Session) -> None:
    item = add_item(session)
    link(session, add_deck(session), item)
    review = add_review(session, add_card(session, item, CardDirection.RECEPTIVE))
    add_card(session, item, CardDirection.PRODUCTIVE)
    session.add_all(
        [
            Enrichment(lexical_item_id=item.id, content={}, schema_version=1),
            ExerciseTemplate(
                lexical_item_id=item.id,
                exercise_type="gap_fill",
                content={},
                origin=ContentOrigin.DEMO,
            ),
        ]
    )
    error = ErrorEvent(
        source=ErrorSource.MANUAL,
        erroneous_text="in university",
        correction="at university",
        category_id=add_category(session).id,
        lexical_item_id=item.id,
        review_log_id=None,
    )
    session.add(error)
    record_event(
        session,
        ItemCreated(lexical_item_id=item.id, item_type=ItemType.WORD, origin=ItemOrigin.QUICK_ADD),
    )
    session.commit()
    assert review.id is not None

    session.delete(item)
    session.commit()
    session.expire_all()

    for model in (Card, ReviewLog, Enrichment, ExerciseTemplate, DeckItem):
        assert _count(session, model) == 0, model.__name__
    assert session.get(ErrorEvent, error.id) is not None
    assert session.get(ErrorEvent, error.id).lexical_item_id is None  # type: ignore[union-attr]
    assert _count(session, EventLog) == 1
