from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Deck, EventLog
from app.domain.enums import CardDirection, DeckKind, DeckStatus
from app.domain.events import (
    EVENT_MODELS,
    CardReviewed,
    DeckCreated,
    DeckStatusChanged,
    EventType,
    SettingChanged,
    parse_event,
)


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(EventLog)) or 0


def test_every_event_type_has_a_payload_model() -> None:
    assert set(EVENT_MODELS) == set(EventType)


def test_record_event_writes_a_validated_row(session: Session) -> None:
    occurred = datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    row = record_event(
        session,
        DeckStatusChanged(deck_id=3, from_status=DeckStatus.QUEUED, to_status=DeckStatus.ACTIVE),
        occurred_at=occurred,
    )
    session.commit()

    assert row.event_type == "deck.status_changed"
    assert (row.entity_type, row.entity_id, row.payload_version) == ("deck", 3, 1)
    assert row.payload == {"deck_id": 3, "from_status": "queued", "to_status": "active"}
    assert row.occurred_at == occurred  # backdated business date
    assert row.recorded_at > occurred
    assert parse_event(row.event_type, row.payload) == DeckStatusChanged(
        deck_id=3, from_status=DeckStatus.QUEUED, to_status=DeckStatus.ACTIVE
    )


def test_invalid_payload_is_refused() -> None:
    with pytest.raises(ValidationError):
        CardReviewed(
            card_id=1,
            review_log_id=1,
            lexical_item_id=1,
            direction=CardDirection.PRODUCTIVE,
            exercise_type="typed_recall",
            final_rating=5,
        )


def test_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        DeckCreated(deck_id=1, kind=DeckKind.CUSTOM, status=DeckStatus.QUEUED, colour="red")  # type: ignore[call-arg]


def test_record_event_revalidates_unchecked_instances(session: Session) -> None:
    bypassed = DeckCreated.model_construct(deck_id=0, kind="custom", status="nonsense")
    with pytest.raises(ValidationError):
        record_event(session, bypassed)
    assert _count(session) == 0


def test_setting_changed_refuses_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="secrets never go to the event log"):
        SettingChanged(key="groq_api_key", old_value=None, new_value="sk-not-a-real-key")


def test_rollback_leaves_no_event(session: Session) -> None:
    deck = Deck(name="Fictional deck")
    session.add(deck)
    session.flush()
    record_event(session, DeckCreated(deck_id=deck.id, kind=deck.kind, status=deck.status))
    session.flush()
    assert _count(session) == 1

    session.rollback()

    assert _count(session) == 0
    assert session.scalar(select(func.count()).select_from(Deck)) == 0
