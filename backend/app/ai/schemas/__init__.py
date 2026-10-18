"""Output schemas of the AI tasks. The gateway always validates provider output against them."""

from pydantic import BaseModel, ConfigDict


class AiOutput(BaseModel):
    """Base class of every task output. An unexpected extra field is not an error."""

    model_config = ConfigDict(extra="ignore")


class TranscriptionSegment(AiOutput):
    start: float | None = None
    end: float | None = None
    no_speech_prob: float | None = None
    avg_logprob: float | None = None


class TranscriptionOutput(AiOutput):
    text: str
    # The provider's measure of the audio, and its segments, when it gives them (D-171).
    duration_s: float | None = None
    segments: list[TranscriptionSegment] = []
