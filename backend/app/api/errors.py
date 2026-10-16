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


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
