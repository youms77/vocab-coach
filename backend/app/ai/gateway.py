"""The AI gateway: one entry point for every AI call of the application.

Synchronous (services are synchronous, D-023; FastAPI runs sync routes in a thread pool). `clock`,
`sleep` and `rng` are injectable so tests never wait. Expected failures are not exceptions: the
result carries a status (`ok`, `incomplete`, `unavailable` + reason). Exceptions are for
programming errors (unknown task, input too long...), raised before any call.

RULE FOR CALLERS (D-038): call the AI first, then write the results in your own short transaction.
Never keep a write transaction open while waiting for a provider.
"""

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.health import ProviderHealth
from app.ai.journal import CallJournal, CallRecord
from app.ai.policy import (
    LOG_MESSAGE_MAX,
    TOTAL_BUDGET_S,
    Action,
    RandomLike,
    decide,
    default_rng,
    unavailable_reason,
)
from app.ai.prompt_loader import PromptLibrary
from app.ai.providers import PronunciationProvider, Provider, build_providers
from app.ai.redact import clean_message
from app.ai.schemas import AiOutput, TranscriptionOutput, TranscriptionSegment
from app.ai.schemas.pronunciation import PronunciationAssessmentOutput
from app.ai.tasks import PRONUNCIATION_TASK, TASKS, TRANSCRIPTION_TASK, TaskSpec
from app.ai.types import (
    AiResult,
    AiStatus,
    AudioClip,
    Capability,
    ErrorKind,
    InputTooLong,
    PronunciationRequest,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    SchemaMismatch,
    TranscriptionRequest,
    UnavailableReason,
    UnknownProvider,
    UnknownTask,
)
from app.db.base import utcnow
from app.domain.settings_defaults import default_for

logger = logging.getLogger("app.ai")

ProviderMap = Mapping[str, Provider]
# (provider, repair message or None, request timeout) -> response
type SendFn = Callable[[Provider, str | None, float], ProviderResponse]
# provider response -> (validated data, "") or (None, validation message)
type ParseFn = Callable[[ProviderResponse], tuple[Any, str]]


