"""Output of the `consolidation_task` task: a talk, a speech or an interview answer that uses 8 to
15 terms of a deck, with a structure of 3 to 6 sections (module G, M7.a1).

The business rules run in a validator that reads the request from the validation context
(`consolidation_context`, D-079): a broken rule is a validation error, so the gateway asks for one
repair, then answers `incomplete`. Messages name locations, never the AI's text.
"""

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from app.ai.schemas import AiOutput
from app.domain.consolidation import MAX_MINUTES, MAX_SECTIONS, MIN_MINUTES, MIN_SECTIONS

TITLE_MAX = 150
PROMPT_MAX = 700
AUDIENCE_MAX = 150
HEADING_MAX = 100
GUIDANCE_MAX = 400

Title = Annotated[str, Field(max_length=TITLE_MAX)]
Prompt = Annotated[str, Field(max_length=PROMPT_MAX)]
Audience = Annotated[str, Field(max_length=AUDIENCE_MAX)]
Heading = Annotated[str, Field(max_length=HEADING_MAX)]
Guidance = Annotated[str, Field(max_length=GUIDANCE_MAX)]


class Section(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading_en: Heading
    heading_fr: Heading
    guidance_en: Guidance
    guidance_fr: Guidance
    term_refs: list[Annotated[str, Field(max_length=20)]]


class ConsolidationTaskOutput(AiOutput):
    task_type: str
    title_en: Title
    title_fr: Title
    prompt_en: Prompt
    prompt_fr: Prompt
    audience_en: Audience
    audience_fr: Audience
    target_minutes: Annotated[int, Field(ge=MIN_MINUTES, le=MAX_MINUTES)]
    sections: Annotated[list[Section], Field(min_length=MIN_SECTIONS, max_length=MAX_SECTIONS)]

    @model_validator(mode="after")
    def matches_the_request(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        refs: list[str] | None = context.get("refs")
        problems: list[str] = []
        for name in (
            "title_en",
            "title_fr",
            "prompt_en",
            "prompt_fr",
            "audience_en",
            "audience_fr",
        ):
            if not getattr(self, name).strip():
                problems.append(f"{name}: must not be empty")
        for i, section in enumerate(self.sections):
            for name in ("heading_en", "heading_fr", "guidance_en", "guidance_fr"):
                if not getattr(section, name).strip():
                    problems.append(f"sections[{i}].{name}: must not be empty")
        expected_type: str | None = context.get("task_type")
        if expected_type is not None and self.task_type != expected_type:
            problems.append(f"task_type: must be {expected_type}")
        if refs is not None:
            known = set(refs)
            used = [ref for section in self.sections for ref in section.term_refs]
            for ref in sorted(set(used) - known):
                problems.append(f"term_refs: unknown reference {ref!r}")
            for ref in sorted({r for r in used if used.count(r) > 1}):
                problems.append(f"term_refs: {ref} appears more than once")
            for ref in refs:
                if ref not in used:
                    problems.append(f"term_refs: {ref} is in no section")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def consolidation_context(refs: list[str], task_type: str) -> dict[str, Any]:
    """What the validator needs: the references given to the AI and the task type asked for."""
    return {"refs": list(refs), "task_type": task_type}
