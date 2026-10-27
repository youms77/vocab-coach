"""The `curriculum_unit` schema and its registration (module H, M8.a2)."""

import pytest
from pydantic import ValidationError

from app.ai.prompt_loader import PromptLibrary
from app.ai.schemas.curriculum_unit import CurriculumUnitOutput
from app.ai.tasks import CURRICULUM_UNIT_MAX_OUTPUT_TOKENS, TASKS
from tests.curriculum_unit_support import BREAKS, broken, unit_output


def test_a_valid_unit_and_its_stored_forms() -> None:
    output = CurriculumUnitOutput.model_validate(unit_output())
    assert output.stored_shadowing() == [0, 2, 4, 6, 8]
    assert output.stored_final_task().formula_refs == [0, 1, 2]
    assert output.formulas[0].style == "neutral"


@pytest.mark.parametrize("change", sorted(BREAKS))
def test_each_rule_is_refused(change: str) -> None:
    with pytest.raises(ValidationError):
        CurriculumUnitOutput.model_validate(broken(change))


def test_messages_never_quote_the_ai_text() -> None:
    data = broken("unknown_ref")
    data["formulas"][0]["function_fr"] = "SECRET-FUNCTION"
    data["formulas"][1]["text"] = "SECRET-FORMULA"
    data["dialogue"]["lines"][3]["text"] = "SECRET-LINE"
    data["final_task"]["prompt_en"] = " "
    with pytest.raises(ValidationError) as caught:
        CurriculumUnitOutput.model_validate(data)
    assert "SECRET" not in str(caught.value)


def test_every_problem_is_reported_at_once() -> None:
    data = broken("unknown_ref")
    data["shadowing"] = [1, 3, 5, 7, 7]
    with pytest.raises(ValidationError) as caught:
        CurriculumUnitOutput.model_validate(data)
    message = str(caught.value)
    assert "formula_refs[2]" in message and "listed twice" in message


def test_the_task_is_registered_with_its_prompt() -> None:
    spec = TASKS["curriculum_unit"]
    assert spec.prompt_label == "curriculum_unit.v1"
    assert spec.max_output_tokens == CURRICULUM_UNIT_MAX_OUTPUT_TOKENS
    prompt = PromptLibrary().get("curriculum_unit", 1)
    assert set(prompt.header.placeholders) == {"title", "level", "goals", "situations"}


def test_the_json_schema_names_the_register_key() -> None:
    schema = CurriculumUnitOutput.model_json_schema()
    assert "register" in schema["$defs"]["Formula"]["properties"]