class Gateway:
    def __init__(
        self,
        providers: ProviderMap | Callable[[], ProviderMap],
        *,
        session_factory: Callable[[], Session],
        provider_order: Callable[[], Sequence[str]] | None = None,
        secrets: Callable[[], Sequence[str]] | None = None,
        clock: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], None] = time.sleep,
        rng: RandomLike | None = None,
        prompts: PromptLibrary | None = None,
        tasks: Mapping[str, TaskSpec] | None = None,
    ) -> None:
        self._providers_source = providers
        self._providers: ProviderMap = providers() if callable(providers) else providers
        self._session_factory = session_factory
        self._order_source = provider_order or self._order_from_settings
        self._last_order: list[str] = list(default_for("ai_provider_order"))
        self._secrets = secrets or (lambda: ())
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or default_rng()
        self._prompts = prompts or PromptLibrary()
        self._tasks = tasks if tasks is not None else TASKS
        self._health = ProviderHealth()
        self._journal = CallJournal(session_factory, self._mask)

    # --- Public API ----------------------------------------------------------------------------

    def generate_json[T: AiOutput](
        self,
        task: str,
        inputs: Mapping[str, str],
        schema: type[T],
        *,
        pin_provider: str | None = None,
        validation_context: Mapping[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> AiResult[T]:
        """Run a registered task and return its output validated against `schema`.

        `validation_context` is handed to Pydantic (`info.context` in the schema's validators), so
        business rules that depend on the request (the expected terms of a batch...) trigger the
        repair like any schema error. `max_output_tokens` lowers the task's ceiling for this call
        (a one-term batch need not reserve the tokens of five); it can never raise it.
        """
        spec = self._tasks.get(task)
        if spec is None:
            raise UnknownTask(f"unknown AI task {task!r}")
        if schema is not spec.output_schema:
            raise SchemaMismatch(
                f"{task} produces {spec.output_schema.__name__}, not {schema.__name__}"
            )
        if sum(len(value) for value in inputs.values()) > spec.max_input_chars:
            raise InputTooLong(f"{task}: inputs exceed {spec.max_input_chars} characters")
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        output_tokens = min(max_output_tokens or spec.max_output_tokens, spec.max_output_tokens)
        context = dict(validation_context) if validation_context is not None else None
        prompt = self._prompts.get(spec.name, spec.prompt_version).render(dict(inputs))
        json_schema = schema.model_json_schema()

        def send(provider: Provider, repair: str | None, timeout_s: float) -> ProviderResponse:
            user = prompt.user
            if repair:
                user += (
                    f"\n\nYour previous answer was rejected: {repair}\n"
                    "Reply again with JSON that fixes this."
                )
            request = ProviderRequest(
                system=prompt.system,
                user=user,
                json_schema=json_schema,
                timeout_s=timeout_s,
                max_output_tokens=output_tokens,
            )
            return provider.generate_json(request)

        return self._run(
            task=spec.name,
            prompt_label=spec.prompt_label,
            capability=Capability.TEXT,
            timeout_s=spec.timeout_s,
            pin=pin_provider,
            send=send,
            parse=lambda response: _validate(schema, response.text, context),
        )

    def transcribe(
        self, audio: AudioClip, *, language: str = "en", pin_provider: str | None = None
    ) -> AiResult[TranscriptionOutput]:
        """Speech to text, through the same retry / fallback / journal path. The output carries the
        provider's audio duration and segments when it gives them (D-171). There is no prompt: a
        target sentence would pull the recognition towards it (D-172)."""

        def send(provider: Provider, repair: str | None, timeout_s: float) -> ProviderResponse:
            return provider.transcribe(
                TranscriptionRequest(audio=audio, language=language, timeout_s=timeout_s)
            )

        return self._run(
            task=TRANSCRIPTION_TASK,
            prompt_label=None,
            capability=Capability.TRANSCRIPTION,
            timeout_s=60.0,
            pin=pin_provider,
            send=send,
            parse=lambda response: (_transcription_output(response), ""),
        )

    def assess_pronunciation(
        self,
        audio: AudioClip,
        *,
        reference_text: str,
        language: str = "en-US",
        pin_provider: str | None = None,
    ) -> AiResult[PronunciationAssessmentOutput]:
        """Score a recording against `reference_text`, word by word (Azure, M6.c1). Same retry,
        budget and journal path as the other calls. `ai_provider_order` does not apply: every
        provider holding the capability is tried, cooldowns respected (D-212). The reference text
        is required here (D-172 is about transcription: assessing against the target is the point).
        """

        def send(provider: Provider, repair: str | None, timeout_s: float) -> ProviderResponse:
            assessor: PronunciationProvider = provider  # type: ignore[assignment]
            return assessor.assess_pronunciation(
                PronunciationRequest(
                    audio=audio,
                    reference_text=reference_text,
                    language=language,
                    timeout_s=timeout_s,
                )
            )

        def parse(response: ProviderResponse) -> tuple[Any, str]:
            if response.assessment is None:
                return None, "the provider returned no assessment"
            return response.assessment, ""

        return self._run(
            task=PRONUNCIATION_TASK,
            prompt_label=None,
            capability=Capability.PRONUNCIATION_ASSESSMENT,
            timeout_s=30.0,
            pin=pin_provider,
            send=send,
            parse=parse,
        )

    def status(self) -> list[ProviderStatus]:
        """Health of every known provider. Never contains a key."""
        now = self._clock()
        order = self._current_order()
        result = []
        for name, provider in self._providers.items():
            health = self._health.snapshot(name, now)
            configured = provider.is_configured()
            enabled = name in order or _outside_order(provider)
            result.append(
                ProviderStatus(
                    name=name,
                    capabilities=provider.capabilities,
                    configured=configured,
                    enabled=enabled,
                    available=configured
                    and enabled
                    and not health.misconfigured
                    and health.cooldown_until is None,
                    cooldown_until=health.cooldown_until,
                    misconfigured=health.misconfigured,
                    last_error=health.last_error,
                )
            )
        return result

    @property
    def providers(self) -> ProviderMap:
        """The providers currently in use (read-only view, for `status` screens)."""
        return self._providers

    def provider_order(self) -> list[str]:
        """The `ai_provider_order` the next call would use."""
        return self._current_order()

    def reload(self) -> None:
        """Forget cooldowns and "misconfigured" marks, and rebuild the providers when a factory was
        given (after the user changed a key, for instance)."""
        self._health.reset()
        if callable(self._providers_source):
            self._providers = self._providers_source()

    # --- Core ----------------------------------------------------------------------------------

    def _run(
        self,
        *,
        task: str,
        prompt_label: str | None,
        capability: Capability,
        timeout_s: float,
        pin: str | None,
        send: SendFn,
        parse: ParseFn,
    ) -> AiResult[Any]:
        if pin is not None and pin not in self._providers:
            raise UnknownProvider(f"unknown AI provider {pin!r}")
        started = self._clock()
        candidates, failures = self._select(capability, pin, started)
        if not candidates and not failures:
            logger.info("%s: no provider configured for %s", task, capability.value)
            return self._unavailable(
                UnavailableReason.NO_PROVIDER_CONFIGURED, prompt_label=prompt_label
            )

        attempts = 0
        budget_exhausted = False
        fallback_from: str | None = None
        last: tuple[str, str, str] | None = None  # provider, model, masked message
        last_call_id: int | None = None

        for provider in candidates:
            model = provider.model_for(capability)
            failed_attempts = 0  # transport failures on this provider
            provider_attempt = 0
            repair: str | None = None
            while True:
                remaining = TOTAL_BUDGET_S - (self._clock() - started).total_seconds()
                if remaining <= 0:
                    budget_exhausted = True
                    break
                provider_attempt += 1
                attempts += 1
                t0 = self._clock()
                response: ProviderResponse | None = None
                data: Any = None
                error_code: str | None = None
                # A provider may need longer than the task's timeout (a local model loading); never
                # more than what is left of the budget.
                floor = getattr(provider, "min_request_timeout_s", 0.0)
                try:
                    response = send(provider, repair, min(max(timeout_s, floor), remaining))
                except ProviderError as exc:
                    error = ProviderError(
                        exc.kind,
                        self._clean(exc.message),
                        retry_after=exc.retry_after,
                        status_code=exc.status_code,
                    )
                except Exception as exc:  # a bug in an adapter must not reach the user
                    error_code = f"unexpected:{type(exc).__name__}"
                    error = ProviderError(ErrorKind.BAD_REQUEST, self._clean(str(exc)))
                    logger.warning(
                        "%s: unexpected %s from %s: %s",
                        task,
                        type(exc).__name__,
                        provider.name,
                        error.message,
                    )
                else:
                    data, problem = parse(response)
                    error = (
                        None
                        if data is not None
                        else ProviderError(ErrorKind.INVALID_OUTPUT, self._clean(problem))
                    )
                duration_ms = int((self._clock() - t0).total_seconds() * 1000)
                last_call_id = self._journal.record(
                    CallRecord(
                        started_at=t0,
                        provider=provider.name,
                        model=response.model if response is not None else model,
                        task=task,
                        prompt_version=prompt_label,
                        input_tokens=response.input_tokens if response is not None else None,
                        output_tokens=response.output_tokens if response is not None else None,
                        duration_ms=duration_ms,
                        success=error is None,
                        http_status=error.status_code if error is not None else None,
                        error_code=None if error is None else (error_code or error.kind.value),
                        error_message=error.message if error is not None else None,
                        attempt=provider_attempt,
                        fallback_from=fallback_from,
                    )
                )
                final_model = response.model if response is not None else model
                if error is None:
                    assert response is not None  # noqa: S101 (narrowing for the type checker)
                    self._health.record_success(provider.name)
                    return AiResult(
                        status=AiStatus.OK,
                        data=data,
                        provider=provider.name,
                        model=final_model,
                        prompt_version=prompt_label,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        attempts=attempts,
                        call_id=last_call_id,
                    )

                last = (provider.name, final_model, error.message)
                if error.kind in (ErrorKind.RATE_LIMITED, ErrorKind.TRANSIENT):
                    failed_attempts += 1
                decision = decide(
                    error,
                    failed_attempts=failed_attempts,
                    repaired=repair is not None,
                    rng=self._rng,
                )
                logger.info(
                    "%s: %s attempt %d failed (%s) -> %s",
                    task,
                    provider.name,
                    provider_attempt,
                    error.kind.value,
                    decision.action.value,
                )
                if error.kind is not ErrorKind.INVALID_OUTPUT:
                    cooldown_until = (
                        self._clock() + decision.cooldown if decision.cooldown else None
                    )
                    self._health.record_failure(
                        provider.name,
                        error.kind,
                        cooldown_until=cooldown_until,
                        misconfigured=decision.misconfigured,
                    )
                    if cooldown_until is not None:
                        logger.info(
                            "%s: %s in cooldown until %s", task, provider.name, cooldown_until
                        )

                if decision.action is Action.REPAIR:
                    repair = error.message
                    continue
                if decision.action is Action.STOP:
                    return AiResult(
                        status=AiStatus.INCOMPLETE,
                        detail=error.message,
                        provider=provider.name,
                        model=final_model,
                        prompt_version=prompt_label,
                        input_tokens=response.input_tokens if response else None,
                        output_tokens=response.output_tokens if response else None,
                        attempts=attempts,
                        call_id=last_call_id,
                    )
                if decision.action is Action.RETRY:
                    elapsed = (self._clock() - started).total_seconds()
                    if elapsed + decision.wait_s > TOTAL_BUDGET_S:
                        logger.info(
                            "%s: waiting %.1f s would exceed the budget", task, decision.wait_s
                        )
                        budget_exhausted = True
                        failures.append(error.kind)
                        break
                    logger.info(
                        "%s: waiting %.1f s before retrying %s",
                        task,
                        decision.wait_s,
                        provider.name,
                    )
                    self._sleep(decision.wait_s)
                    continue
                # FALLBACK
                failures.append(error.kind)
                fallback_from = provider.name
                break

        reason = unavailable_reason(failures, budget_exhausted=budget_exhausted)
        return self._unavailable(
            reason,
            prompt_label=prompt_label,
            provider=last[0] if last else None,
            model=last[1] if last else None,
            detail=last[2] if last else None,
            attempts=attempts,
            call_id=last_call_id,
        )

    def _select(
        self, capability: Capability, pin: str | None, now: datetime
    ) -> tuple[list[Provider], list[ErrorKind]]:
        """Providers to try, in order, and the failure kinds of those skipped (cooldown, auth)."""
        if pin is not None:
            names = [pin]
        elif capability in ORDERLESS_CAPABILITIES:
            names = [name for name, p in self._providers.items() if capability in p.capabilities]
        else:
            names = self._current_order()
        candidates: list[Provider] = []
        skipped: list[ErrorKind] = []
        for name in names:
            provider = self._providers.get(name)
            if provider is None or not provider.is_configured():
                continue
            if capability not in provider.capabilities:
                continue
            if pin is None:
                blocked = self._health.blocked_by(name, now)
                if blocked is not None:
                    skipped.append(blocked)
                    continue
            candidates.append(provider)
        return candidates, skipped

    def _current_order(self) -> list[str]:
        try:
            order = list(self._order_source())
        except Exception as exc:  # database busy or missing: keep working with the last order
            logger.warning("could not read ai_provider_order (%s)", type(exc).__name__)
            return self._last_order
        self._last_order = order
        return order

    def _order_from_settings(self) -> list[str]:
        from app.db.settings_store import get_setting

        with self._session_factory() as session:
            return list(get_setting(session, "ai_provider_order"))

    def _unavailable(
        self,
        reason: UnavailableReason,
        *,
        prompt_label: str | None,
        provider: str | None = None,
        model: str | None = None,
        detail: str | None = None,
        attempts: int = 0,
        call_id: int | None = None,
    ) -> AiResult[Any]:
        return AiResult(
            status=AiStatus.UNAVAILABLE,
            reason=reason,
            detail=detail,
            provider=provider,
            model=model,
            prompt_version=prompt_label,
            attempts=attempts,
            call_id=call_id,
        )

    def _clean(self, text: str) -> str:
        return clean_message(text, self._secrets(), LOG_MESSAGE_MAX)

    def _mask(self, text: str) -> str:
        return clean_message(text, self._secrets(), 1000)


# Capabilities whose providers are not listed in `ai_provider_order`: the setting that switches
# the feature on is checked by the service (D-212).
ORDERLESS_CAPABILITIES = frozenset({Capability.PRONUNCIATION_ASSESSMENT})


def _outside_order(provider: Provider) -> bool:
    return bool(provider.capabilities) and provider.capabilities <= ORDERLESS_CAPABILITIES


def _transcription_output(response: ProviderResponse) -> TranscriptionOutput:
    details = response.transcription
    if details is None:
        return TranscriptionOutput(text=response.text)
    return TranscriptionOutput(
        text=response.text,
        duration_s=details.duration_s,
        segments=[
            TranscriptionSegment(
                start=segment.start,
                end=segment.end,
                no_speech_prob=segment.no_speech_prob,
                avg_logprob=segment.avg_logprob,
            )
            for segment in details.segments
        ],
    )


def _validate[T: BaseModel](
    schema: type[T], text: str, context: dict[str, Any] | None = None
) -> tuple[T | None, str]:
    """Validate model output. The message never quotes the output itself (it is stored and sent back
    to the model): only locations and rule names."""
    try:
        return schema.model_validate_json(text, context=context), ""
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in err['loc']) or 'output'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        ]
        return None, "; ".join(problems[:5])


@lru_cache
def get_gateway() -> Gateway:
    """The application's gateway. Until M2.b adds the real providers it has none, so every call
    returns `unavailable(no_provider_configured)`: the app works in degraded mode."""
    from app.config import get_settings
    from app.db.engine import get_engine

    return Gateway(
        build_providers,
        session_factory=lambda: Session(get_engine(), expire_on_commit=False),
        secrets=lambda: get_settings().secret_values(),
    )
