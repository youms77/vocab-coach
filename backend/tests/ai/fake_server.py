"""A tiny HTTP server on 127.0.0.1 that plays scripted answers, for adapter and gateway tests.

Real sockets on the loopback interface (the network guard of `conftest.py` allows them and refuses
everything else), so the adapters are exercised end to end: URL, headers, body, status, timeouts.
"""

import contextlib
import json
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class Reply:
    """One scripted answer. `body` may be bytes, text or a JSON-serialisable value."""

    status: int = 200
    body: Any = b""
    headers: dict[str, str] = field(default_factory=dict)
    delay_s: float = 0.0  # wait before answering (timeout tests)
    drop: bool = False  # close the connection without answering


@dataclass
class Received:
    method: str
    path: str
    headers: dict[str, str]  # lower-case names
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


Handler = Callable[[Received], Reply]


def fixture_reply(provider: str, name: str, status: int = 200, **kwargs: Any) -> Reply:
    """A reply whose body is `tests/ai/fixtures/<provider>/<name>.json` (read as UTF-8)."""
    body = (FIXTURES / provider / f"{name}.json").read_text(encoding="utf-8")
    return Reply(status=status, body=body, **kwargs)


class FakeServer:
    """Plays `script` in order, one reply per request (the last one repeats), or asks `handler`."""

    def __init__(self, script: Iterable[Reply] = (), *, handler: Handler | None = None) -> None:
        self.script = list(script)
        self.handler = handler
        self.requests: list[Received] = []
        self._lock = threading.Lock()
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                received = Received(
                    method="POST",
                    path=self.path,
                    headers={name.lower(): value for name, value in self.headers.items()},
                    body=self.rfile.read(length),
                )
                reply = outer._next_reply(received)
                if reply.delay_s:
                    time.sleep(reply.delay_s)
                if reply.drop:
                    self.close_connection = True
                    return
                payload = _encode(reply.body)
                self.send_response(reply.status)
                headers = {"Content-Type": "application/json; charset=utf-8", **reply.headers}
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                with contextlib.suppress(OSError):  # the client may have given up (timeouts)
                    self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                pass  # keep the test output clean

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "FakeServer":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _next_reply(self, received: Received) -> Reply:
        with self._lock:
            self.requests.append(received)
            index = len(self.requests) - 1
        if self.handler is not None:
            return self.handler(received)
        if not self.script:
            return Reply(status=500, body={"error": "no scripted reply"})
        return self.script[min(index, len(self.script) - 1)]


def _encode(body: Any) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body, ensure_ascii=False).encode("utf-8")
