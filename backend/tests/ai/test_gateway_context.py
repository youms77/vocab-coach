"""`validation_context` and the per-call `max_output_tokens` ceiling (M3.b, D-079)."""

from collections.abc import Callable

import pytest
from pydantic import ValidationInfo, field_validator

from app.ai.gateway import Gateway
from app.ai.providers.fake import FakeProvider, Success
from app.ai.schemas import AiOutput
from app.ai.tasks import TaskSpec
from app.ai.types import AiStatus

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]


class EchoMustMatch(AiOutput):
    ok: bool
    echo: str

    @field_validator("echo")
    @classmethod
    def echo_is_expected(cls, value: str, info: ValidationInfo) -> str:
        expected = (info.context or {}).get("expected")
        if expected is not None and value != expected:
            raise ValueError("echo is not the expected text")
        return value


TASKS = {
    "connection_test": TaskSpec(
        name="connection_test",
        prompt_version=1,
        output_schema=EchoMustMatch,
        max_input_chars=200,
        max_output_tokens=1000,
    )
}


def _call(gateway: Gateway, **kwargs: object):
    return gateway.generate_json("connection_test", {"text": "ping"}, EchoMustMatch, **kwargs)


def test_context_reaches_the_validators_and_a_violation_triggers_the_repair(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory(
        "a",
        Success(content={"ok": True, "echo": "wrong"}),
        Success(content={"ok": True, "echo": "ping"}),
    )
    result = _call(make_gateway(a, tasks=TASKS), validation_context={"expected": "ping"})
    assert result.ok and result.attempts == 2
    assert "echo is not the expected text" in a.requests[1].user


def test_without_context_the_same_output_is_accepted(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success(content={"ok": True, "echo": "wrong"}))
    assert _call(make_gateway(a, tasks=TASKS)).ok


def test_still_violated_after_the_repair_is_incomplete(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success(content={"ok": True, "echo": "wrong"}))
    result = _call(make_gateway(a, tasks=TASKS), validation_context={"expected": "ping"})
    assert result.status is AiStatus.INCOMPLETE


def test_max_output_tokens_lowers_the_ceiling_but_never_raises_it(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a", Success(content={"ok": True, "echo": "ping"}))
    gateway = make_gateway(a, tasks=TASKS)
    _call(gateway)
    _call(gateway, max_output_tokens=300)
    _call(gateway, max_output_tokens=5000)
    assert [r.max_output_tokens for r in a.requests] == [1000, 300, 1000]


def test_a_non_positive_ceiling_is_a_programming_error(
    provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    a = provider_factory("a")
    with pytest.raises(ValueError, match="max_output_tokens"):
        _call(make_gateway(a, tasks=TASKS), max_output_tokens=0)
    assert a.calls == 0
