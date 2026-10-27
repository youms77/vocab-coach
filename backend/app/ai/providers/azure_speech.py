"""Azure AI Speech adapter: pronunciation assessment, short-audio REST API (M6.c1, D-213).

Facts read on Microsoft Learn on 2026-10-24 (sources and unverified points in D-211):
- `POST https://{region}.stt.speech.microsoft.com` + `PATH` + `?language=en-US&format=detailed`,
  the regional host of Microsoft's own REST sample; the key goes in the `Ocp-Apim-Subscription-Key`
  header only;
- the audio is WAV PCM 16 kHz mono or OGG Opus (webm, m4a and mp3 are refused), 30 s at most when
  pronunciation assessment is on;
- the assessment is asked for in the `Pronunciation-Assessment` header: base64 of a UTF-8 JSON;
- the free F0 tier gives 5 audio hours a month and one concurrent request; whether pronunciation
  assessment is included in F0 is NOT confirmed by the pricing page.
The answer was never observed live: the REST page puts the scores flat in `NBest[0]`, the SDK JSON
nests them under `PronunciationAssessment`. The parser accepts both and ignores what it does not
understand. No SDK and no new dependency (D-049).
"""

import base64
import json
import re
from typing import Any

from app.ai.http import HttpResponse, post
from app.ai.providers.common import as_number, parse_retry_after
from app.ai.redact import clean_message
from app.ai.schemas.pronunciation import (
    PhonemeScore,
    PronunciationAssessmentOutput,
    WordScore,
)
from app.ai.types import (
    Capability,
    ErrorKind,
    PronunciationRequest,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    TranscriptionRequest,
)
from app.domain import pronunciation as pa

MODEL = "pa-rest-v1"
PATH = "/speech/recognition/conversation/cognitiveservices/v1"
REGION_PATTERN = re.compile(r"^[a-z0-9]{2,40}$")
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
_MESSAGE_LIMIT = 300
_SILENCE_STATUSES = frozenset({"NoMatch", "InitialSilenceTimeout", "BabbleTimeout"})
_TICKS_PER_SECOND = 10_000_000  # Offset and Duration are in units of 100 ns
_TICKS_PER_MS = 10_000
_CONTENT_TYPES = {
    "wav": "audio/wav; codecs=audio/pcm; samplerate=16000",
    "ogg": "audio/ogg; codecs=opus",
}


def default_base_url(region: str) -> str:
    return f"https://{region}.stt.speech.microsoft.com"


