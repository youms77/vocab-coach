"""Output validation: one repair attempt, then `incomplete`; programming errors raise."""

from collections.abc import Callable

import pytest

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas import AiOutput
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.types import AiStatus, ErrorKind, InputTooLong, SchemaMismatch, UnknownTask
from tests.ai.conftest import log_rows, ping

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]


def test_invalid_output_is_repaired_once_with_the_validation_message(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success(content="not json at all"), Success())
    result = ping(make_gateway(a))

    assert result.ok and result.attempts == 2
    first, repaired = a.requests
    assert "rejected" not in first.user
    assert "Your previous answer was rejected" in repaired.user
    assert "Invalid JSON" in repaired.user
    rows = log_rows(engine)
    assert [(r.success, r.error_code, r.attempt) for r in rows] == [
        (False, "invalid_output", 1),
        (True, None, 2),
    ]
    assert rows[0].input_tokens == 10  # an invalid answer still used tokens


def test_schema_rejection_names_the_field_but_never_quotes_the_output(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success(content={"echo": "LEAKY-TEXT"}), Success())
    ping(make_gateway(a))
    message = a.requests[1].user
    assert "ok" in message and "Field required" in message
    assert "LEAKY-TEXT" not in message


def test_still_invalid_after_the_repair_gives_incomplete_without_fallback(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success(content="nope"))
    b = provider_factory("b", Success())
    result = ping(make_gateway(a, b))

    assert result.status is AiStatus.INCOMPLETE and result.data is None
    assert result.detail and "Invalid JSON" in result.detail
    assert (result.provider, result.attempts) == ("a", 2)
    assert b.calls == 0
    assert [r.success for r in log_rows(engine)] == [False, False]


def test_repair_message_survives_a_retry(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory(
        "a",
        Success(content="nope"),
        Failure(ErrorKind.RATE_LIMITED, retry_after=1.0),
        Success(),
    )
    assert ping(make_gateway(a)).ok
    assert all("rejected" in request.user for request in a.requests[1:])


def test_extra_fields_in_the_output_are_ignored(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success(content={"ok": True, "echo": "x", "bonus": 1}))
    assert ping(make_gateway(a)).data == ConnectionTestOutput(ok=True, echo="x")


def test_the_json_schema_is_sent_to_the_provider(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success())
    ping(make_gateway(a))
    request = a.requests[0]
    assert set(request.json_schema["properties"]) == {"ok", "echo"}  # type: ignore[arg-type]
    assert request.max_output_tokens == 100


def test_programming_errors_raise_before_any_call(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory, engine
) -> None:
    a = provider_factory("a", Success())
    gateway = make_gateway(a)

    with pytest.raises(UnknownTask):
        gateway.generate_json("no_such_task", {}, ConnectionTestOutput)
    with pytest.raises(SchemaMismatch):
        gateway.generate_json("connection_test", {"text": "x"}, AiOutput)
    with pytest.raises(InputTooLong):
        gateway.generate_json("connection_test", {"text": "x" * 201}, ConnectionTestOutput)

    assert a.calls == 0 and log_rows(engine) == []
