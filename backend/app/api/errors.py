"""One error format for the whole API: `{"detail": {"code": "...", "message": "..."}}` (D-063).

`code` is stable and meant for the program (and for the i18n key of the screen); `message` is an
English explanation. Messages are masked with the configured keys. FastAPI's own 422 answers quote
the value that was received (`input`), which would send a pasted key straight back: the handler
below keeps only the location and the rule.
"""

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from app.ai.redact import mask_secrets
from app.config import get_settings
from app.db.engine import get_engine, sqlite_file
from app.domain.deck_queue import InvalidDeckTransition
from app.domain.item_status import InvalidItemTransition
from app.services.discovery import DiscoveryError
from app.services.library import LibraryError


def api_error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    secrets = get_settings().secret_values()
    detail = {"code": code, "message": mask_secrets(message, secrets), **extra}
    return HTTPException(status_code=status, detail=detail)


def require_database(engine: Annotated[Engine, Depends(get_engine)]) -> None:
    """503 instead of silently creating an empty database file when `db upgrade` was never run."""
    db_file = sqlite_file(engine.url.render_as_string(hide_password=False))
    if db_file is not None and not db_file.exists():
        raise api_error(
            503, "database_unavailable", "There is no database yet. Run `python -m app db upgrade`."
        )


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 (narrowing)
    errors = [
        {"loc": [str(part) for part in error["loc"]], "message": str(error["msg"])}
        for error in exc.errors()  # `input` and `ctx` are left out on purpose
    ]
    detail = {"code": "invalid_request", "message": "The request is invalid.", "errors": errors}
    return JSONResponse({"detail": detail}, status_code=422)


def _error_response(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    secrets = get_settings().secret_values()
    detail = {"code": code, "message": mask_secrets(message, secrets), **extra}
    return JSONResponse({"detail": detail}, status_code=status)


async def _library_error(_request: Request, exc: Exception) -> JSONResponse:
    """A refusal raised by a library service (module A): its own status, code and details."""
    assert isinstance(exc, LibraryError)  # noqa: S101 (narrowing)
    return _error_response(exc.status, exc.code, exc.message, **exc.extra)


async def _invalid_transition(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidItemTransition)  # noqa: S101 (narrowing)
    return _error_response(
        409,
        "invalid_transition",
        f"A term cannot go from {exc.from_status.value} to {exc.to_status.value} this way.",
        from_status=exc.from_status.value,
        to_status=exc.to_status.value,
    )


async def _invalid_deck_transition(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidDeckTransition)  # noqa: S101 (narrowing)
    return _error_response(
        409,
        "invalid_transition",
        f"A deck cannot go from {exc.from_status.value} to {exc.to_status.value}.",
        from_status=exc.from_status.value,
        to_status=exc.to_status.value,
    )


async def _discovery_error(_request: Request, exc: Exception) -> JSONResponse:
    """A paused or done deck, or a term that is not in the deck given (D-025)."""
    assert isinstance(exc, DiscoveryError)  # noqa: S101 (narrowing)
    return _error_response(409, "discovery_not_allowed", str(exc))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(LibraryError, _library_error)
    app.add_exception_handler(InvalidItemTransition, _invalid_transition)
    app.add_exception_handler(InvalidDeckTransition, _invalid_deck_transition)
    app.add_exception_handler(DiscoveryError, _discovery_error)
