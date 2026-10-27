"""Shared data of the statistics and export tests (M9.a): a small hand-built database."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.api.clock import get_now
from app.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine
from app.db.event_log import record_event
from app.db.models import Card, ErrorCategory, ErrorEvent, ProductionAttempt, ReviewLog
from app.db.taxonomy import sync_taxonomy
from app.domain.enums import (
    CardDirection,
    ErrorSource,
    ItemStatus,
    Modality,
    ProductionKind,
    SrsState,
)
from app.domain.events import ItemStatusChanged, SettingChanged
from app.main import create_app
from tests.factories import add_item

NOW = datetime(2026, 9, 1, 10, tzinfo=UTC)  # study day 2026-09-01
DAY = datetime(2026, 8, 20, 18, tzinfo=UTC)  # study day 2026-08-20


@contextmanager
def make_client(engine: Engine, now: datetime = NOW) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_now] = lambda: now
    with TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}") as test_client:
        yield test_client


def _category(session: Session, code: str) -> int:
    return session.scalar(select(ErrorCategory.id).where(ErrorCategory.code == code))  # type: ignore[return-value]


def add_sample(engine: Engine) -> None:
    """600 words, 3 errors in writing, 1 drill error, 10 reviews in Review (9 successes)."""
    with Session(engine) as session:
        sync_taxonomy(session)
        writing = ProductionAttempt(
            kind=ProductionKind.WRITING, modality=Modality.WRITTEN, text="...", word_count=600,
            created_at=DAY, updated_at=DAY,
        )  # fmt: skip
        drill = ProductionAttempt(
            kind=ProductionKind.DRILL, modality=Modality.WRITTEN, text="...", word_count=0,
            created_at=DAY, updated_at=DAY,
        )  # fmt: skip
        session.add_all([writing, drill])
        session.flush()
        fixed = _category(session, "grammar.preposition.fixed_expression")
        for wrong in ("in campus", "in campus", "by purpose"):
            session.add(
                ErrorEvent(
                    production_attempt_id=writing.id,
                    source=ErrorSource.WRITING,
                    original_text=f"I did it {wrong}.",
                    erroneous_text=wrong,
                    correction="on campus" if wrong == "in campus" else "on purpose",
                    category_id=fixed,
                    occurred_at=DAY,
                )  # fmt: skip
            )
        session.add(
            ErrorEvent(
                production_attempt_id=drill.id,
                source=ErrorSource.DRILL,
                erroneous_text="the",
                correction="a",
                category_id=_category(session, "grammar.article"),
                occurred_at=DAY,
            )  # fmt: skip
        )
        item = add_item(session, "hinge on", ItemStatus.LEARNING)
        card = Card(lexical_item_id=item.id, direction=CardDirection.PRODUCTIVE, due=NOW)
        session.add(card)
        session.flush()
        for rating in [3] * 9 + [1]:
            session.add(
                ReviewLog(
                    card_id=card.id,
                    reviewed_at=DAY,
                    exercise_type="typed_recall",
                    final_rating=rating,
                    state_before=SrsState.REVIEW,
                    state_after=SrsState.REVIEW,
                    due_after=NOW,
                    scheduled_days=3.0,
                    srs_algorithm="test",
                    retrievability=0.9,
                )  # fmt: skip
            )
        record_event(
            session,
            ItemStatusChanged(
                lexical_item_id=item.id,
                from_status=ItemStatus.LEARNING,
                to_status=ItemStatus.CONSOLIDATED,
            ),  # fmt: skip
            occurred_at=DAY,
        )
        record_event(
            session,
            SettingChanged(key="target_retention", old_value=0.9, new_value=0.85),
            occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        session.commit()


def counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
        }
