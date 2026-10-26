"""Task registry. Each task pins its prompt version, so adding a prompt file never changes behaviour
silently. Adding a task = one prompt file + one schema class + one entry here; the gateway does
not change.
"""

from dataclasses import dataclass

from app.ai.policy import REQUEST_TIMEOUT_S
from app.ai.schemas import AiOutput
from app.ai.schemas.connection_test import ConnectionTestOutput
from app.ai.schemas.consolidation_task import ConsolidationTaskOutput
from app.ai.schemas.curriculum_unit import CurriculumUnitOutput
from app.ai.schemas.enrichment import ENRICHMENT_BATCH_SIZE, EnrichmentBatchOutput
from app.ai.schemas.list_extension import MAX_COUNT, ListExtensionOutput
from app.ai.schemas.production_correction import ProductionCorrectionOutput
from app.ai.schemas.speaking_correction import SpeakingCorrectionOutput
from app.ai.schemas.targeted_drill import TargetedDrillOutput
from app.ai.schemas.transcript_analysis import TranscriptAnalysisOutput

TRANSCRIPTION_TASK = "transcription"  # task name in `ai_call_log` for speech-to-text
PRONUNCIATION_TASK = "pronunciation_assessment"  # same, for pronunciation assessment (M6.c1)


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


# `transcript_analysis` (D-134), one call per chunk of at most 2 500 characters and 20 units
# (`app/domain/transcript_import.py`). Input: the units as JSON lines (2 500 + 20 x about 30), the
# context before each unit that opens a turn (20 x (300 + about 30)), and about 33 taxonomy lines
# (spelling and pronunciation left out) of at most about 230 characters: about 17 300 at most.
TRANSCRIPT_MAX_INPUT_CHARS = 20000
# Output: a long unit (600 characters) needs about 150 tokens for its corrected text and up to 4
# errors of about 170 tokens, so a call asks for a base plus a share per unit. The ceiling covers
# 40 errors (6 800 tokens) and the corrected units of a full chunk.
TRANSCRIPT_MAX_OUTPUT_TOKENS = 8000
TRANSCRIPT_BASE_TOKENS = 800
TRANSCRIPT_TOKENS_PER_UNIT = 450


def transcript_output_budget(unit_count: int) -> int:
    """Output tokens to ask for when checking `unit_count` units (at most the ceiling)."""
    wanted = TRANSCRIPT_BASE_TOKENS + TRANSCRIPT_TOKENS_PER_UNIT * unit_count
    return min(wanted, TRANSCRIPT_MAX_OUTPUT_TOKENS)


# `speaking_correction` (M6.a2a), one call per transcription. Input: the text (4 000 characters,
# `MAX_SPEAKING_CHARS`), its at most 40 units as JSON lines (about 800 more), the prompt (500), 15
# targets (about 250 each) and about 33 taxonomy lines (spelling and pronunciation left out) of at
# most about 230 characters: about 16 600 at most, plus room for categories the user adds.
SPEAKING_MAX_INPUT_CHARS = 20000
# Output: as `production_correction` (a unit is corrected like a sentence, 30 errors at most), with
# a base 400 tokens larger for `structure` (two comments of at most 600 characters, 10 connectors,
# 3 suggestions in two languages). Same ceiling as D-128.
SPEAKING_MAX_OUTPUT_TOKENS = 10000
SPEAKING_BASE_TOKENS = 1200
SPEAKING_TOKENS_PER_UNIT = 250


def speaking_output_budget(unit_count: int) -> int:
    """Output tokens to ask for when correcting `unit_count` units (at most the ceiling)."""
    wanted = SPEAKING_BASE_TOKENS + SPEAKING_TOKENS_PER_UNIT * unit_count
    return min(wanted, SPEAKING_MAX_OUTPUT_TOKENS)


