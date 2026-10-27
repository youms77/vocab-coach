"""`/api/stats/progress`, `/practice`, `/ai`, `/overview` on a hand-built database (M9.a2).

A read writes nothing: every table is counted before and after.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import AICallLog, ProductionAttempt, StudySession
from app.domain.enums import ItemStatus, ItemType, Modality, ProductionKind
from app.domain.events import ItemCreated, ItemOrigin, ItemStatusChanged
from tests.stats_support import DAY, add_sample, counts, make_client


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with make_client(engine) as test_client:
        yield test_client


@pytest.fixture
def data(engine: Engine) -> None:
    add_sample(engine)
    with Session(engine) as session:
        # The sample's term (id 1) was created without events; give term 2 a full life.
        record_event(
            session,
            ItemCreated(lexical_item_id=2, item_type=ItemType.WORD, origin=ItemOrigin.QUICK_ADD),
            occurred_at=DAY - timedelta(days=3),
        )
        record_event(
            session,
            ItemStatusChanged(
                lexical_item_id=2, from_status=ItemStatus.DRAFT, to_status=ItemStatus.QUEUED
            ),
            occurred_at=DAY - timedelta(days=2),
        )
        speech = ProductionAttempt(
            kind=ProductionKind.SHADOWING, modality=Modality.ORAL, text="...", word_count=0,
            audio_path="shadowing/1.webm", audio_seconds=12.5, created_at=DAY, updated_at=DAY,
        )  # fmt: skip
        session.add(speech)
        session.add(StudySession(started_at=DAY, ended_at=DAY + timedelta(minutes=25)))
        for success, code in ((True, None), (False, "rate_limited"), (False, "quota_exhausted")):
            session.add(
                AICallLog(
                    started_at=DAY,
                    provider="gemini",
                    model="gemini-test",
                    task="enrichment",
                    input_tokens=100,
                    output_tokens=50,
                    duration_ms=1000,
                    success=success,
                    error_code=code,
                    attempt=1,
                )  # fmt: skip
            )
        session.commit()


@pytest.mark.usefixtures("data")
def test_progress(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/progress", params={"from": "2026-08-16", "to": "2026-08-20"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["funnel_order"] == ["queued", "discovering", "learning", "consolidated", "active"]
    assert body["snapshot"]["learning"] == 1
    assert sum(body["snapshot"].values()) == 1
    # Term 1 has a status change (learning -> consolidated) and no creation event.
    last = body["rebuilt"][-1]["counts"]
    assert (last["consolidated"], last["queued"]) == (1, 1)
    assert [b["counts"]["draft"] for b in body["rebuilt"]] == [0, 1, 0, 0, 0]
    assert len(body["forecast"]) == 14
    assert {t["code"] for t in body["tracks"]} >= {"general_everyday", "speaking_scenarios"}
    assert counts(engine) == before


@pytest.mark.usefixtures("data")
def test_practice(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/practice", params={"from": "2026-08-20", "to": "2026-08-21"})
    assert answer.status_code == 200
    body = answer.json()
    day = body["study_time"]["buckets"][0]
    # 10 reviews, 3 productions and the events at the same instant: one block of 60 s.
    assert (day["seconds"], day["blocks"], day["session_seconds"]) == (60.0, 1, 1500.0)
    assert body["words_written"] == 600 and body["words_oral"] == 0
    assert body["speech_seconds"] == 12.5 and body["speech_by_kind"] == {"shadowing": 12.5}
    # Only 2026-08-20 has actions (a creation or a move to `queued` is not one).
    assert (body["streaks"]["longest"], body["streaks"]["current"]) == (1, 0)
    assert counts(engine) == before


@pytest.mark.usefixtures("data")
def test_ai(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/ai", params={"from": "2026-08-20", "to": "2026-08-20"})
    assert answer.status_code == 200
    body = answer.json()
    gemini = body["days"][0]["providers"][0]
    assert (gemini["provider"], gemini["requests"], gemini["successes"]) == ("gemini", 3, 1)
    assert (gemini["rate_limited"], gemini["quota_exhausted"]) == (1, 1)
    assert (gemini["input_tokens"], gemini["avg_duration_ms"]) == (300, 1000.0)
    assert body["totals"][0]["requests"] == 3
    assert set(body["azure_month"]) == {"month", "audio_seconds", "assessments"}
    text = answer.text.lower()
    assert "key" not in text and "prompt" not in text
    assert counts(engine) == before


@pytest.mark.usefixtures("data")
def test_overview(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/overview")
    assert answer.status_code == 200
    body = answer.json()
    assert body["study_day"] == "2026-09-01"
    assert body["error_rate_last_28"]["errors"] == 3 and body["error_rate_last_28"]["words"] == 600
    assert body["retention_last_28"]["n"] == 10 and body["current_target"] == 0.85
    assert body["active_terms"] == {"value": 0, "n": 1}
    assert body["current_streak"]["value"] == 0
    assert body["study_minutes_last_7"] == 0
    assert body["reviews_due_tomorrow"]["value"] >= 0
    assert counts(engine) == before


@pytest.mark.parametrize("route", ["/api/stats/progress", "/api/stats/practice", "/api/stats/ai"])
def test_bad_periods_are_422(client: TestClient, route: str) -> None:
    for params in ({"from": "2026-09-02", "to": "2026-09-01"}, {"granularity": "year"}):
        answer = client.get(route, params=params)
        assert answer.status_code == 422
        assert answer.json()["detail"]["code"] == "invalid_request"


def test_empty_database(client: TestClient) -> None:
    for route in ("progress", "practice", "ai", "overview"):
        assert client.get(f"/api/stats/{route}").status_code == 200, route
