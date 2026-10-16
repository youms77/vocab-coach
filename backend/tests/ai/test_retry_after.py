"""`retry_after` formats, JSON fences and the small helpers shared by the adapters."""

from datetime import UTC, datetime

import pytest

from app.ai.providers.common import (
    as_int,
    parse_retry_after,
    retry_after_from_message,
    strip_json_fence,
)

NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2, 2.0),
        (2.5, 2.5),
        ("2", 2.0),
        ("2.5", 2.5),
        (" 7 ", 7.0),
        ("34s", 34.0),
        ("34S", 34.0),
        ("7.66s", 7.66),
        ("2m59.56s", 179.56),
        ("1h2m3s", 3723.0),
        ("5m", 300.0),
        ("700ms", 0.7),
        ("1m30s", 90.0),
        ("0s", 0.0),
        ("0", 0.0),
    ],
)
def test_seconds_and_durations(value: object, expected: float) -> None:
    assert parse_retry_after(value) == pytest.approx(expected)


def test_http_date_is_relative_to_now() -> None:
    assert parse_retry_after("Fri, 16 Oct 2026 12:00:30 GMT", now=NOW) == 30.0
    assert parse_retry_after("Fri, 16 Oct 2026 11:59:00 GMT", now=NOW) == 0.0  # already past


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "soon", "-3", -1, float("nan"), float("inf"), "1x", "s", "ms", True, "12:00"],
)
def test_unreadable_values_are_none(value: object) -> None:
    assert parse_retry_after(value) is None


def test_retry_after_quoted_in_a_message() -> None:
    message = "Rate limit reached for model X ... Please try again in 7m12.5s. Visit https://..."
    assert retry_after_from_message(message) == pytest.approx(432.5)
    assert retry_after_from_message("Please try again in 700ms.") == pytest.approx(0.7)
    assert retry_after_from_message("Please try again in 34s") == 34.0
    assert retry_after_from_message("no hint here") is None
    assert retry_after_from_message(None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('  ```json\n{"a": 1}\n```  \n', '{"a": 1}'),
        ('```json\n{"a": 1}', '{"a": 1}'),  # closing fence missing
        ('{"text": "use ``` for code"}', '{"text": "use ``` for code"}'),  # not a fence
        ("```", "```"),  # nothing to unwrap
    ],
)
def test_json_fences(text: str, expected: str) -> None:
    assert strip_json_fence(text) == expected


def test_token_counts() -> None:
    assert as_int(12) == 12 and as_int(0) == 0
    assert as_int(None) is None and as_int("12") is None and as_int(True) is None
    assert as_int(-1) is None and as_int(1.5) is None
