"""`ai_call_log` writer: one row per provider request, in a short transaction of its own.

Why not the caller's session (exception to D-023, see D-038): a rollback of the caller must not
erase the trace of failed calls, and a SQLite write transaction must never stay open during a slow
network call (`busy_timeout` is 5 s). A write failure is logged and swallowed: it never turns a
successful AI result into an error. Rows never hold a prompt, a response, user text or a key.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AICallLog

logger = logging.getLogger("app.ai")


@dataclass(frozen=True)
class CallRecord:
    started_at: datetime
    provider: str
    model: str
    task: str
    prompt_version: str | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    success: bool
    http_status: int | None
    error_code: str | None
    error_message: str | None  # already masked and truncated by the gateway
    attempt: int
    fallback_from: str | None


class CallJournal:
    def __init__(
        self, session_factory: Callable[[], Session], mask: Callable[[str], str] = str
    ) -> None:
        self._session_factory = session_factory
        self._mask = mask

    def record(self, record: CallRecord) -> int | None:
        """Write and commit one row; returns its id, or None if the write failed."""
        try:
            with self._session_factory() as session:
                row = AICallLog(**vars(record))
                session.add(row)
                session.flush()
                row_id = row.id
                session.commit()
                return row_id
        except Exception as exc:
            logger.warning(
                "could not write ai_call_log (%s): %s", type(exc).__name__, self._mask(str(exc))
            )
            return None
