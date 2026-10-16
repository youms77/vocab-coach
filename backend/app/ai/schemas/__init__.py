"""Output schemas of the AI tasks. The gateway always validates provider output against them."""

from pydantic import BaseModel, ConfigDict


class AiOutput(BaseModel):
    """Base class of every task output. An unexpected extra field is not an error."""

    model_config = ConfigDict(extra="ignore")


class TranscriptionOutput(AiOutput):
    text: str