class AzureSpeechProvider:
    name = "azure"
    capabilities = frozenset({Capability.PRONUNCIATION_ASSESSMENT})

    def __init__(self, api_key: str | None, region: str | None, *, base_url: str | None = None):
        self._api_key = (api_key or "").strip() or None
        self._region = (region or "").strip().lower() or None
        # Tests aim the adapter at a loopback server; the real URL is built from the region.
        self._base_url = base_url.rstrip("/") if base_url else None

    @classmethod
    def from_settings(cls, settings: Any) -> "AzureSpeechProvider":
        key = settings.azure_speech_key
        return cls(
            key.get_secret_value() if key is not None else None, settings.azure_speech_region
        )

    def __repr__(self) -> str:  # never the key
        return f"AzureSpeechProvider(region={self._region!r}, configured={self.is_configured()})"

    @property
    def region(self) -> str | None:
        return self._region

    def is_configured(self) -> bool:
        return self._api_key is not None and self._region is not None

    def model_for(self, capability: Capability) -> str:
        return MODEL

    # Only pronunciation assessment is offered; the gateway never selects Azure for these.

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        raise ProviderError(ErrorKind.BAD_REQUEST, "Azure Speech does not generate text")

    def transcribe(self, request: TranscriptionRequest) -> ProviderResponse:
        raise ProviderError(ErrorKind.BAD_REQUEST, "Azure Speech is used for assessment only")

    # --- Pronunciation assessment ------------------------------------------------------------

    def assess_pronunciation(self, request: PronunciationRequest) -> ProviderResponse:
        key = self._api_key
        if key is None or self._region is None:
            raise ProviderError(ErrorKind.AUTH, "the Azure Speech key or region is not configured")
        url = self._url(request.language)
        clip = request.audio
        extension = clip.filename.rpartition(".")[2] if "." in clip.filename else ""
        kind = pa.audio_kind(clip.data, extension)
        if kind is None:
            raise ProviderError(
                ErrorKind.BAD_REQUEST,
                "Azure reads only WAV PCM 16 kHz mono and OGG Opus mono; this clip is neither",
            )
        seconds = pa.audio_duration_s(clip.data)
        if seconds is not None and seconds > pa.MAX_ASSESSMENT_SECONDS:
            raise ProviderError(
                ErrorKind.BAD_REQUEST,
                f"the clip lasts {seconds:.1f} s; pronunciation assessment takes "
                f"{pa.MAX_ASSESSMENT_SECONDS:.0f} s at most",
            )
        reference = request.reference_text.strip()
        if not reference:
            raise ProviderError(ErrorKind.BAD_REQUEST, "the reference text is empty")
        response = post(
            url,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": _CONTENT_TYPES[kind],
                "Accept": "application/json",
                "Pronunciation-Assessment": _assessment_header(reference),
            },
            body=clip.data,
            timeout_s=request.timeout_s,
        )
        if response.status != 200:
            raise self.translate_error(response)
        return ProviderResponse(text="", model=MODEL, assessment=self.parse(response))

    def _url(self, language: str) -> str:
        region = self._region or ""
        if not REGION_PATTERN.match(region):
            raise ProviderError(
                ErrorKind.BAD_REQUEST, "VOCAB_AZURE_SPEECH_REGION is not a valid region"
            )
        if not _LANGUAGE.match(language):
            raise ProviderError(ErrorKind.BAD_REQUEST, "the language code is not valid")
        base = self._base_url or default_base_url(region)
        return f"{base}{PATH}?language={language}&format=detailed"

    # --- Answers -----------------------------------------------------------------------------

    def parse(self, response: HttpResponse) -> PronunciationAssessmentOutput:
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the Azure answer is not a JSON object")
        status = data.get("RecognitionStatus")
        if status in _SILENCE_STATUSES:
            return PronunciationAssessmentOutput(status="silence", duration_s=_seconds(data))
        if status == "Error":
            raise ProviderError(ErrorKind.TRANSIENT, "Azure reported a recognition error")
        if status != "Success":
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the Azure answer has no usable status")
        best = data.get("NBest")
        best = best[0] if isinstance(best, list) and best else None
        if not isinstance(best, dict):
            raise ProviderError(ErrorKind.INVALID_OUTPUT, "the Azure answer has no result")
        return PronunciationAssessmentOutput(
            status="ok",
            accuracy=_score(best, "AccuracyScore"),
            fluency=_score(best, "FluencyScore"),
            completeness=_score(best, "CompletenessScore"),
            pronunciation=_score(best, "PronScore"),
            words=_words(best.get("Words")),
            duration_s=_seconds(data),
        )

    def translate_error(self, response: HttpResponse) -> ProviderError:
        """Column "Azure" of the error table (D-050, D-213)."""
        status = response.status
        detail = self._detail(response)
        lowered = detail.lower()
        retry_after = parse_retry_after(response.header("retry-after"))
        if status in (403, 429) and "quota" in lowered:
            # How Azure words "the monthly F0 hours are used up" is not documented: a heuristic.
            kind = ErrorKind.QUOTA_EXHAUSTED
        elif status == 401 or status == 403:
            kind = ErrorKind.AUTH
            detail = (
                f"Azure rejected the key or the region, or the request is not permitted: {detail}"
            )
        elif status == 429:
            kind = ErrorKind.RATE_LIMITED
        elif status == 408 or status >= 500:
            kind = ErrorKind.TRANSIENT
        else:
            kind = ErrorKind.BAD_REQUEST
        return ProviderError(kind, detail, retry_after=retry_after, status_code=status)

    def _detail(self, response: HttpResponse) -> str:
        """The service's own message, masked and cut; `HTTP <status>` when there is none."""
        data = response.json()
        text: Any = None
        if isinstance(data, dict):
            error = data.get("error")
            candidates = [
                error.get("message") if isinstance(error, dict) else error,
                data.get("message"),
                data.get("Message"),
            ]
            text = next((c for c in candidates if isinstance(c, str) and c.strip()), None)
        elif data is None:
            raw = response.body[:500].decode("utf-8", errors="replace").strip()
            text = raw or None
        if not isinstance(text, str) or not text.strip():
            return f"HTTP {response.status}"
        return self.mask(text)

    def mask(self, text: str) -> str:
        secrets = [self._api_key] if self._api_key else []
        return clean_message(text, secrets, _MESSAGE_LIMIT)


# --- Pure helpers ---------------------------------------------------------------------------------


def _assessment_header(reference_text: str) -> str:
    parameters = {
        "ReferenceText": reference_text,
        "GradingSystem": "HundredMark",
        "Granularity": "Phoneme",
        "Dimension": "Comprehensive",
        "EnableMiscue": "True",
        "PhonemeAlphabet": "IPA",
    }
    raw = json.dumps(parameters, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _score(node: dict[str, Any], key: str) -> float | None:
    """A 0-100 score, flat (REST page) or under `PronunciationAssessment` (SDK JSON)."""
    value = node.get(key)
    if value is None:
        nested = node.get("PronunciationAssessment")
        value = nested.get(key) if isinstance(nested, dict) else None
    number = as_number(value)
    return number if number is not None and 0 <= number <= 100 else None


def _seconds(data: dict[str, Any]) -> float | None:
    ticks = as_number(data.get("Duration"))
    return ticks / _TICKS_PER_SECOND if ticks is not None and ticks >= 0 else None


def _millis(value: Any) -> int | None:
    ticks = as_number(value)
    return round(ticks / _TICKS_PER_MS) if ticks is not None and ticks >= 0 else None


def _words(raw: Any) -> list[WordScore]:
    words = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("Word"), str):
            continue
        nested = item.get("PronunciationAssessment")
        error = item.get("ErrorType")
        if error is None and isinstance(nested, dict):
            error = nested.get("ErrorType")
        words.append(
            WordScore(
                word=item["Word"],
                accuracy=_score(item, "AccuracyScore"),
                error_type=error if isinstance(error, str) else None,
                offset_ms=_millis(item.get("Offset")),
                duration_ms=_millis(item.get("Duration")),
                phonemes=_phonemes(item.get("Phonemes")),
            )
        )
    return words


def _phonemes(raw: Any) -> list[PhonemeScore]:
    return [
        PhonemeScore(phoneme=item["Phoneme"], accuracy=_score(item, "AccuracyScore"))
        for item in (raw if isinstance(raw, list) else [])
        if isinstance(item, dict) and isinstance(item.get("Phoneme"), str)
    ]
