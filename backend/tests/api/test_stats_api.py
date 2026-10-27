"""`/api/stats/errors` and `/api/stats/memory` on a hand-built database (M9.a).

A read writes nothing: every table is counted before and after, as in the `grade` tests.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.db.models import ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from app.domain.enums import Modality, ProductionKind
from tests.stats_support import add_sample, counts, make_client


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with make_client(engine) as test_client:
        yield test_client


@pytest.fixture
def data(engine: Engine) -> None:
    add_sample(engine)


@pytest.mark.usefixtures("data")
def test_error_stats(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/errors", params={"from": "2026-08-20", "to": "2026-08-21"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["from"] == "2026-08-20" and body["to"] == "2026-08-21"
    assert (body["study_day"], body["granularity"], body["demo"]) == ("2026-09-01", "day", False)
    assert "computed_at" in body
    rates = body["rates"]
    assert rates["rate"] == {"value": 0.5, "errors": 3, "words": 600, "insufficient": False}
    assert rates["unnormalized"]["by_reason"]["drill"] == 1
    assert [b["key"] for b in rates["buckets"]] == ["2026-08-20", "2026-08-21"]
    assert rates["buckets"][1]["rate"] == {
        "value": None,
        "errors": 0,
        "words": 0,
        "insufficient": True,
    }
    assert rates["level2"] == [{"code": "grammar.preposition", "level": 2, "rate": rates["rate"]}]
    top = body["top_recurring"]
    assert [(t["erroneous_text"], t["count"], t["has_card"]) for t in top] == [
        ("in campus", 2, False)
    ]
    assert set(body["trends"]["by_status"]) == {"declining", "rising", "stable", "insufficient"}
    assert counts(engine) == before


@pytest.mark.usefixtures("data")
def test_memory_stats(client: TestClient, engine: Engine) -> None:
    before = counts(engine)
    answer = client.get("/api/stats/memory", params={"from": "2026-08-01", "granularity": "week"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["retention"]["all"] == {
        "value": 0.9,
        "successes": 9,
        "n": 10,
        "insufficient": False,
    }
    assert body["retention"]["target"] == 0.85
    assert body["default_target"] == 0.9
    assert body["lapses"]["total"] == 1
    assert body["top_lapsed_terms"] == [{"item_id": 1, "term": "hinge on", "lapses": 1}]
    assert body["retention"]["buckets"][0]["key"] == "2026-07-27"  # Monday of the first week
    # Consolidated, but its discovery is unknown: not counted.
    assert body["time_to_consolidation"]["n"] == 0
    assert counts(engine) == before


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-09-02", "to": "2026-09-01"},
        {"from": "2025-08-30", "to": "2026-09-01"},  # 368 days
        {"from": "not-a-date"},
        {"granularity": "month"},
    ],
)
@pytest.mark.parametrize("route", ["/api/stats/errors", "/api/stats/memory"])
def test_bad_parameters_are_422(client: TestClient, route: str, params: dict[str, str]) -> None:
    answer = client.get(route, params=params)
    assert answer.status_code == 422
    assert answer.json()["detail"]["code"] == "invalid_request"


def test_an_empty_database_answers(client: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        sync_taxonomy(session)
        session.commit()
    for route in ("/api/stats/errors", "/api/stats/memory"):
        assert client.get(route).status_code == 200


def test_the_connection_is_writable_again_after_a_read(client: TestClient, engine: Engine) -> None:
    assert client.get("/api/stats/memory").status_code == 200
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA query_only")).scalar() == 0


@pytest.mark.usefixtures("data")
def test_a_production_at_0330_in_douala_counts_for_the_previous_study_day(
    client: TestClient, engine: Engine
) -> None:
    late = datetime(2026, 8, 21, 2, 30, tzinfo=UTC)  # 03:30 in Douala: study day 2026-08-20
    with Session(engine) as session:
        session.add(
            ProductionAttempt(
                kind=ProductionKind.WRITING,
                modality=Modality.WRITTEN,
                text="...",
                word_count=100,
                created_at=late,
                updated_at=late,
            )  # fmt: skip
        )
        session.commit()
    body = client.get("/api/stats/errors", params={"from": "2026-08-20", "to": "2026-08-21"})
    words = {b["key"]: b["rate"]["words"] for b in body.json()["rates"]["buckets"]}
    assert words == {"2026-08-20": 700, "2026-08-21": 0}
