from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_health_returns_ok_and_version() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_unknown_route_is_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/does-not-exist").status_code == 404
