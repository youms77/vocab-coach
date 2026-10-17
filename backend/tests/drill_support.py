"""Builders of `targeted_drill` outputs for the tests (fictional data)."""

from copy import deepcopy
from typing import Any

FIXED = "grammar.preposition.fixed_expression"
THEMES = ["campus", "data_economics", "everyday"]


def gap_item(n: int, **changes: Any) -> dict[str, Any]:
    return {
        "kind": "gap_fill",
        "sentence": f"In week {n}, my friend lived ___ campus with two classmates.",
        "answer": "on",
        "accepted": [],
        "options": None,
        "category_code": FIXED,
        "theme": THEMES[n % 3],
        "explanation_en": "We say 'on campus'.",
        "explanation_fr": "On dit « on campus ».",
    } | changes


def choice_item(n: int, **changes: Any) -> dict[str, Any]:
    return {
        "kind": "choice",
        "sentence": f"Report {n} was due, so I stayed ___ university until late.",
        "answer": "at",
        "accepted": [],
        "options": ["at", "in", "on"],
        "category_code": FIXED,
        "theme": THEMES[(n + 1) % 3],
        "explanation_en": "We say 'at university'.",
        "explanation_fr": "On dit « at university ».",
    } | changes


def drill_output(count: int = 10, **changes: Any) -> dict[str, Any]:
    """A valid drill: gap-fill and choice items in turn, three themes."""
    output: dict[str, Any] = {
        "rule_en": "Some phrases always take the same preposition. Learn them as a whole.",
        "rule_fr": "Certaines expressions prennent toujours la même préposition.",
        "items": [gap_item(n) if n % 2 == 0 else choice_item(n) for n in range(count)],
    }
    output.update(deepcopy(changes))
    return output


def broken(change: str) -> dict[str, Any]:
    output = drill_output()
    items = output["items"]
    match change:
        case "too_few_items":
            output["items"] = items[:9]
        case "too_many_items":
            output["items"] = [*items, gap_item(99)]
        case "no_gap":
            items[0]["sentence"] = "My friend lived on campus."
        case "two_gaps":
            items[0]["sentence"] = "My friend lived ___ campus ___ a year."
        case "long_gap":
            items[0]["sentence"] = "My friend lived _____ campus."
        case "too_long_sentence":
            items[0]["sentence"] = "Word " * 30 + "___ campus."
        case "answer_too_long":
            items[0]["answer"] = "on the big old campus"
        case "blank_answer":
            items[0]["answer"] = " . "
        case "duplicate_sentence":
            items[2]["sentence"] = items[0]["sentence"]
        case "accepted_is_a_wrong_option":
            items[1]["accepted"] = ["in"]
        case "answer_not_in_options":
            items[1]["options"] = ["in", "on"]
        case "answer_twice_in_options":
            items[1]["options"] = ["at", "At", "on"]
        case "one_option":
            items[1]["options"] = ["at"]
        case "gap_fill_with_options":
            items[0]["options"] = ["on", "in"]
        case "foreign_category":
            items[0]["category_code"] = "grammar.tense"
        case "blank_explanation":
            items[0]["explanation_fr"] = "   "
        case "one_theme":
            for item in items:
                item["theme"] = "campus"
        case "rule_too_long":
            output["rule_en"] = "One. Two. Three. Four."
        case _:
            raise ValueError(change)
    return output


BROKEN = [
    "too_few_items",
    "too_many_items",
    "no_gap",
    "two_gaps",
    "long_gap",
    "too_long_sentence",
    "answer_too_long",
    "blank_answer",
    "duplicate_sentence",
    "accepted_is_a_wrong_option",
    "answer_not_in_options",
    "answer_twice_in_options",
    "one_option",
    "gap_fill_with_options",
    "foreign_category",
    "blank_explanation",
    "one_theme",
    "rule_too_long",
]
