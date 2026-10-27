"""Serving the built frontend from the backend, in the use mode (M10.b, D-310 to D-312).

One catch-all route, registered after every API route. For a request that reaches it:

- under `/api`, `/docs`, `/redoc`, `/openapi.json` (no such route matched): a plain 404, as before;
- under `/assets/`, or when the last segment has an extension: a real file of the build, found
  after resolving the path and checking that it stays inside `dist`, else a 404. Never
  `index.html`: a missing `.js` must not receive HTML;
- any other `GET` / `HEAD` path (`/library/items/3`): `index.html`, the single-page application's
  entry (the SPA fallback; the router of the browser does the rest);
- any other method on a page path: 405.

The Content-Security-Policy is set here, on the frontend's responses only; `/docs` needs inline
scripts and keeps its own behaviour.
"""

import re
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response

NOT_BUILT = (
    "The frontend is not built: {path} was not found. "
    "Build it with `npm --prefix frontend run build` (or start with `.\\start.ps1 -Use`, "
    "which builds when needed)."
)
BACKEND_PREFIXES = ("/api", "/docs", "/redoc", "/openapi.json")
ASSETS_PREFIX = "/assets"
# Vite names built files `<name>-<hash>.<ext>`; the hash changes with the content.
HASHED = re.compile(r"-[A-Za-z0-9_-]{6,}\.[A-Za-z0-9]+$")
IMMUTABLE = "public, max-age=31536000, immutable"
# Windows takes media types from the registry, where `.js` can be `text/plain`: fixed here.
MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".txt": "text/plain; charset=utf-8",
}
# Strict: only the application's own files. `blob:` serves the recordings (M6) and downloads,
# `data:` small images. No inline script or style (D-311).
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


class FrontendNotBuilt(RuntimeError):
    """`dist/` or its `index.html` is missing: the message names the command to run."""


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def resolve_file(dist: Path, url_path: str) -> Path | None:
    """The file of `dist` that `url_path` names, or None. `dist` must be already resolved.

    The path comes decoded from the server (`%2e%2e` is `..` by now). Refused before touching the
    disk: NUL, backslash (a Windows separator), a colon (drive letter, NTFS stream). Then the
    path is resolved (symbolic links, `..`) and must still be inside `dist`.
    """
    relative = url_path.lstrip("/")
    if not relative or any(char in relative for char in ("\x00", "\\", ":")):
        return None
    try:
        candidate = (dist / relative).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(dist) or not candidate.is_file():
        return None
    return candidate


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve `dist` from `app`. Raises FrontendNotBuilt when the build is missing."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise FrontendNotBuilt(NOT_BUILT.format(path=index))

    def file_response(path: Path, cache_control: str) -> FileResponse:
        return FileResponse(
            path,
            media_type=MEDIA_TYPES.get(path.suffix.lower()),
            headers={
                "Cache-Control": cache_control,
                "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            },
        )

    async def serve(request: Request) -> Response:
        path = request.scope["path"]
        if any(_under(path, prefix) for prefix in BACKEND_PREFIXES):
            raise HTTPException(404)  # the answer an unknown route had before the use mode
        if request.method.upper() not in ("GET", "HEAD"):
            raise HTTPException(405, headers={"Allow": "GET, HEAD"})
        if _under(path, ASSETS_PREFIX) or "." in path.rsplit("/", 1)[-1]:
            found = resolve_file(dist, path)
            if found is None:
                raise HTTPException(404)
            hashed = _under(path, ASSETS_PREFIX) and HASHED.search(found.name)
            return file_response(found, IMMUTABLE if hashed else "no-cache")
        return file_response(index, "no-cache")

    app.add_route(
        "/{path:path}",
        serve,
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
