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
from app.ai.schemas.production_correction import ProductionCorrectionOutput

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

# `production_correction` (D-128). Input: the text (4 000 characters, 40 sentences numbered as JSON
# lines: about 5 000), the prompt (500), 15 targets (about 250 each), and about 40 taxonomy lines
# (about 110 each): 13 000 characters at most, plus room for categories the user adds.
CORRECTION_MAX_INPUT_CHARS = 16000
# Output ceiling: 30 errors of about 170 tokens, the corrected and the natural text (about 1 000
# tokens each for 4 000 characters), the sentences, notes and targets. A call asks for less: the
# base plus a share per sentence (`correction_output_budget`).
CORRECTION_MAX_OUTPUT_TOKENS = 10000
CORRECTION_BASE_TOKENS = 800
CORRECTION_TOKENS_PER_SENTENCE = 250


def correction_output_budget(sentence_count: int) -> int:
    """Output tokens to ask for when correcting `sentence_count` sentences (at most the ceiling)."""
    wanted = CORRECTION_BASE_TOKENS + CORRECTION_TOKENS_PER_SENTENCE * sentence_count
    return min(wanted, CORRECTION_MAX_OUTPUT_TOKENS)


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
        TaskSpec(
            name="production_correction",
            prompt_version=1,
            output_schema=ProductionCorrectionOutput,
            max_input_chars=CORRECTION_MAX_INPUT_CHARS,
            max_output_tokens=CORRECTION_MAX_OUTPUT_TOKENS,
            timeout_s=60.0,
        ),
    )
}
