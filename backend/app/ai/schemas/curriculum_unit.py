"""Output of the `curriculum_unit` task: the content of a speaking scenario unit (module H, M8.a2).

8 to 15 formulas, a dialogue between two fictional speakers, 5 to 8 lines to shadow and a final
speaking task. The AI numbers the dialogue lines from 1 (`shadowing: [1, 3]`) and the formulas
`f1`, `f2`... (`formula_refs`); `stored_*` convert them to the 0-based indices that are stored.

The rules (`app.domain.curriculum_unit.problems`) run in a validator, so a broken rule is a
validation error: the gateway asks for one repair, then answers `incomplete` (D-079). Messages
name locations, never the AI's text. Without a context only the shapes are checked.
"""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.schemas import AiOutput
from app.domain import curriculum_unit as rules
from app.domain.curriculum_unit import Dialogue, Formula, Minutes


class FinalTaskOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_en: rules.Prompt
    prompt_fr: rules.Prompt
    minutes: Minutes
    formula_refs: Annotated[
        list[Annotated[str, Field(max_length=6)]],
        Field(min_length=rules.FINAL_REFS_MIN, max_length=rules.FORMULAS_MAX),
    ]


class CurriculumUnitOutput(AiOutput):
    formulas: Annotated[
        list[Formula], Field(min_length=rules.FORMULAS_MIN, max_length=rules.FORMULAS_MAX)
    ]
    dialogue: Dialogue
    shadowing: Annotated[
        list[Annotated[int, Field(ge=1, le=rules.LINES_MAX)]],
        Field(min_length=rules.SHADOWING_MIN, max_length=rules.SHADOWING_MAX),
    ]
    final_task: FinalTaskOut

    def stored_shadowing(self) -> list[int]:
        return [number - 1 for number in self.shadowing]

    def stored_final_task(self) -> rules.FinalTask:
        refs = [rules.parse_formula_ref(ref) for ref in self.final_task.formula_refs]
        return rules.FinalTask(
            prompt_en=self.final_task.prompt_en,
            prompt_fr=self.final_task.prompt_fr,
            minutes=self.final_task.minutes,
            formula_refs=[ref for ref in refs if ref is not None],
        )

    @model_validator(mode="after")
    def follows_the_rules(self) -> Self:
        found: list[str] = []
        unknown = [
            position
            for position, ref in enumerate(self.final_task.formula_refs)
            if (index := rules.parse_formula_ref(ref)) is None or index >= len(self.formulas)
        ]
        found.extend(f"final_task.formula_refs[{p}]: unknown reference" for p in unknown)
        if not unknown:
            found.extend(
                rules.problems(
                    self.formulas, self.dialogue, self.stored_shadowing(), self.stored_final_task()
                )
            )
        else:
            # The other rules still say what else is wrong, so one repair can fix all of it.
            known = rules.FinalTask(
                prompt_en=self.final_task.prompt_en,
                prompt_fr=self.final_task.prompt_fr,
                minutes=self.final_task.minutes,
                formula_refs=[0, 1, 2],
            )
            found.extend(
                p
                for p in rules.problems(
                    self.formulas, self.dialogue, self.stored_shadowing(), known
                )
                if not p.startswith("final_task.formula_refs")
            )
        if found:
            raise ValueError("; ".join(found))
        return self
