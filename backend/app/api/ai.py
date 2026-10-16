"""AI endpoints for the settings page: provider state, credentials, connection test, usage (D-064).

Keys are written to `.env` (never to the database), the settings and the gateway are reloaded, and
nothing that comes back to the browser contains a key, a fragment of a key or the Ollama address.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.ai.redact import clean_message
from app.ai.types import Capability, UnknownProvider
from app.api.errors import api_error, require_database
from app.config import get_settings
from app.db.engine import get_engine
from app.db.event_log import record_event
from app.domain.events import AiCredentialChanged
from app.domain.settings_defaults import KNOWN_AI_PROVIDERS
from app.services import env_file
from app.services.ai_connection_test import (
    ConnectionTestReport,
    TestInProgress,
    run_connection_test,
)
from app.services.ai_usage import ai_usage_last_days
from app.services.demo_guard import is_demo

logger = logging.getLogger("app.api.ai")

router = APIRouter(prefix="/ai", tags=["ai"])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]

ENV_FILE_STATUS = {
    "invalid_credential": 422,
    "set_in_environment": 409,
    "env_file_locked": 409,
    "env_file_write_failed": 500,
}


# --- Response models ----------------------------------------------------------------------------


class ProviderState(BaseModel):
    name: str
    capabilities: list[str]
    configured: bool
    enabled: bool  # listed in the provider order
    available: bool  # configured, enabled, not cooling down, not misconfigured
    cooldown_until: datetime | None
    misconfigured: bool
    last_error: str | None
    models: dict[str, str]  # capability -> model name
    # Where the credential comes from: "environment" (a variable of the process, which takes
    # priority and blocks editing), "env_file" (editable) or "none".
    credential_source: Literal["env_file", "environment", "none"]
    credential_kind: Literal["api_key", "base_url"]


class AiStatusResponse(BaseModel):
    ai_off: bool  # the provider order is empty
    degraded: bool  # no provider can be called right now
    demo: bool  # writes are refused
    order: list[str]
    providers: list[ProviderState]


class CredentialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: SecretStr


class TestBody(BaseModel):
    __test__ = False  # not a pytest class

    model_config = ConfigDict(extra="forbid")

    provider: str


class TestResponse(BaseModel):
    __test__ = False

    provider: str
    status: Literal["ok", "incomplete", "unavailable"]
    reason: str | None
    model: str | None
    elapsed_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None
    http_status: int | None
    message: str | None
    detail_kind: Literal["none", "provider", "schema"]


class UsageRow(BaseModel):
    provider: str
    model: str
    requests: int
    successes: int
    errors: dict[str, int]
    input_tokens: int
    output_tokens: int
    avg_duration_ms: float | None


class UsageDay(BaseModel):
    day: str  # ISO date of the study day
    requests: int
    successes: int
    input_tokens: int
    output_tokens: int
    rows: list[UsageRow]


class UsageResponse(BaseModel):
    days: list[UsageDay]  # today first, empty days included


# --- Helpers -------------------------------------------------------------------------------------


def _check_provider(name: str) -> None:
    if name not in KNOWN_AI_PROVIDERS:
        raise api_error(404, "unknown_provider", "Unknown AI provider.")


def _refuse_in_demo(engine: Engine) -> None:
    if is_demo(get_settings(), engine):
        raise api_error(
            409, "demo_read_only", "The demo database is read-only for AI keys and provider order."
        )


def _provider_states(gateway: Gateway) -> list[ProviderState]:
    statuses = {status.name: status for status in gateway.status()}
    states = []
    for name in KNOWN_AI_PROVIDERS:
        status = statuses.get(name)
        provider = gateway.providers.get(name)
        if status is None or provider is None:
            continue
        variable = env_file.EDITABLE[name]
        in_environment = _in_environment(variable)
        if in_environment:
            source: Literal["env_file", "environment", "none"] = "environment"
        elif status.configured:
            source = "env_file"
        else:
            source = "none"
        states.append(
            ProviderState(
                name=name,
                capabilities=sorted(c.value for c in status.capabilities),
                configured=status.configured,
                enabled=status.enabled,
                available=status.available,
                cooldown_until=status.cooldown_until,
                misconfigured=status.misconfigured,
                last_error=status.last_error.value if status.last_error else None,
                models={
                    capability.value: provider.model_for(capability)
                    for capability in Capability
                    if capability in provider.capabilities
                },
                credential_source=source,
                credential_kind="base_url" if name == "ollama" else "api_key",
            )
        )
    return states


def _in_environment(variable: str) -> bool:
    try:
        env_file.ensure_not_in_environment(variable)
    except env_file.EnvFileError:
        return True
    return False


def _state_of(gateway: Gateway, name: str) -> ProviderState:
    return next(state for state in _provider_states(gateway) if state.name == name)


def _record_credential_event(engine: Engine, name: str, action: Literal["set", "removed"]) -> None:
    """The file is already changed: a failure here is logged (masked), not turned into an error."""
    try:
        with Session(engine) as session:
            record_event(session, AiCredentialChanged(provider=name, action=action))
            session.commit()
    except Exception as exc:  # database missing, busy or not migrated
        message = clean_message(str(exc), get_settings().secret_values(), 200)
        logger.warning("ai.credential_changed not recorded (%s): %s", type(exc).__name__, message)


def _change_credential(
    name: str, value: str | None, gateway: Gateway, engine: Engine
) -> ProviderState:
    _check_provider(name)
    _refuse_in_demo(engine)

    def reload() -> None:
        get_settings.cache_clear()
        gateway.reload()

    try:
        update = env_file.update_credential(name, value, after_write=reload)
    except env_file.EnvFileError as exc:
        raise api_error(ENV_FILE_STATUS.get(exc.code, 500), exc.code, exc.message) from None
    if update.changed:
        _record_credential_event(engine, name, "removed" if value is None else "set")
    return _state_of(gateway, name)


# --- Routes --------------------------------------------------------------------------------------


@router.get("/status", response_model=AiStatusResponse)
def ai_status(gateway: GatewayDep, engine: EngineDep) -> AiStatusResponse:
    order = gateway.provider_order()
    providers = _provider_states(gateway)
    return AiStatusResponse(
        ai_off=not order,
        degraded=not any(provider.available for provider in providers),
        demo=is_demo(get_settings(), engine),
        order=order,
        providers=providers,
    )


@router.put("/providers/{name}/credential", response_model=ProviderState)
def put_credential(
    name: str, body: CredentialBody, gateway: GatewayDep, engine: EngineDep
) -> ProviderState:
    return _change_credential(name, body.value.get_secret_value(), gateway, engine)


@router.delete("/providers/{name}/credential", response_model=ProviderState)
def delete_credential(name: str, gateway: GatewayDep, engine: EngineDep) -> ProviderState:
    return _change_credential(name, None, gateway, engine)


@router.post("/test", response_model=TestResponse)
def test_connection(body: TestBody, gateway: GatewayDep, engine: EngineDep) -> TestResponse:
    # No database session is open here: the call can last a minute (D-038).
    _check_provider(body.provider)
    _refuse_in_demo(engine)
    try:
        report = run_connection_test(
            gateway, lambda: Session(engine), body.provider, get_settings().secret_values
        )
    except TestInProgress:
        raise api_error(
            409, "test_in_progress", "A test of this provider is already running."
        ) from None
    except UnknownProvider:
        raise api_error(404, "unknown_provider", "Unknown AI provider.") from None
    return _test_response(report)


def _test_response(report: ConnectionTestReport) -> TestResponse:
    return TestResponse(
        provider=report.provider,
        status=report.status.value,
        reason=report.reason.value if report.reason else None,
        model=report.model,
        elapsed_ms=report.elapsed_ms,
        input_tokens=report.input_tokens,
        output_tokens=report.output_tokens,
        error_code=report.error_code,
        http_status=report.http_status,
        message=report.message,
        detail_kind=report.detail_kind,
    )


@router.get("/usage", response_model=UsageResponse, dependencies=[Depends(require_database)])
def ai_usage(engine: EngineDep, days: Annotated[int, Query(ge=1, le=90)] = 7) -> UsageResponse:
    with Session(engine) as session:
        session.execute(text("PRAGMA query_only = ON"))
        try:
            usage = ai_usage_last_days(session, datetime.now(UTC), days)
        finally:
            session.rollback()
            # The connection goes back to the pool: leave it writable for the next request.
            session.execute(text("PRAGMA query_only = OFF"))
            session.rollback()
    return UsageResponse(
        days=[
            UsageDay(
                day=day.day.isoformat(),
                requests=day.requests,
                successes=day.successes,
                input_tokens=day.input_tokens,
                output_tokens=day.output_tokens,
                rows=[UsageRow(**vars(row)) for row in day.rows],
            )
            for day in usage
        ]
    )
