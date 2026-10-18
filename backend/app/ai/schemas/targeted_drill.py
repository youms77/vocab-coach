"""Output of the `targeted_drill` task: the rule of one error category and 5 to 15 items.

The business rules run in a validator that reads the request from the validation context
(`drill_context`, D-079): a broken rule is a validation error, so the gateway asks for one repair,
then answers `incomplete`. Messages name locations, never the items' text. The right option of a
choice item is found by the server (`app/domain/drills.py`), never given by the AI.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from app.ai.schemas import AiOutput
from app.domain.drills import (
    GAP,
    MAX_ACCEPTED,
    MAX_ANSWER_WORDS,
    MAX_SENTENCE_WORDS,
    fill_gap,
    gap_runs,
)
from app.domain.grading import normalize_answer
from app.domain.sentences import split_sentences

MAX_RULE_SENTENCES = 3
MIN_THEMES = 2

Text = Annotated[str, Field(min_length=1, max_length=600)]
Form = Annotated[str, Field(min_length=1, max_length=80)]


class DrillItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["gap_fill", "choice"]
    sentence: Annotated[str, Field(min_length=1, max_length=400)]
    answer: Form
    accepted: Annotated[list[Form], Field(max_length=MAX_ACCEPTED)] = []
    options: list[Form] | None = None
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    theme: Literal["campus", "data_economics", "everyday"]
    explanation_en: Text
    explanation_fr: Text


class TargetedDrillOutput(AiOutput):
    rule_en: Text
    rule_fr: Text
    items: Annotated[list[DrillItem], Field(min_length=1)]

    @model_validator(mode="after")
    def matches_the_request(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        count: int | None = context.get("count")
        if count is None:
            return self
        codes: set[str] = context.get("codes", set())
        problems: list[str] = []
        for name, rule in (("rule_en", self.rule_en), ("rule_fr", self.rule_fr)):
            sentences = len(split_sentences(rule, max_sentences=None))
            if not 1 <= sentences <= MAX_RULE_SENTENCES:
                problems.append(f"{name}: 1 to {MAX_RULE_SENTENCES} sentences")
        if len(self.items) != count:
            problems.append(f"items: exactly {count} items")
        seen: set[str] = set()
        for i, item in enumerate(self.items):
            problems += _item_problems(i, item, codes)
            key = normalize_answer(item.sentence)
            if key in seen:
                problems.append(f"items[{i}].sentence: the same sentence appears twice")
            seen.add(key)
        if len({item.theme for item in self.items}) < MIN_THEMES:
            problems.append(f"items: use at least {MIN_THEMES} different themes")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _words(text: str) -> int:
    return len(text.split())


def _item_problems(i: int, item: DrillItem, codes: set[str]) -> list[str]:
    at = f"items[{i}]"
    problems: list[str] = []
    if gap_runs(item.sentence) != [GAP]:
        problems.append(f"{at}.sentence: exactly one gap written {GAP}")
    elif _words(fill_gap(item.sentence, item.answer)) > MAX_SENTENCE_WORDS:
        problems.append(f"{at}.sentence: at most {MAX_SENTENCE_WORDS} words once completed")
    answer = normalize_answer(item.answer)
    if not answer:
        problems.append(f"{at}.answer: must not be empty")
    for name, form in [("answer", item.answer)] + [
        (f"accepted[{n}]", form) for n, form in enumerate(item.accepted)
    ]:
        if _words(form) > MAX_ANSWER_WORDS:
            problems.append(f"{at}.{name}: at most {MAX_ANSWER_WORDS} words")
        if not normalize_answer(form):
            problems.append(f"{at}.{name}: must not be empty")
    if item.kind == "choice":
        options = item.options or []
        normalized = [normalize_answer(option) for option in options]
        if not 2 <= len(options) <= 4:
            problems.append(f"{at}.options: 2 to 4 options for a choice item")
        if len(set(normalized)) != len(normalized):
            problems.append(f"{at}.options: each option must be different")
        if normalized.count(answer) != 1:
            problems.append(f"{at}.options: must contain the answer exactly once")
        wrong = {option for option in normalized if option != answer}
        if any(normalize_answer(form) in wrong for form in item.accepted):
            problems.append(f"{at}.accepted: must not contain a wrong option")
    elif item.options:
        problems.append(f"{at}.options: a gap_fill item has no options (null)")
    if item.category_code not in codes:
        problems.append(f"{at}.category_code: the requested code or one of its listed children")
    for name in ("explanation_en", "explanation_fr"):
        if not getattr(item, name).strip():
            problems.append(f"{at}.{name}: must not be empty")
    return problems


def drill_context(count: int, codes: set[str]) -> dict[str, Any]:
    """What the validator needs: the number of items asked for and the codes allowed (the
    requested code and its active descendants)."""
    return {"count": count, "codes": set(codes)}
