"""Statistics on the demo database (seed 42, 60 days, anchor 2026-09-01), M9.a.

Every route answers 200 and the figures agree with the tables. The learner model of the demo
(D-034, `content/demo/errors.yaml`) is checked through the lasting trends: with the default
thresholds, `fixed_expression` (3.0 -> 1.0 errors per 100 words over 60 days) drops to 0.61 x its
earlier rate, which is `stable`, not `declining` (owner's decision, option A: the thresholds stay;
a dataset v8 with a steeper decline is proposed for later).
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.engine import create_db_engine
from app.db.models import ReviewLog
from app.demo.seed import seed_demo, sqlite_url
from app.domain.study_day import study_day_bounds
from tests.demo_support import DEMO_ANCHOR, DEMO_SEED
from tests.stats_support import counts, make_client

NOW = datetime(2026, 9, 1, 10, tzinfo=UTC)  # study day = the anchor
FROM = "2026-07-03"  # the 60 days of history and the anchor day


@pytest.fixture(scope="module")
def demo_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    path = tmp_path_factory.mktemp("demo-stats") / "vocab-coach-demo.sqlite3"
    seed_demo(path, seed=DEMO_SEED, days=60, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def client(demo_engine: Engine) -> Iterator[TestClient]:
    with make_client(demo_engine, NOW) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def errors(client: TestClient) -> dict:
    answer = client.get("/api/stats/errors", params={"from": FROM})
    assert answer.status_code == 200
    return answer.json()


@pytest.fixture(scope="module")
def memory(client: TestClient) -> dict:
    answer = client.get("/api/stats/memory", params={"from": FROM})
    assert answer.status_code == 200
    return answer.json()


def test_every_route_answers(client: TestClient, demo_engine: Engine) -> None:
    before = counts(demo_engine)
    for route in ("/api/stats/errors", "/api/stats/memory", "/api/export/csv"):
        for granularity in ("day", "week"):
            answer = client.get(route, params={"granularity": granularity})
            assert answer.status_code == 200, route
    assert client.get("/api/stats/errors").json()["demo"] is True
    assert counts(demo_engine) == before


def test_level_one_categories_add_up_to_the_total(errors: dict) -> None:
    rates = errors["rates"]
    assert rates["rate"]["errors"] > 0
    assert sum(c["rate"]["errors"] for c in rates["level1"]) == rates["rate"]["errors"]
    assert sum(c["rate"]["errors"] for c in rates["level2"]) == rates["rate"]["errors"]
    for bucket in rates["buckets"]:
        assert sum(c["rate"]["errors"] for c in bucket["level1"]) == bucket["rate"]["errors"]
    assert sum(b["rate"]["words"] for b in rates["buckets"]) == rates["rate"]["words"]


def _trends(errors: dict) -> dict[str, tuple[str, int, int, float | None]]:
    return {
        t["code"]: (status, t["window_a"]["errors"], t["window_b"]["errors"], t["ratio"])
        for status, group in errors["trends"]["by_status"].items()
        for t in group
    }


def test_the_three_witness_categories(errors: dict) -> None:
    trends = _trends(errors)
    assert (errors["trends"]["words_a"], errors["trends"]["words_b"]) == (1710, 1601)
    # Declines, but to 0.61 x the earlier rate: not "lasting decline" at DECLINE_RATIO = 0.5.
    assert trends["grammar.preposition.fixed_expression"] == ("stable", 42, 24, 0.610333)
    assert trends["grammar.tense.past_simple_vs_present_perfect"] == ("stable", 27, 30, 1.186758)
    assert trends["discourse"] == ("rising", 4, 6, 1.602124)


def test_the_number_of_reviews_equals_the_review_log_of_the_period(
    memory: dict, demo_engine: Engine
) -> None:
    with Session(demo_engine) as session:
        tz = ZoneInfo("Africa/Douala")
        start, _ = study_day_bounds(date(2026, 7, 3), tz, 4)
        _, end = study_day_bounds(DEMO_ANCHOR, tz, 4)
        in_period = select(func.count()).where(
            ReviewLog.reviewed_at >= start, ReviewLog.reviewed_at < end
        )
        total = session.scalar(in_period)
        reinforcements = session.scalar(
            in_period.where(ReviewLog.exercise_type == "consolidation_misuse")
        )
    by_type = sum(row["success"]["n"] for row in memory["success_by_exercise"])
    assert by_type + reinforcements == total
    assert sum(b["review_state_reviews"] for b in memory["lapses"]["buckets"]) <= total


def test_memory_figures_are_plausible(memory: dict) -> None:
    retention = memory["retention"]
    assert retention["target"] == 0.9
    assert 0.8 < retention["all"]["value"] < 0.95
    assert retention["all"]["n"] == (retention["receptive"]["n"] + retention["productive"]["n"])
    assert memory["time_to_consolidation"]["n"] > 0
    assert memory["lapses"]["total"] == sum(b["lapses"] for b in memory["lapses"]["buckets"])
