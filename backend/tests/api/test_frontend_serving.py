"""Use mode (M10.b): the built frontend served by the backend, on a fake `dist` (no npm build)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.frontend import (
    CONTENT_SECURITY_POLICY,
    FrontendNotBuilt,
    mount_frontend,
    resolve_file,
)
from app.api.headers import SECURITY_HEADERS
from app.config import Settings
from app.db.engine import get_engine
from app.main import create_app

PORT = 8000
INDEX = "<!doctype html><title>fake</title><div id=root></div>"
SECRET = "TOP-SECRET-VALUE"  # noqa: S105 (a fake value)


@pytest.fixture
def site(tmp_path: Path) -> Path:
    """`site/dist` is the fake build; `site/.env` and `site/outside.txt` are outside of it."""
    root = tmp_path / "site"
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "assets" / "Font-abc123.woff2").write_bytes(b"wOF2-fake")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (root / ".env").write_text(f"VOCAB_GEMINI_API_KEY={SECRET}\n", encoding="utf-8")
    (root / "outside.txt").write_text(SECRET, encoding="utf-8")
    (root / "dist2").mkdir()  # a sibling whose name starts like `dist`
    (root / "dist2" / "leak.txt").write_text(SECRET, encoding="utf-8")
    return dist


def make_client(site: Path, engine: Engine, *, host: str = f"127.0.0.1:{PORT}") -> TestClient:
    settings = Settings(_env_file=None, use_mode=True, frontend_dist=site)  # type: ignore[call-arg]
    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app, base_url=f"http://{host}", follow_redirects=False)


@pytest.fixture
def client(site: Path, engine: Engine) -> Iterator[TestClient]:
    with make_client(site, engine) as test_client:
        yield test_client


def test_root_and_deep_pages_receive_index_html(client: TestClient) -> None:
    for url in ("/", "/library", "/library/items/3", "/stats?granularity=week&from=2026-01-01"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.text == INDEX
        assert response.headers["content-type"].startswith("text/html")


def test_head_on_a_page_has_no_body(client: TestClient) -> None:
    response = client.head("/library/items/3")
    assert response.status_code == 200
    assert response.content == b""


def test_missing_files_are_404_and_never_html(client: TestClient) -> None:
    for url in (
        "/assets/absent.js",
        "/assets/absent",
        "/favicon-absent.png",
        "/assets/",
        "/assets",
    ):
        response = client.get(url)
        assert response.status_code == 404, url
        assert "<!doctype" not in response.text.lower(), url


def test_unknown_api_and_docs_paths_keep_the_plain_404(client: TestClient) -> None:
    for url in ("/api/inconnu", "/api", "/docs/nothing", "/redoc/x"):
        response = client.get(url)
        assert response.status_code == 404, url
        assert response.json() == {"detail": "Not Found"}
    assert client.post("/api/inconnu", json={}).status_code == 404


def test_a_write_on_a_page_path_is_never_answered_with_html(client: TestClient) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, "/library", json={})
        assert response.status_code == 405, method
        assert response.headers["allow"] == "GET, HEAD"
        assert "<!doctype" not in response.text.lower()


def test_docs_and_openapi_still_work_without_the_strict_csp(client: TestClient) -> None:
    for url in ("/docs", "/openapi.json"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert "content-security-policy" not in response.headers


def test_cache_headers_by_kind_of_file(client: TestClient) -> None:
    hashed = client.get("/assets/app-abc123.js")
    assert hashed.status_code == 200
    assert hashed.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert hashed.headers["content-type"].startswith("text/javascript")
    font = client.get("/assets/Font-abc123.woff2")
    assert font.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert font.headers["content-type"] == "font/woff2"
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/favicon.svg").headers["cache-control"] == "no-cache"
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_security_headers_everywhere_and_csp_on_the_frontend_only(client: TestClient) -> None:
    for url in (
        "/",
        "/assets/app-abc123.js",
        "/api/health",
        "/api/inconnu",
        "/docs",
        "/assets/x.js",
    ):
        response = client.get(url)
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value, (url, name)
    assert client.get("/").headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert client.get("/assets/app-abc123.js").headers["content-security-policy"]
    assert "content-security-policy" not in client.get("/api/health").headers
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "microphone=(self)" in SECURITY_HEADERS["Permissions-Policy"]


def test_localhost_is_redirected_to_the_loopback_address(site: Path, engine: Engine) -> None:
    for host in (f"localhost:{PORT}", f"[::1]:{PORT}"):
        with make_client(site, engine, host=host) as client:
            response = client.get("/library/items/3?granularity=week&x=a%20b")
            assert response.status_code == 307, host
            assert (
                response.headers["location"]
                == f"http://127.0.0.1:{PORT}/library/items/3?granularity=week&x=a%20b"
            )
            assert client.head("/stats").status_code == 307
            assert client.get("/api/health").status_code == 307
            # A write is not redirected (the browser would replay it): it reaches the page rules.
            assert client.post("/api/inconnu", json={}).status_code == 404


def test_a_foreign_host_gets_403_before_any_redirect(site: Path, engine: Engine) -> None:
    for host in ("evil.example:8000", "localhost:9999", "127.0.0.1:9999", "evil.example"):
        with make_client(site, engine, host=host) as client:
            for url in ("/", "/assets/app-abc123.js", "/api/health", "/stats"):
                response = client.get(url)
                assert response.status_code == 403, (host, url)
                assert "location" not in response.headers
                assert response.json()["detail"]["code"] == "forbidden_host"


def test_the_guard_still_applies_to_writes_in_single_port_mode(client: TestClient) -> None:
    own = f"http://127.0.0.1:{PORT}"
    for origin in ("http://evil.example", "null", "http://127.0.0.1:5174"):
        response = client.post("/api/inconnu", json={}, headers={"Origin": origin})
        assert response.status_code == 403, origin
        assert response.json()["detail"]["code"] == "forbidden_origin"
    cross = client.post("/api/inconnu", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403
    text = client.post("/api/inconnu", content="a=b", headers={"Content-Type": "text/plain"})
    assert text.status_code == 415
    # The page served on this port writes to the API: accepted (here: reaches the 404).
    same = client.post(
        "/api/inconnu", json={}, headers={"Origin": own, "Sec-Fetch-Site": "same-origin"}
    )
    assert same.status_code == 404


MALICIOUS = [
    "/assets/../.env",
    "/%2e%2e/.env",
    "/assets/%2e%2e/%2e%2e/.env",
    "/assets/..%2f..%2f.env",
    "/assets/..%2f..%2fbackend%2fapp%2fconfig.py",
    "/assets/..%5c..%5c.env",
    "/assets/..\\..\\.env",
    "/C:/Windows/win.ini",
    "/C%3A%5CWindows%5Cwin.ini",
    "//etc/passwd",
    "/assets/app-abc123.js%00.png",
    "/assets/%00",
    "/..%2fdist2%2fleak.txt",
    "/assets/../../dist2/leak.txt",
    "/assets/....//....//.env",
    "/assets/app-abc123.js::$DATA",
    "/outside.txt",
    "/.env",
]


@pytest.mark.parametrize("url", MALICIOUS)
def test_malicious_paths_never_leave_dist(client: TestClient, url: str) -> None:
    response = client.get(url)
    assert SECRET not in response.text, url
    assert "VOCAB_" not in response.text, url
    assert "def " not in response.text, url
    assert response.status_code != 500, url
    if response.status_code == 200:  # only a page fallback (no extension) may answer
        assert response.text == INDEX


@pytest.mark.parametrize(
    "url_path",
    [
        "/../.env",
        "/assets/../../.env",
        "/assets/../../dist2/leak.txt",
        "\\..\\.env",
        "/assets/..\\..\\.env",
        "/C:/Windows/win.ini",
        "/assets/a\x00.js",
        "/..",
        "/",
        "",
    ],
)
def test_resolve_file_refuses_decoded_paths_outside_dist(site: Path, url_path: str) -> None:
    assert resolve_file(site.resolve(), url_path) is None


def test_resolve_file_finds_real_files_only(site: Path) -> None:
    dist = site.resolve()
    assert resolve_file(dist, "/assets/app-abc123.js") == dist / "assets" / "app-abc123.js"
    assert resolve_file(dist, "/assets") is None  # a directory
    assert resolve_file(dist, "/assets/absent.js") is None


def test_a_symbolic_link_out_of_dist_is_not_followed(site: Path) -> None:
    link = site / "assets" / "link-abc123.txt"
    try:
        link.symlink_to(site.parent / "outside.txt")
    except OSError:
        pytest.skip("symbolic links need a privilege on this machine")
    assert resolve_file(site.resolve(), "/assets/link-abc123.txt") is None


def test_a_missing_build_stops_the_start_with_the_command_to_run(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, use_mode=True, frontend_dist=tmp_path / "nothing")  # type: ignore[call-arg]
    with pytest.raises(FrontendNotBuilt, match=r"npm --prefix frontend run build"):
        create_app(settings)
    (tmp_path / "empty").mkdir()
    with pytest.raises(FrontendNotBuilt, match=r"index\.html"):
        mount_frontend(create_app(Settings(_env_file=None)), tmp_path / "empty")  # type: ignore[call-arg]


def test_development_mode_does_not_serve_the_frontend(engine: Engine) -> None:
    app = create_app(Settings(_env_file=None))  # type: ignore[call-arg]
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}", follow_redirects=False)
    assert client.get("/").status_code == 404
    assert client.get("/library").status_code == 404
    # Redirect off too: `localhost` is simply an allowed Host (the Vite proxy sets its own).
    local = TestClient(app, base_url=f"http://localhost:{PORT}", follow_redirects=False)
    assert local.get("/api/health").status_code == 200
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"


def test_an_unhandled_error_does_not_leak_a_traceback(site: Path, engine: Engine) -> None:
    settings = Settings(_env_file=None, use_mode=True, frontend_dist=site)  # type: ignore[call-arg]
    app = create_app(settings)

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError(f"explosion {SECRET}")

    app.router.routes.insert(0, app.router.routes.pop())  # before the page fallback

    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}", raise_server_exceptions=False)
    response = client.get("/api/boom")
    assert response.status_code == 500
    assert SECRET not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
