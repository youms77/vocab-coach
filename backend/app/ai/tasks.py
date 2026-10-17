"""Task registry. Each task pins its prompt version, so adding a prompt file never changes behaviour
silently. Adding a task = one prompt file + one schema class + one entry here; the gateway does
not change.
"""

from dataclasses import dataclass

from app.ai.policy import REQUEST_TIMEOUT_S
from app.ai.schemas import AiOutput
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.schemas.enrichment import ENRICHMENT_BATCH_SIZE, EnrichmentBatchOutput
from app.ai.schemas.list_extension import MAX_COUNT, ListExtensionOutput

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


# Output budget of one term of the `enrichment` task (D-080): the sheet is about 900 tokens of JSON,
# the exercise sentences about 450. The service asks for `ENRICHMENT_TOKENS_PER_TERM` x batch size.
ENRICHMENT_TOKENS_PER_TERM = 1500
# A suggestion of `list_extension` (term, type, category, sentence) is about 50 tokens.
EXTENSION_TOKENS_PER_SUGGESTION = 60

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
        TaskSpec(
            name="enrichment",
            prompt_version=1,
            output_schema=EnrichmentBatchOutput,
            # 5 terms x ~1 300 characters (term, type, sentence cut to 400, deck name, domain and
            # context cut to 300) and the JSON keys.
            max_input_chars=8000,
            max_output_tokens=ENRICHMENT_TOKENS_PER_TERM * ENRICHMENT_BATCH_SIZE,
            # 7 000 tokens of output may take longer than the default 30 s; the 90 s budget holds.
            timeout_s=60.0,
        ),
        TaskSpec(
            name="list_extension",
            prompt_version=1,
            output_schema=ListExtensionOutput,
            # Deck fields cut to ~1 000 characters, at most 80 terms cut to 2 400 characters.
            max_input_chars=4000,
            max_output_tokens=EXTENSION_TOKENS_PER_SUGGESTION * (MAX_COUNT + 5),
            timeout_s=45.0,
        ),
    )
}
