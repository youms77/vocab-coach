from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app import __version__
from app.db.engine import create_db_engine, get_engine
from app.main import create_app
from tests.conftest import sqlite_url


def _client(engine: Engine) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app)


def test_health_reports_database_at_head(engine: Engine) -> None:
    response = _client(engine).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["version"]) == ("ok", __version__)
    assert body["database"] == {"ok": True, "revision": "0001", "at_head": True}


def test_health_without_database_does_not_create_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    engine = create_db_engine(sqlite_url(missing))
    try:
        body = _client(engine).get("/api/health").json()
    finally:
        engine.dispose()
    assert body["status"] == "ok"
    assert body["database"] == {"ok": False, "revision": None, "at_head": False}
    assert not missing.exists()


def test_unknown_route_is_404(engine: Engine) -> None:
    assert _client(engine).get("/api/does-not-exist").status_code == 404
