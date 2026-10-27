"""Route timings on a demo database (M10.b, method of D-278). Not part of the application.

Run from `backend/` against a TEMPORARY data directory, never against `data/`:

    $env:VOCAB_DATA_DIR = "$env:TEMP\\vc-perf"
    uv run python -m app demo seed --reset --days 365 --seed 42 --anchor 2026-10-27
    uv run python ..\\scripts\\measure_performance.py 2026-10-27

In-process `TestClient`, `now` = the anchor at noon, one first call (cold), then the median of five
warm calls. Prints one line per route: first call and median, in milliseconds.
"""

import os
import statistics
import sys
import time
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

anchor = date.fromisoformat(sys.argv[1])
data_dir = os.environ.get("VOCAB_DATA_DIR", "")
if not data_dir or os.path.abspath(data_dir).lower().endswith(os.path.join("vocab-coach", "data")):
    sys.exit("Set VOCAB_DATA_DIR to a temporary folder first.")
os.environ["VOCAB_DEMO"] = "1"

from app.api.clock import get_now  # noqa: E402
from app.main import create_app  # noqa: E402

NOW = datetime(anchor.year, anchor.month, anchor.day, 12, 0, tzinfo=UTC)
app = create_app()
app.dependency_overrides[get_now] = lambda: NOW
client = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})


def timed(method: str, url: str, **kwargs: object) -> tuple[float, object]:
    start = time.perf_counter()
    response = client.request(method, url, **kwargs)
    elapsed = (time.perf_counter() - start) * 1000
    assert response.status_code < 400, (method, url, response.status_code, response.text[:200])
    return elapsed, response


def measure(label: str, method: str, url: str, **kwargs: object) -> None:
    first, _ = timed(method, url, **kwargs)
    warm = [timed(method, url, **kwargs)[0] for _ in range(5)]
    print(f"{label:<46} first {first:7.1f} ms   median {statistics.median(warm):7.1f} ms")


first_day = date.fromordinal(anchor.toordinal() - 365).isoformat()
measure("GET /api/session/today", "GET", "/api/session/today")
_, started = timed("POST", "/api/session/start")
session_id = started.json()["id"]
measure("POST /api/session/start (already open)", "POST", "/api/session/start")
measure("GET /api/session/{id}/next", "GET", f"/api/session/{session_id}/next")
step = client.get(f"/api/session/{session_id}/next").json()
print("   next step kind:", step.get("kind"), "| keys:", sorted(step)[:8])
measure("GET /api/items (first page)", "GET", "/api/items")
measure("GET /api/items?q=the (search)", "GET", "/api/items", params={"q": "the"})
measure("GET /api/stats/overview", "GET", "/api/stats/overview")
measure(
    "GET /api/stats/errors week, 366 days",
    "GET",
    "/api/stats/errors",
    params={"from": first_day, "to": anchor.isoformat(), "granularity": "week"},
)
measure("GET /api/stats/memory", "GET", "/api/stats/memory")
measure("GET /api/stats/progress", "GET", "/api/stats/progress")
measure("GET /api/stats/practice", "GET", "/api/stats/practice")
measure("POST /api/backup", "POST", "/api/backup")

review = step.get("review")
if review:
    grade_body = {
        "card_id": review["card_id"],
        "exercise_type": review["exercise_type"],
        "exercise_template_id": review["exercise_template_id"],
        "answer": "x",
        "response_time_ms": 3000,
    }
    measure("POST /api/reviews/grade", "POST", "/api/reviews/grade", json=grade_body)
else:
    print("POST /api/reviews/grade: the next step is not a review")
