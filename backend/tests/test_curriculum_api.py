"""Module H API: tracks, start, open, unit, errors in the D-063 format, and the triage hand-off."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.engine import get_engine, get_session
from app.main import create_app
from app.services import curriculum

CONTENT = Path(__file__).resolve().parents[2] / "content"


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    """Both the engine and the session dependency point at the test database: routes commit."""

    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = session_override
    with TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}") as test_client:
        yield test_client


def code_of(response) -> str:  # noqa: ANN001
    return response.json()["detail"]["code"]


def test_tracks_and_detail(client: TestClient) -> None:
    tracks = client.get("/api/curriculum/tracks").json()
    assert [t["code"] for t in tracks] == ["general_everyday", "academic", "speaking_scenarios"]
    assert tracks[0]["title"] == {"en": "General everyday English", "fr": "Anglais courant"}
    assert tracks[0]["unit_count"] == 113 and tracks[0]["started"] is False

    page = client.get("/api/curriculum/tracks/academic?limit=5&offset=10").json()
    assert page["total_units"] == 39 and page["limit"] == 5 and page["offset"] == 10
    assert [u["number"] for u in page["units"]] == [11, 12, 13, 14, 15]
    assert page["units"][0]["state"] == "not_opened" and page["units"][0]["unit_id"] is None

    scenarios = client.get("/api/curriculum/tracks/speaking_scenarios?limit=50").json()
    assert len(scenarios["units"]) == 16
    assert {u["content_status"] for u in scenarios["units"]} == {"pending"}

    assert client.get("/api/curriculum/tracks/nope").status_code == 404
    assert client.get("/api/curriculum/tracks/academic?limit=0").status_code == 422
    assert client.get("/api/curriculum/units/99").status_code == 404


def test_start_open_reopen_and_unit(client: TestClient) -> None:
    refused = client.post("/api/curriculum/tracks/academic/units/1/open")
    assert refused.status_code == 409 and code_of(refused) == "track_not_started"
    assert refused.json()["detail"]["track"] == "academic"

    started = client.post("/api/curriculum/tracks/academic/start").json()
    assert started["created"] is True and started["track"]["started"] is True
    again = client.post("/api/curriculum/tracks/academic/start").json()
    assert again["created"] is False and again["track"]["deck_id"] == started["track"]["deck_id"]

    opened = client.post("/api/curriculum/tracks/academic/units/1/open").json()
    assert opened["created"] is True and opened["imported"] == 25
    unit = opened["unit"]
    assert unit["code"] == "nawl_001" and unit["state"] == "opened"
    assert unit["terms"][0]["term"] == "abdominal"

    reopened = client.post("/api/curriculum/tracks/academic/units/1/open").json()
    assert reopened["created"] is False and reopened["unit"]["id"] == unit["id"]
    assert client.get(f"/api/curriculum/units/{unit['id']}").json() == reopened["unit"]

    detail = client.get("/api/curriculum/tracks/academic?limit=2").json()
    assert [u["state"] for u in detail["units"]] == ["opened", "not_opened"]
    assert detail["track"]["opened_units"] == 1

    missing = client.post("/api/curriculum/tracks/academic/units/40/open")
    assert missing.status_code == 404 and code_of(missing) == "unit_not_found"
    scenario = client.post("/api/curriculum/tracks/speaking_scenarios/units/1/open")
    assert scenario.status_code == 422 and code_of(scenario) == "not_a_wordlist_track"


def test_triage_accepts_the_25_decisions_of_a_unit_at_once(client: TestClient) -> None:
    client.post("/api/curriculum/tracks/general_everyday/start")
    unit = client.post("/api/curriculum/tracks/general_everyday/units/1/open").json()["unit"]
    ids = [t["item_id"] for t in unit["terms"]]
    assert len(ids) == 25
    waiting = client.get("/api/triage", params={"deck_id": unit["deck_id"]}).json()
    assert [e["item_id"] for e in waiting] == ids
    decisions = [
        {"item_id": item_id, "decision": ("known", "unsure", "learn")[n % 3]}
        for n, item_id in enumerate(ids)
    ]
    done = client.post("/api/triage", json={"decisions": decisions})
    assert done.status_code == 200
    assert sum(done.json().values()) == 25
    after = client.get(f"/api/curriculum/units/{unit['id']}").json()
    assert after["state"] == "triaged"
    assert client.get("/api/triage", params={"deck_id": unit["deck_id"]}).json() == []


def test_missing_wordlist_is_reported(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(CONTENT / "curriculum.yaml", tmp_path / "curriculum.yaml")
    monkeypatch.setattr(curriculum, "CONTENT_DIR", tmp_path)  # no wordlists folder at all
    tracks = {t["code"]: t for t in client.get("/api/curriculum/tracks").json()}
    assert tracks["academic"]["available"] is False
    assert tracks["academic"]["reason"] == "wordlist_missing"
    assert tracks["speaking_scenarios"]["available"] is True
    response = client.post("/api/curriculum/tracks/academic/start")
    assert response.status_code == 409 and code_of(response) == "wordlist_missing"
    assert client.get("/api/curriculum/tracks").json()[1]["started"] is False


def test_unavailable_syllabus(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curriculum, "CONTENT_DIR", tmp_path)
    response = client.get("/api/curriculum/tracks")
    assert response.status_code == 503 and code_of(response) == "syllabus_unavailable"
