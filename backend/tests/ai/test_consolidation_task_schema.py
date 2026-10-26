"""The `consolidation_task` schema and its registration (module G, M7.a1)."""

import pytest
from pydantic import ValidationError

from app.ai.prompt_loader import PromptLibrary
from app.ai.schemas.consolidation_task import ConsolidationTaskOutput, consolidation_context
from app.ai.tasks import TASKS
from app.domain.consolidation import term_ref
from tests.consolidation_support import BROKEN, broken, task_output

REFS = [term_ref(i) for i in range(10)]


def validate(data: dict, task_type: str = "talk") -> ConsolidationTaskOutput:
    return ConsolidationTaskOutput.model_validate(
        data, context=consolidation_context(REFS, task_type)
    )


def test_a_valid_task() -> None:
    output = validate(task_output())
    assert len(output.sections) == 4


@pytest.mark.parametrize("change", BROKEN)
def test_each_rule_is_refused(change: str) -> None:
    with pytest.raises(ValidationError):
        validate(broken(change))


def test_messages_never_quote_the_ai_text() -> None:
    data = broken("unknown_ref")
    data["sections"][0]["heading_en"] = "SECRET-HEADING"
    data["title_fr"] = " "
    with pytest.raises(ValidationError) as caught:
        validate(data)
    assert "SECRET-HEADING" not in str(caught.value)


def test_without_a_context_only_the_shape_is_checked() -> None:
    ConsolidationTaskOutput.model_validate(task_output(["a", "b"]))


def test_the_task_is_registered_with_its_prompt() -> None:
    spec = TASKS["consolidation_task"]
    assert spec.prompt_label == "consolidation_task.v1"
    assert spec.timeout_s == 45.0
    prompt = PromptLibrary().get("consolidation_task", 1)
    assert set(prompt.header.placeholders) == {"deck", "terms", "task_type", "term_count"}
