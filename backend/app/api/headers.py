"""Security headers and the `localhost` redirect of the use mode (M10.b, D-310, D-312).

Both are pure ASGI middlewares (no `BaseHTTPMiddleware`, which would buffer streamed bodies such
as the recordings). Their place in the stack is set in `create_app`: the Host guard (D-061) is the
outermost layer, so a foreign Host is refused before any redirect.
"""

from starlette.datastructures import MutableHeaders
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # The microphone serves the speaking practice (M6); speech synthesis needs no permission.
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
}
API_PREFIX = "/api"


def is_api_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


class SecurityHeaders:
    """Adds the fixed headers to every HTTP response and `Cache-Control: no-store` to `/api`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        api = is_api_path(scope["path"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                if api and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class LocalhostRedirect:
    """`localhost:<port>` and `[::1]:<port>` -> 307 to `127.0.0.1:<port>`, same path and query.

    The browser keeps its preferences (theme, language) per origin: one address only. Reading
    requests only (GET, HEAD); a write sent to another name is not redirected, the browser would
    replay it. Anything else is passed on untouched.
    """

    def __init__(self, app: ASGIApp, *, port: int) -> None:
        self.app = app
        self.port = port
        self.redirected = frozenset({f"localhost:{port}", f"[::1]:{port}"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"].upper() in ("GET", "HEAD"):
            hosts = [
                value.decode("latin-1").strip().lower()
                for name, value in scope["headers"]
                if name == b"host"
            ]
            if len(hosts) == 1 and hosts[0] in self.redirected:
                path = scope.get("raw_path") or scope["path"].encode()
                target = f"http://127.0.0.1:{self.port}{path.decode('latin-1')}"
                if scope["query_string"]:
                    target += "?" + scope["query_string"].decode("latin-1")
                await RedirectResponse(target, status_code=307)(scope, receive, send)
                return
        await self.app(scope, receive, send)
