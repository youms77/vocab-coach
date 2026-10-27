"""The `pronunciation_assessment` capability of the gateway (M6.c1, D-212)."""

from collections.abc import Callable

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.schemas.pronunciation import PronunciationAssessmentOutput
from app.ai.types import AiStatus, AudioClip, Capability, ErrorKind, UnavailableReason
from tests.ai.conftest import FakeClock, log_rows, ping
from tests.audio_support import wav

OUTPUT = PronunciationAssessmentOutput(status="ok", accuracy=80, pronunciation=75)
CLIP = AudioClip(data=wav(), filename="take.wav", content_type="audio/wav")
PA = Capability.PRONUNCIATION_ASSESSMENT


def _azure(provider_factory: Callable[..., FakeProvider], *script, **kwargs) -> FakeProvider:
    return provider_factory("azure", *script, capabilities=[PA], **kwargs)


def _assess(gateway: Gateway, **kwargs):
    return gateway.assess_pronunciation(CLIP, reference_text="I think so.", **kwargs)


def test_azure_is_used_although_it_is_not_in_the_provider_order(make_gateway, provider_factory):
    azure = _azure(provider_factory, Success(content="", assessment=OUTPUT))
    gateway = make_gateway(azure, order=["gemini", "groq"])
    result = _assess(gateway)
    assert result.status is AiStatus.OK and result.data == OUTPUT
    assert result.provider == "azure" and result.prompt_version is None
    [request] = azure.assessments
    assert request.reference_text == "I think so." and request.language == "en-US"
    assert request.timeout_s <= 30.0


def test_one_journal_row_per_request(engine, make_gateway, provider_factory):
    gateway = make_gateway(_azure(provider_factory, Success(content="", assessment=OUTPUT)))
    _assess(gateway)
    [row] = log_rows(engine)
    assert (row.provider, row.task, row.success) == ("azure", "pronunciation_assessment", True)
    assert row.prompt_version is None and row.error_code is None


def test_an_unconfigured_provider_is_not_called_and_leaves_no_row(
    engine, make_gateway, provider_factory
):
    azure = _azure(provider_factory, configured=False)
    result = _assess(make_gateway(azure))
    assert result.status is AiStatus.UNAVAILABLE
    assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED
    assert azure.calls == 0 and log_rows(engine) == []


def test_a_cooldown_is_respected(make_gateway, provider_factory, clock: FakeClock):
    azure = _azure(provider_factory, Failure(ErrorKind.QUOTA_EXHAUSTED, status_code=429))
    gateway = make_gateway(azure)
    first = _assess(gateway)
    assert first.status is AiStatus.UNAVAILABLE and first.reason is UnavailableReason.QUOTA
    assert azure.calls == 1
    again = _assess(gateway)
    assert again.status is AiStatus.UNAVAILABLE and azure.calls == 1  # cooling down: no request
    status = next(s for s in gateway.status() if s.name == "azure")
    assert status.cooldown_until is not None and not status.available
    gateway.reload()  # the owner changed the key: the mark is forgotten
    _assess(gateway)
    assert azure.calls == 2


def test_a_transient_error_is_retried(make_gateway, provider_factory):
    azure = _azure(
        provider_factory,
        Failure(ErrorKind.TRANSIENT, status_code=503),
        Success(content="", assessment=OUTPUT),
    )
    result = _assess(make_gateway(azure))
    assert result.status is AiStatus.OK and result.attempts == 2


def test_a_response_without_assessment_is_invalid_output(engine, make_gateway, provider_factory):
    azure = _azure(provider_factory, Success(content=""))
    result = _assess(make_gateway(azure))
    assert result.status is AiStatus.INCOMPLETE
    assert log_rows(engine)[0].error_code == "invalid_output"


def test_a_text_call_never_picks_azure_even_if_the_order_names_it(make_gateway, provider_factory):
    azure = _azure(provider_factory)
    gateway = make_gateway(azure, order=["azure"])
    assert ping(gateway).reason is UnavailableReason.NO_PROVIDER_CONFIGURED
    assert azure.calls == 0


def test_a_text_provider_is_never_picked_for_assessment(make_gateway, provider_factory):
    text = provider_factory("gemini", Success())
    result = _assess(make_gateway(text, order=["gemini"]))
    assert result.reason is UnavailableReason.NO_PROVIDER_CONFIGURED and text.calls == 0


def test_status_lists_azure_as_enabled_without_the_order(make_gateway, provider_factory):
    gateway = make_gateway(_azure(provider_factory), order=[])
    [status] = gateway.status()
    assert status.enabled and status.available and status.capabilities == {PA}


def test_the_key_is_masked_in_the_journal(engine, make_gateway, provider_factory):
    key = "az_secret_0123456789abcdef"
    azure = _azure(provider_factory, Failure(ErrorKind.AUTH, f"bad key {key}", status_code=401))
    gateway = make_gateway(azure, secrets=[key])
    result = _assess(gateway)
    assert key not in (result.detail or "")
    assert all(key not in (row.error_message or "") for row in log_rows(engine))
