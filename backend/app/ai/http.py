"""Minimal HTTP client for the AI providers, standard library only (D-046).

The three provider APIs are plain JSON POSTs, and the gateway owns retries, so an SDK would only add
its own retry loop, its own error types and a dependency to audit. What matters here:

- a non-2xx answer is a normal `HttpResponse` (the adapter translates it, it has the headers);
- every network failure becomes a `ProviderError` whose message is fixed text, never `str(exc)`:
  library errors may quote the URL, and the URL may carry a credential;
- redirects are refused (a redirect could forward the API key header to another host);
- loopback hosts bypass the system proxy (Ollama), everything else uses it;
- only `http` and `https` URLs: `urllib` would also open `file:` URLs.
"""

import http.client
import json
import re
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.ai.types import ErrorKind, ProviderError

USER_AGENT = "vocab-coach/0.1"  # an explicit one: some API gateways refuse "Python-urllib"
MAX_BODY_BYTES = 4 * 1024 * 1024  # an answer larger than this is not a chat completion
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]  # lower-case names
    body: bytes

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def json(self) -> Any:
        """The body as JSON, or None when it is not valid UTF-8 JSON."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError:  # includes UnicodeDecodeError
            return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the 3xx answer is returned as an HTTPError, then as an HttpResponse


_REMOTE_OPENER = urllib.request.build_opener(_NoRedirect)
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def post(url: str, *, headers: Mapping[str, str], body: bytes, timeout_s: float) -> HttpResponse:
    """POST `body` and return the answer, whatever its status.

    `timeout_s` bounds each socket operation and, through a deadline, the whole answer.
    Raises `ProviderError` (`network`, `transient` on a timeout, `bad_request` on a bad URL).
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ProviderError(ErrorKind.BAD_REQUEST, "the provider URL must be http(s)://host...")
    request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310 (scheme checked)
    request.add_header("User-Agent", USER_AGENT)
    for name, value in headers.items():
        request.add_header(name, value)
    opener = _LOOPBACK_OPENER if parts.hostname in LOOPBACK_HOSTS else _REMOTE_OPENER
    try:
        return _exchange(opener, request, timeout_s)
    except ProviderError:
        raise
    except TimeoutError:
        raise _timeout(timeout_s) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):  # a connect timeout arrives wrapped
            raise _timeout(timeout_s) from None
        raise ProviderError(ErrorKind.NETWORK, _describe_failure(exc.reason)) from None
    except (http.client.HTTPException, OSError) as exc:
        raise ProviderError(ErrorKind.NETWORK, _describe_failure(exc)) from None


def _timeout(timeout_s: float) -> ProviderError:
    return ProviderError(ErrorKind.TRANSIENT, f"the request timed out after {timeout_s:.1f} s")


def _exchange(
    opener: urllib.request.OpenerDirector, request: urllib.request.Request, timeout_s: float
) -> HttpResponse:
    deadline = time.monotonic() + timeout_s
    try:
        with opener.open(request, timeout=timeout_s) as reply:
            return _read(reply, reply.status, deadline)
    except urllib.error.HTTPError as exc:  # an answer with an error status
        with exc:
            return _read(exc, exc.code, deadline)


def _read(reply: Any, status: int, deadline: float) -> HttpResponse:
    chunks: list[bytes] = []
    size = 0
    while chunk := reply.read(_CHUNK):
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ProviderError(ErrorKind.BAD_REQUEST, "the provider answer is unexpectedly large")
        if time.monotonic() > deadline:
            raise TimeoutError
        chunks.append(chunk)
    headers = {name.lower(): value for name, value in reply.headers.items()}
    return HttpResponse(status=status, headers=headers, body=b"".join(chunks))


def _describe_failure(reason: object) -> str:
    """Fixed wording per failure class: never the exception text (it may quote the URL)."""
    if isinstance(reason, socket.gaierror):
        return "DNS lookup failed"
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused"
    if isinstance(reason, ssl.SSLError | ssl.CertificateError):
        return "TLS handshake failed"
    if isinstance(reason, http.client.RemoteDisconnected | ConnectionResetError):
        return "connection closed by the server"
    return f"connection failed ({type(reason).__name__})"


# --- multipart/form-data (speech-to-text uploads) ---------------------------------------------

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")
_SAFE_CONTENT_TYPE = re.compile(r"^[\w.+-]+/[\w.+-]+$")


def encode_multipart(
    fields: Mapping[str, str], *, file_field: str, filename: str, content_type: str, data: bytes
) -> tuple[bytes, str]:
    """A `multipart/form-data` body: text fields, then one file. Returns (body, Content-Type)."""
    boundary = f"vocabcoach{secrets.token_hex(16)}"
    safe_name = _SAFE_FILENAME.sub("_", Path(filename).name) or "audio"
    safe_type = (
        content_type if _SAFE_CONTENT_TYPE.match(content_type) else "application/octet-stream"
    )
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(value.encode("utf-8") + b"\r\n")
    lines.append(f"--{boundary}\r\n".encode())
    lines.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'.encode()
    )
    lines.append(f"Content-Type: {safe_type}\r\n\r\n".encode())
    lines.append(data + b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    return b"".join(lines), f"multipart/form-data; boundary={boundary}"
