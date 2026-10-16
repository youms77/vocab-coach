"""Helpers shared by the provider adapters: `retry_after` parsing, JSON fences, small extractors."""

import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

# "2m59.56s", "7.66s", "34s", "700ms", "1h2m3s"; the `(?!s)` keeps "ms" from matching as minutes.
_DURATION = re.compile(
    r"^(?:(?P<h>\d+(?:\.\d+)?)h)?"
    r"(?:(?P<m>\d+(?:\.\d+)?)m(?!s))?"
    r"(?:(?P<s>\d+(?:\.\d+)?)s)?"
    r"(?:(?P<ms>\d+(?:\.\d+)?)ms)?$"
)
_TRY_AGAIN = re.compile(r"try again in ([0-9hms.]+)", re.IGNORECASE)


def parse_retry_after(value: object, *, now: datetime | None = None) -> float | None:
    """Seconds to wait from a `Retry-After`-like value, or None when it cannot be read.

    Accepts a number of seconds (`2`, `"2.5"`), a duration (`"34s"`, `"2m59.56s"`, `"700ms"`) and an
    HTTP date (relative to `now`, UTC by default). Never negative, never NaN or infinite.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return _finite(float(value))
    text = str(value).strip().lower()
    if not text:
        return None
    try:
        return _finite(float(text))
    except ValueError:
        pass
    match = _DURATION.match(text)
    if match and any(match.groupdict().values()):
        parts = {key: float(number) for key, number in match.groupdict().items() if number}
        seconds = (
            parts.get("h", 0.0) * 3600
            + parts.get("m", 0.0) * 60
            + parts.get("s", 0.0)
            + parts.get("ms", 0.0) / 1000
        )
        return _finite(seconds)
    try:
        moment = parsedate_to_datetime(str(value).strip())
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return _finite((moment - (now or datetime.now(UTC))).total_seconds(), floor_at_zero=True)


def retry_after_from_message(message: str | None) -> float | None:
    """`retry_after` quoted in an error message, e.g. "Please try again in 7m12.5s"."""
    if not message:
        return None
    match = _TRY_AGAIN.search(message)
    return parse_retry_after(match.group(1).rstrip(".")) if match else None


def _finite(seconds: float, *, floor_at_zero: bool = False) -> float | None:
    if math.isnan(seconds) or math.isinf(seconds):
        return None
    if seconds < 0:
        return 0.0 if floor_at_zero else None
    return seconds


def strip_json_fence(text: str) -> str:
    """Remove a Markdown code fence around a JSON answer; any other text is returned unchanged.

    Native JSON modes should not produce one, but small local models sometimes do. Only a text
    that starts with a fence is touched, so a JSON string containing backticks is safe.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return text
    body = stripped[first_newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


def as_int(value: Any) -> int | None:
    """A token count from a JSON value (None when missing or not a plain integer)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