# `targeted_drill` (D-135). Input: the category and its children (about 8 lines of at most 250
# characters: 2 000), at most 5 recent errors (wrong form and correction, at most 600 each:
# 3 000) and the count: about 5 200 characters at most.
DRILL_MAX_INPUT_CHARS = 6000
# Output: an item is about 250 tokens (sentence, answer, accepted forms, options, theme and two
# explanations), the two rules about 160, the JSON frame about 240: `400 + 250 x items`, so 15
# items need 4 150 tokens.
DRILL_BASE_TOKENS = 400
DRILL_TOKENS_PER_ITEM = 250
DRILL_MAX_OUTPUT_TOKENS = 4200


def drill_output_budget(item_count: int) -> int:
    """Output tokens to ask for when writing `item_count` items (at most the ceiling)."""
    return min(DRILL_BASE_TOKENS + DRILL_TOKENS_PER_ITEM * item_count, DRILL_MAX_OUTPUT_TOKENS)


# `consolidation_task` (M7.a1). Input: the deck (name 300, domain 200, description and source cut to
# about 700: about 1 200) and at most 15 terms (ref, term, type and a simple definition cut to 300:
# about 300 each, 4 500): 8 000 characters leave room for the JSON keys.
CONSOLIDATION_MAX_INPUT_CHARS = 8000
# Output: titles, prompts and audience in two languages (about 500 tokens), at most 6 sections of
# about 250 tokens (two headings, two guidance texts, the references) and the JSON frame.
CONSOLIDATION_MAX_OUTPUT_TOKENS = 3000

# `curriculum_unit` (M8.a2). Input: the values of a syllabus unit, each text at most 500 characters
# (`Text` of `app/domain/curriculum.py`): title 500, level 500, 4 goals (2 000) and 6 situations
# (3 000): 6 000 characters at most, 6 500 leave room for the JSON keys.
CURRICULUM_UNIT_MAX_INPUT_CHARS = 6500
# Output: a formula is about 110 tokens (text, type, function in two languages, register, keys), so
# 15 make 1 650; the dialogue is two settings (80) and 16 lines of about 36 tokens (580); the
# shadowing numbers (30) and the final task (two prompts of 70 and the references: 200); the JSON
# frame (100): about 2 700. French text costs more tokens than English: the ceiling is 4 000.
CURRICULUM_UNIT_MAX_OUTPUT_TOKENS = 4000


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
        TaskSpec(
            name="transcript_analysis",
            prompt_version=1,
            output_schema=TranscriptAnalysisOutput,
            max_input_chars=TRANSCRIPT_MAX_INPUT_CHARS,
            max_output_tokens=TRANSCRIPT_MAX_OUTPUT_TOKENS,
            timeout_s=60.0,
        ),
        TaskSpec(
            name="speaking_correction",
            prompt_version=1,
            output_schema=SpeakingCorrectionOutput,
            max_input_chars=SPEAKING_MAX_INPUT_CHARS,
            max_output_tokens=SPEAKING_MAX_OUTPUT_TOKENS,
            # As `production_correction`: up to 10 000 tokens of output; the 90 s budget holds.
            timeout_s=60.0,
        ),
        TaskSpec(
            name="consolidation_task",
            prompt_version=1,
            output_schema=ConsolidationTaskOutput,
            max_input_chars=CONSOLIDATION_MAX_INPUT_CHARS,
            max_output_tokens=CONSOLIDATION_MAX_OUTPUT_TOKENS,
            timeout_s=45.0,
        ),
        TaskSpec(
            name="targeted_drill",
            prompt_version=1,
            output_schema=TargetedDrillOutput,
            max_input_chars=DRILL_MAX_INPUT_CHARS,
            max_output_tokens=DRILL_MAX_OUTPUT_TOKENS,
            timeout_s=45.0,
        ),
        TaskSpec(
            name="curriculum_unit",
            prompt_version=1,
            output_schema=CurriculumUnitOutput,
            max_input_chars=CURRICULUM_UNIT_MAX_INPUT_CHARS,
            max_output_tokens=CURRICULUM_UNIT_MAX_OUTPUT_TOKENS,
            # Up to 4 000 tokens of output: the 90 s budget holds.
            timeout_s=60.0,
        ),
    )
}
