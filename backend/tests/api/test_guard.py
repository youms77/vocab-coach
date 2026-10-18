"""The API guard (D-061): Host, Origin / Sec-Fetch-Site and JSON-only write requests."""

import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.guard import ApiGuard

PORT = 8000  # the default; tests/api/conftest.py removes VOCAB_PORT from the environment
ORIGIN = f"http://127.0.0.1:{PORT}"
VITE = "http://127.0.0.1:5173"


class Body(BaseModel):
    value: str


def _app(*, guarded: bool = True) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/echo")
    @app.put("/echo")
    @app.patch("/echo")
    def echo(body: Body) -> dict[str, str]:
        return {"value": body.value}

    @app.delete("/echo")
    def remove() -> dict[str, str]:
        return {"deleted": "yes"}

    @app.post("/empty")
    def empty() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/speech/upload")
    @app.post("/api/other/upload")
    async def upload(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    if guarded:
        app.add_middleware(ApiGuard, port=PORT, allowed_origins=[VITE, "http://localhost:5173"])
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), base_url=f"http://127.0.0.1:{PORT}")


def _code(response: httpx2.Response) -> str:
    return response.json()["detail"]["code"]


# --- Host ---------------------------------------------------------------------------------------


def test_get_without_origin_is_accepted(client: TestClient) -> None:
    assert client.get("/ping").json() == {"ok": "yes"}


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "127.0.0.1", "0.0.0.0:8000"])
def test_foreign_host_is_refused_even_for_get(client: TestClient, host: str) -> None:
    response = client.get("/ping", headers={"Host": host})
    assert (response.status_code, _code(response)) == (403, "forbidden_host")


def test_wrong_port_is_refused(client: TestClient) -> None:
    response = client.get("/ping", headers={"Host": f"127.0.0.1:{PORT + 1}"})
    assert (response.status_code, _code(response)) == (403, "forbidden_host")


@pytest.mark.parametrize("name", ["localhost", "[::1]", "LOCALHOST", "127.0.0.1"])
def test_loopback_names_are_accepted(client: TestClient, name: str) -> None:
    assert client.get("/ping", headers={"Host": f"{name}:{PORT}"}).status_code == 200


