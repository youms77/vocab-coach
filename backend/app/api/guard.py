"""Protection of the API against requests forged by another web page (D-061).

The API listens on the loopback only, but the owner's browser can reach it, so a page opened in
another tab could try two things:

- **Cross-site request forgery**: make the browser send a write request (`PUT /api/ai/...`).
- **DNS rebinding**: make a hostile domain resolve to 127.0.0.1 and read the answers.

Three rules, applied to the whole application (`/docs` and `/openapi.json` too):

1. `Host` must be the loopback address with the backend's port (rebinding sends the hostile name).
2. A write method (POST, PUT, PATCH, DELETE) with an `Origin` outside the allowed list, or with
   `Sec-Fetch-Site: cross-site`, is refused. The browser sets both headers; a page cannot forge
   them.
3. A POST, PUT or PATCH with a body must be `application/json`: a form from another site cannot
   send that without a CORS preflight, which the CORS middleware refuses. The one exception is a
   raw recording, an `audio/*` body, on the `/api/speech/` paths only (D-170): no `audio/*` type is
   "CORS-safelisted" either, so another site still needs a preflight, refused the same way.

Pure ASGI (no `BaseHTTPMiddleware`: it would buffer bodies and complicate streaming). Added last in
`create_app` so it is the outermost layer: even a CORS preflight goes through the Host check.
"""

from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")
# Recordings are posted raw, with their audio media type, under this prefix (module F).
AUDIO_UPLOAD_PREFIX = "/api/speech/"


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


class ApiGuard:
    def __init__(self, app: ASGIApp, *, port: int, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = frozenset(f"{name}:{port}" for name in LOOPBACK_NAMES)
        # The configured origins (Vite) plus the backend's own, for the single-port mode (M10).
        self.allowed_origins = frozenset(
            {_normalize_origin(origin) for origin in allowed_origins}
            | {f"http://{host}" for host in self.allowed_hosts}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":  # no WebSocket in this application
            await send({"type": "websocket.close", "code": 1008})
            return
        refusal = self._refusal(scope)
        if refusal is None:
            await self.app(scope, receive, send)
            return
        status, code, message = refusal
        response = JSONResponse(
            {"detail": {"code": code, "message": message}},
            status_code=status,
        )
        await response(scope, receive, send)

    def _refusal(self, scope: Scope) -> tuple[int, str, str] | None:
        raw = [
            (name.decode("latin-1"), value.decode("latin-1")) for name, value in scope["headers"]
        ]
        headers = dict(raw)
        hosts = [value.strip().lower() for name, value in raw if name == "host"]
        if len(hosts) != 1 or hosts[0] not in self.allowed_hosts:  # two Host headers: ambiguous
            return 403, "forbidden_host", "This address is not allowed. Use http://127.0.0.1."

        method = scope["method"].upper()
        if method not in WRITE_METHODS:
            return None
        origin = headers.get("origin")
        if origin is not None and _normalize_origin(origin) not in self.allowed_origins:
            return 403, "forbidden_origin", "Requests from this origin are not allowed."
        if headers.get("sec-fetch-site", "").strip().lower() == "cross-site":
            return 403, "cross_site_request", "Cross-site requests are not allowed."

        if method in BODY_METHODS and _has_body(headers):
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            audio_upload = media_type.startswith("audio/") and scope["path"].startswith(
                AUDIO_UPLOAD_PREFIX
            )
            if media_type != "application/json" and not audio_upload:
                return 415, "unsupported_media_type", "The request body must be application/json."
        return None


def _has_body(headers: dict[str, str]) -> bool:
    if "transfer-encoding" in headers:
        return True
    length = headers.get("content-length", "").strip()
    return length not in ("", "0")
