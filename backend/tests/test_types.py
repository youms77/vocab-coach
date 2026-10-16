from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.db.models import Deck, StudySession


def test_utc_datetime_round_trip_returns_aware_utc(session: Session) -> None:
    douala = timezone(timedelta(hours=1))
    started = datetime(2026, 10, 16, 9, 30, tzinfo=douala)
    study = StudySession(started_at=started)
    session.add(study)
    session.commit()
    session.expire_all()

    loaded = session.get(StudySession, study.id)
    assert loaded is not None
    assert loaded.started_at.tzinfo is UTC
    assert loaded.started_at == datetime(2026, 10, 16, 8, 30, tzinfo=UTC)
    assert loaded.created_at.tzinfo is UTC


def test_naive_datetime_is_refused(session: Session) -> None:
    session.add(StudySession(started_at=datetime(2026, 10, 16, 9, 30)))  # noqa: DTZ001
    with pytest.raises(StatementError, match="Naive datetime refused"):
        session.flush()


def test_json_column_tracks_top_level_changes(session: Session) -> None:
    study = StudySession(planned={"reviews": 10})
    session.add(study)
    session.commit()

    study.planned["new_items"] = 5  # in-place change, tracked by MutableDict
    session.commit()
    session.expire_all()
    assert session.get(StudySession, study.id).planned == {"reviews": 10, "new_items": 5}  # type: ignore[union-attr]


def test_closed_enum_refuses_unknown_value_in_python(session: Session) -> None:
    session.add(Deck(name="x", status="archived"))
    with pytest.raises(StatementError):
        session.flush()
