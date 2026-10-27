"""Output of a pronunciation assessment (M6.c1). Built by the provider adapter, not parsed from
model text: the gateway still validates it like every other result."""

from typing import Literal

from pydantic import Field

from app.ai.schemas import AiOutput

Score = Field(default=None, ge=0, le=100)


class PhonemeScore(AiOutput):
    phoneme: str
    accuracy: float | None = Score


class WordScore(AiOutput):
    word: str
    accuracy: float | None = Score
    # Azure's `ErrorType` as sent (None, Omission, Insertion, Mispronunciation, and prosody
    # values); an unknown value is kept as is.
    error_type: str | None = None
    offset_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    phonemes: list[PhonemeScore] = []


class PronunciationAssessmentOutput(AiOutput):
    status: Literal["ok", "silence"]
    accuracy: float | None = Score
    fluency: float | None = Score
    completeness: float | None = Score
    pronunciation: float | None = Score
    words: list[WordScore] = []
    duration_s: float | None = Field(default=None, ge=0)