def test_rebinding_preflight_is_refused_by_host_check(client: TestClient) -> None:
    response = client.options(
        "/echo",
        headers={
            "Host": "evil.example:8000",
            "Origin": "http://evil.example:8000",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert (response.status_code, _code(response)) == (403, "forbidden_host")


def test_two_host_headers_are_refused() -> None:
    guard = ApiGuard(_app(guarded=False), port=PORT, allowed_origins=[])
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [(b"host", f"127.0.0.1:{PORT}".encode()), (b"host", b"evil.example")],
    }
    refusal = guard._refusal(scope)  # noqa: SLF001
    assert refusal is not None
    assert refusal[1] == "forbidden_host"


# --- Origin and Sec-Fetch-Site --------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_foreign_origin_is_refused_on_writes(client: TestClient, method: str) -> None:
    response = client.request(
        method, "/echo", json={"value": "x"}, headers={"Origin": "https://evil.example"}
    )
    assert (response.status_code, _code(response)) == (403, "forbidden_origin")


def test_null_origin_is_refused(client: TestClient) -> None:
    response = client.put("/echo", json={"value": "x"}, headers={"Origin": "null"})
    assert (response.status_code, _code(response)) == (403, "forbidden_origin")


def test_cross_site_fetch_metadata_is_refused(client: TestClient) -> None:
    response = client.post("/echo", json={"value": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert (response.status_code, _code(response)) == (403, "cross_site_request")


@pytest.mark.parametrize("origin", [VITE, "http://localhost:5173", ORIGIN, f"http://[::1]:{PORT}"])
def test_known_origins_are_accepted(client: TestClient, origin: str) -> None:
    response = client.put("/echo", json={"value": "x"}, headers={"Origin": origin})
    assert response.status_code == 200


def test_same_site_and_same_origin_fetch_metadata_are_accepted(client: TestClient) -> None:
    for site in ("same-origin", "same-site", "none"):
        response = client.put("/echo", json={"value": "x"}, headers={"Sec-Fetch-Site": site})
        assert response.status_code == 200


def test_foreign_origin_on_get_is_not_blocked_here(client: TestClient) -> None:
    # Reads are protected by CORS (the page cannot read the answer) and by the Host check.
    assert client.get("/ping", headers={"Origin": "https://evil.example"}).status_code == 200


# --- Content type --------------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded"])
def test_non_json_body_is_refused(client: TestClient, content_type: str) -> None:
    response = client.put("/echo", content=b'{"value":"x"}', headers={"Content-Type": content_type})
    assert (response.status_code, _code(response)) == (415, "unsupported_media_type")


def test_body_without_content_type_is_refused(client: TestClient) -> None:
    response = client.post("/echo", content=b'{"value":"x"}')
    assert response.status_code == 415


def test_json_with_charset_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/echo",
        content=b'{"value":"x"}',
        headers={"Content-Type": "Application/JSON; charset=utf-8"},
    )
    assert response.json() == {"value": "x"}


def test_write_without_body_needs_no_content_type(client: TestClient) -> None:
    assert client.post("/empty").status_code == 200
    assert client.delete("/echo").status_code == 200


# --- Raw recordings (D-170) ----------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["audio/webm", "audio/wav", "Audio/Webm;codecs=opus"])
def test_an_audio_body_is_accepted_under_the_speech_paths(
    client: TestClient, content_type: str
) -> None:
    response = client.post(
        "/api/speech/upload", content=b"RIFF1234", headers={"Content-Type": content_type}
    )
    assert response.json() == {"bytes": 8}


def test_an_audio_body_is_refused_anywhere_else(client: TestClient) -> None:
    for path in ("/api/other/upload", "/echo"):
        response = client.post(path, content=b"RIFF", headers={"Content-Type": "audio/wav"})
        assert (response.status_code, _code(response)) == (415, "unsupported_media_type")


@pytest.mark.parametrize("content_type", ["text/plain", "video/webm", "application/octet-stream"])
def test_other_bodies_stay_refused_under_the_speech_paths(
    client: TestClient, content_type: str
) -> None:
    response = client.post(
        "/api/speech/upload", content=b"RIFF", headers={"Content-Type": content_type}
    )
    assert (response.status_code, _code(response)) == (415, "unsupported_media_type")


def test_an_audio_body_from_another_site_is_refused(client: TestClient) -> None:
    audio = {"Content-Type": "audio/webm"}
    foreign = client.post(
        "/api/speech/upload", content=b"RIFF", headers=audio | {"Origin": "https://evil.example"}
    )
    assert (foreign.status_code, _code(foreign)) == (403, "forbidden_origin")
    cross = client.post(
        "/api/speech/upload", content=b"RIFF", headers=audio | {"Sec-Fetch-Site": "cross-site"}
    )
    assert (cross.status_code, _code(cross)) == (403, "cross_site_request")


def test_an_audio_upload_from_another_site_fails_its_preflight(api_client: TestClient) -> None:
    """No `audio/*` type is CORS-safelisted: a page elsewhere must ask first, and is refused."""
    response = api_client.options(
        "/api/speech/shadowing",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded"])
def test_fastapi_alone_would_answer_422_to_a_form_body(content_type: str) -> None:
    """Why the explicit 415 exists: it does not depend on FastAPI's own behaviour."""
    bare = TestClient(_app(guarded=False))
    response = bare.put("/echo", content=b"value=x", headers={"Content-Type": content_type})
    assert response.status_code == 422


# --- Application wiring --------------------------------------------------------------------------


def test_real_app_is_protected_including_docs(api_client: TestClient) -> None:
    assert api_client.get("/docs").status_code == 200
    assert api_client.get("/openapi.json", headers={"Host": "evil.example"}).status_code == 403
    assert api_client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403


def test_vite_origin_passes_cors_preflight(api_client: TestClient) -> None:
    response = api_client.options(
        "/api/health", headers={"Origin": VITE, "Access-Control-Request-Method": "PUT"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == VITE
