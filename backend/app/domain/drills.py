"""Targeted drills (module E, M5.a2). Pure Python: no database, no clock.

A drill is 5 to 15 items generated once by the AI (`targeted_drill`) for one error category, then
stored (`production_attempt.ai_feedback`, `format: "drill-1"`). This module holds the rules that do
not need the database:

- `fill_gap`: the sentence with its single `___` replaced;
- `options_order`: the options of a choice item shuffled with `random.Random("drill:<id>:<index>")`,
  so every read and the grading see the same order without storing it (like D-103); the index of
  the right option is computed from that order, never given by the AI;
- `grade_item`: **exact** grading after the D-102 normalisation (NFKC, apostrophes, case, spaces,
  punctuation at both ends) against `answer` and `accepted`; no typo tolerance and no "form"
  (D-135). Outcomes: `exact`, `wrong`, `empty`;
- `public_item`: what an item shows before it is answered, never its solution (D-103).
"""

import random
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.grading import normalize_answer

GAP = "___"
GAP_RUN = re.compile(r"_+")
MIN_ITEMS = 5
MAX_ITEMS = 15
DEFAULT_ITEMS = 10
MAX_ANSWER_WORDS = 4
MAX_SENTENCE_WORDS = 30
MAX_ACCEPTED = 3
THEMES = ("campus", "data_economics", "everyday")

ItemKind = Literal["gap_fill", "choice"]
Outcome = Literal["exact", "wrong", "empty"]

# Keys an unanswered item never carries (the API test walks every item for them).
SOLUTION_KEYS = frozenset(
    {"answer", "accepted", "correct_index", "expected", "explanation_en", "explanation_fr"}
)


def fill_gap(sentence: str, text: str) -> str:
    """The sentence with its gap replaced by `text` (the gap itself when `text` is empty)."""
    return sentence.replace(GAP, text.strip() or GAP, 1)


def options_order(drill_id: int, index: int, options: list[str]) -> list[str]:
    """The options of item `index` in the order shown for drill `drill_id` (deterministic)."""
    shuffled = list(options)
    random.Random(f"drill:{drill_id}:{index}").shuffle(shuffled)  # noqa: S311 (not security)
    return shuffled


def correct_index(shown: list[str], answer: str) -> int | None:
    expected = normalize_answer(answer)
    for i, option in enumerate(shown):
        if normalize_answer(option) == expected:
            return i
    return None


@dataclass(frozen=True)
class Graded:
    outcome: Outcome
    given: str  # what the user typed, or the option they chose ("" when empty)


def grade_item(
    item: dict[str, Any],
    shown: list[str] | None,
    *,
    answer: str | None,
    choice_index: int | None,
) -> Graded:
    """Grade one attempt. The caller has checked the attempt fits the item's kind and that
    `choice_index` is within `shown`."""
    if item["kind"] == "choice":
        if choice_index is None or shown is None:
            return Graded("empty", "")
        given = shown[choice_index]
        right = correct_index(shown, item["answer"])
        return Graded("exact" if choice_index == right else "wrong", given)
    given = (answer or "").strip()
    normalized = normalize_answer(given)
    if not normalized:
        return Graded("empty", given)
    expected = {normalize_answer(form) for form in [item["answer"], *item.get("accepted", [])]}
    return Graded("exact" if normalized in expected else "wrong", given)


def public_item(drill_id: int, index: int, item: dict[str, Any]) -> dict[str, Any]:
    """An item before it is answered: kind, sentence and the shown options only."""
    options = item.get("options") if item["kind"] == "choice" else None
    return {
        "index": index,
        "kind": item["kind"],
        "sentence": item["sentence"],
        "options": options_order(drill_id, index, options) if options else None,
    }


def item_result(
    drill_id: int, index: int, item: dict[str, Any], *, outcome: Outcome, given: str
) -> dict[str, Any]:
    """The solution of an answered item (shown only after the attempt)."""
    shown = (
        options_order(drill_id, index, item["options"])
        if item["kind"] == "choice" and item.get("options")
        else None
    )
    return {
        "outcome": outcome,
        "expected": item["answer"],
        "accepted": list(item.get("accepted", [])),
        "correct_index": correct_index(shown, item["answer"]) if shown else None,
        "explanation_en": item["explanation_en"],
        "explanation_fr": item["explanation_fr"],
        "given": given,
    }


def score(items: int, answers: list[dict[str, Any]]) -> dict[str, int]:
    outcomes = [answer["outcome"] for answer in answers]
    return {
        "correct": outcomes.count("exact"),
        "wrong": outcomes.count("wrong"),
        "empty": outcomes.count("empty"),
        "answered": len(outcomes),
        "total": items,
    }


def gap_runs(sentence: str) -> list[str]:
    """Every run of underscores in the sentence; a valid item has exactly one, `___`."""
    return GAP_RUN.findall(sentence)
