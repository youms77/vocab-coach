"""Task registry. Each task pins its prompt version, so adding a prompt file never changes behaviour
silently. Adding a task = one prompt file + one schema class + one entry here; the gateway does
not change.
"""

from dataclasses import dataclass

from app.ai.policy import REQUEST_TIMEOUT_S
from app.ai.schemas import AiOutput
from app.ai.schemas.connection_test import ConnectionTestOutput

TRANSCRIPTION_TASK = "transcription"  # task name in `ai_call_log` for speech-to-text


@dataclass(frozen=True)
class TaskSpec:
    name: str
    prompt_version: int
    output_schema: type[AiOutput]
    max_input_chars: int  # total length of the input values, checked before any call
    max_output_tokens: int
    timeout_s: float = REQUEST_TIMEOUT_S

    @property
    def prompt_label(self) -> str:
        """Stored in results and in `ai_call_log.prompt_version`, e.g. `connection_test.v1`."""
        return f"{self.name}.v{self.prompt_version}"


TASKS: dict[str, TaskSpec] = {
    spec.name: spec
    for spec in (
        TaskSpec(
            name="connection_test",
            prompt_version=1,
            output_schema=ConnectionTestOutput,
            max_input_chars=200,
            max_output_tokens=100,
            timeout_s=15.0,
        ),
    )
}
