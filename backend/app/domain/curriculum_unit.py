"""Content of a scenario unit (module H, M8.a2): formulas, a model dialogue, shadowing lines and a
final speaking task. Pure Python: the shapes and the rules the AI output, an edit and the demo
share (D-246 to D-251).

Stored positions are 0-based (`shadowing` holds line indices, `formula_refs` formula indices). The
AI numbers lines and formulas from 1 (`line 1`, `f1`), converted when the content is stored.
Every problem message names a location, never the text it found.
"""

import re
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.exercises import contains_term
from app.domain.normalize import normalize_term

UNIT_FORMAT = "curriculum-unit-1"

FORMULAS_MIN, FORMULAS_MAX = 8, 15
LINES_MIN, LINES_MAX = 8, 16
SHADOWING_MIN, SHADOWING_MAX = 5, 8
SHADOWING_WORDS_MIN, SHADOWING_WORDS_MAX = 4, 25
FINAL_REFS_MIN = 3
FINAL_MINUTES = (1, 2)
SPEAKER_COUNT = 2
# At least half of the formulas must be used by the dialogue (`contains_term`).
PRESENCE_SHARE = 0.5

FORMULA_MAX = 120
FUNCTION_MAX = 200
REGISTER_MAX = 40
SETTING_MAX = 300
NAME_MAX = 40
LINE_MAX = 300
PROMPT_MAX = 600

FormulaType = Literal["spoken_formula", "collocation", "phrase"]
Minutes = Literal[1, 2]

Step = Literal["formulas", "dialogue", "shadowing", "final_task"]
STEPS: tuple[Step, ...] = ("formulas", "dialogue", "shadowing", "final_task")

FORMULA_REF = re.compile(r"^f([1-9][0-9]?)$")

Short = Annotated[str, Field(max_length=FORMULA_MAX)]
Function = Annotated[str, Field(max_length=FUNCTION_MAX)]
Register = Annotated[str, Field(max_length=REGISTER_MAX)]
Setting = Annotated[str, Field(max_length=SETTING_MAX)]
Name = Annotated[str, Field(max_length=NAME_MAX)]
Line = Annotated[str, Field(max_length=LINE_MAX)]
Prompt = Annotated[str, Field(max_length=PROMPT_MAX)]


class Formula(BaseModel):
    """A formula: `register` is the JSON key, `style` the attribute (`BaseModel` has `register`)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    text: Short
    item_type: FormulaType
    function_en: Function
    function_fr: Function
    style: Register = Field(alias="register")


class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker: Name
    text: Line


class Dialogue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    setting_en: Setting
    setting_fr: Setting
    speakers: Annotated[list[Name], Field(min_length=SPEAKER_COUNT, max_length=SPEAKER_COUNT)]
    lines: Annotated[list[DialogueLine], Field(min_length=LINES_MIN, max_length=LINES_MAX)]


class FinalTask(BaseModel):
    """The final speaking task as stored: `formula_refs` are 0-based formula indices."""

    model_config = ConfigDict(extra="ignore")

    prompt_en: Prompt
    prompt_fr: Prompt
    minutes: Minutes
    formula_refs: Annotated[list[int], Field(min_length=FINAL_REFS_MIN, max_length=FORMULAS_MAX)]


def word_count(text: str) -> int:
    return len(text.split())


def formula_ref(index: int) -> str:
    """The reference the AI uses for formula `index` (0-based): `f1`, `f2`..."""
    return f"f{index + 1}"


def parse_formula_ref(ref: str) -> int | None:
    """The 0-based index a reference names, or None when it is not `f<n>`."""
    match = FORMULA_REF.match(ref.strip())
    return int(match.group(1)) - 1 if match else None


def _blank(text: str) -> bool:
    return not text.strip()


def problems(
    formulas: Sequence[Formula],
    dialogue: Dialogue,
    shadowing: Sequence[int],
    final_task: FinalTask,
) -> list[str]:
    """Every rule the shapes cannot say, as locations (empty when the content is acceptable)."""
    found: list[str] = []
    for i, formula in enumerate(formulas):
        for name in ("text", "function_en", "function_fr", "style"):
            if _blank(getattr(formula, name)):
                key = "register" if name == "style" else name
                found.append(f"formulas[{i}].{key}: must not be empty")
    seen: dict[str, int] = {}
    for i, formula in enumerate(formulas):
        key = normalize_term(formula.text)
        if not key:
            continue
        if key in seen:
            found.append(f"formulas[{i}]: repeats formulas[{seen[key]}]")
        else:
            seen[key] = i

    for name in ("setting_en", "setting_fr"):
        if _blank(getattr(dialogue, name)):
            found.append(f"dialogue.{name}: must not be empty")
    speakers = [s.strip().casefold() for s in dialogue.speakers]
    if any(not s for s in speakers):
        found.append("dialogue.speakers: a name must not be empty")
    elif len(set(speakers)) != len(speakers):
        found.append("dialogue.speakers: the two names must differ")
    for i, line in enumerate(dialogue.lines):
        if _blank(line.text):
            found.append(f"dialogue.lines[{i}].text: must not be empty")
        if line.speaker.strip().casefold() not in speakers:
            found.append(f"dialogue.lines[{i}].speaker: not one of the two speakers")

    texts = [line.text for line in dialogue.lines]
    if formulas:
        present = sum(1 for f in formulas if any(contains_term(f.text, t) for t in texts))
        if present < len(formulas) * PRESENCE_SHARE:
            found.append(
                f"dialogue: only {present} of {len(formulas)} formulas are used "
                f"(at least half are needed)"
            )

    if len(set(shadowing)) != len(shadowing):
        found.append("shadowing: a line is listed twice")
    for position, index in enumerate(shadowing):
        if not 0 <= index < len(texts):
            found.append(f"shadowing[{position}]: not a line of the dialogue")
            continue
        words = word_count(texts[index])
        if not SHADOWING_WORDS_MIN <= words <= SHADOWING_WORDS_MAX:
            found.append(
                f"shadowing[{position}]: the line has {words} words, "
                f"{SHADOWING_WORDS_MIN} to {SHADOWING_WORDS_MAX} are needed"
            )

    for name in ("prompt_en", "prompt_fr"):
        if _blank(getattr(final_task, name)):
            found.append(f"final_task.{name}: must not be empty")
    refs = final_task.formula_refs
    if len(set(refs)) != len(refs):
        found.append("final_task.formula_refs: a formula is listed twice")
    for position, index in enumerate(refs):
        if not 0 <= index < len(formulas):
            found.append(f"final_task.formula_refs[{position}]: not a formula of the unit")
    return found


def shadowing_lines(content: dict[str, Any]) -> list[str]:
    """The sentences to shadow, in the order of `shadowing`."""
    lines = [line["text"] for line in content.get("dialogue", {}).get("lines", [])]
    return [lines[i] for i in content.get("shadowing", []) if 0 <= i < len(lines)]
