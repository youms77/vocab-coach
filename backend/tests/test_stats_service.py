"""The statistics service reads every payload version (M9.a): a missing field, a malformed value or
an id that no longer exists is skipped, never an error."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import EventLog, ProductionAttempt
from app.domain.enums import ItemStatus, Modality, ProductionKind
from app.services import stats
from tests.factories import add_item

NOW = datetime(2026, 9, 1, 10, tzinfo=UTC)
PASTED = datetime(2026, 8, 21, 18, tzinfo=UTC)  # study day 2026-08-21


def raw_event(
    session: Session, event_type: str, payload: dict[str, Any], version: int, at: datetime
) -> None:
    """An event row as an old version wrote it (no validation by the current models)."""
    session.add(
        EventLog(
            occurred_at=at,
            recorded_at=at,
            event_type=event_type,
            entity_type="test",
            entity_id=None,
            payload=payload,
            payload_version=version,
        )  # fmt: skip
    )


def transcript(session: Session, words: int) -> int:
    attempt = ProductionAttempt(
        kind=ProductionKind.TRANSCRIPT_ANALYSIS, modality=Modality.ORAL, text="...",
        word_count=words, created_at=PASTED, updated_at=PASTED,
    )  # fmt: skip
    session.add(attempt)
    session.flush()
    return attempt.id


def test_old_and_odd_payloads_are_read(engine: Engine) -> None:
    with Session(engine) as session:
        v1 = transcript(session, 200)  # production.recorded v1: no `occurred_on`
        v3 = transcript(session, 300)  # v3 with the day of the conversation
        odd = transcript(session, 400)  # a value that is not a date
        raw_event(session, "production.recorded",
                  {"production_attempt_id": v1, "kind": "transcript_analysis", "modality": "oral",
                   "word_count": 200}, 1, PASTED)  # fmt: skip
        raw_event(session, "production.recorded",
                  {"production_attempt_id": v3, "kind": "transcript_analysis", "modality": "oral",
                   "word_count": 300, "occurred_on": "2026-08-18"}, 3, PASTED)  # fmt: skip
        raw_event(session, "production.recorded",
                  {"production_attempt_id": odd, "occurred_on": "a week ago"}, 3,
                  PASTED)  # fmt: skip
        raw_event(session, "production.recorded", {}, 1, PASTED)  # nothing at all

        item_id = add_item(session, "hinge on", ItemStatus.CONSOLIDATED).id
        found = datetime(2026, 8, 10, 18, tzinfo=UTC)
        raw_event(session, "discovery.completed", {"lexical_item_id": item_id}, 1, found)
        raw_event(session, "item.status_changed",
                  {"lexical_item_id": item_id, "from_status": "learning",
                   "to_status": "consolidated"}, 1, PASTED)  # fmt: skip
        # A term merged or deleted since: its events stay, nothing else exists.
        raw_event(session, "item.status_changed",
                  {"lexical_item_id": 999, "from_status": "learning",
                   "to_status": "consolidated"}, 1, PASTED)  # fmt: skip
        raw_event(session, "discovery.completed", {"lexical_item_id": 999}, 1, found)
        raw_event(session, "setting.changed",
                  {"key": "target_retention", "old_value": 0.9, "new_value": "0.8"}, 1,
                  found)  # fmt: skip
        raw_event(session, "setting.changed", {"key": "target_retention"}, 1, found)
        session.commit()

    with stats.read_only(engine) as session:
        days = stats.transcript_days(session)
        assert days == {v3: date(2026, 8, 18)}
        words = {p.production_id: p.occurred_on for p in stats.load_productions(session)}
        assert words == {v1: None, v3: date(2026, 8, 18), odd: None}
        assert stats.retention_changes(session) == []

        errors = stats.error_stats(session, NOW, date(2026, 8, 1), date(2026, 9, 1))
        by_day = {b.key: b.rate.words for b in errors.rates.buckets if b.rate.words}
        assert by_day == {date(2026, 8, 18): 300, date(2026, 8, 21): 600}

        memory = stats.memory_stats(session, NOW, date(2026, 8, 1), date(2026, 9, 1))
        delays = memory.time_to_consolidation
        # Item 999 has a discovery and a consolidation but no row: it still counts (11 days).
        assert [(d.item_id, d.days) for d in delays.items] == [(item_id, 11), (999, 11)]
