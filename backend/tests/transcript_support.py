"""Builders of `transcript_analysis` outputs for the tests (fictional data)."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.domain.transcript_import import Unit, split_units

EXAMPLES = Path(__file__).resolve().parents[2] / "content" / "examples"
EXAMPLE_FILE = EXAMPLES / "m5_transcript.txt"
CLEAN_FILE = EXAMPLES / "m5_transcript_clean.txt"
UNLABELLED_FILE = EXAMPLES / "m5_transcript_unlabelled.txt"

EXAMPLE = EXAMPLE_FILE.read_text(encoding="utf-8")
# The user's turns of the example, as stored (one unit each).
EXAMPLE_TURNS = [
    "Uh, I live in campus, in a small room near the library.",
    "Um, I study here since two years. I'm doing a master's in statistics.",
    "Yesterday I have finished my report, and then I, uh, I went— I watched a film with my "
    "friends.",
    "It was about a young economist who, um, who travels to Douala for her research.",
]
# What ChatGPT says in the example: it must never reach the provider outside the context frame.
CHATGPT_QUOTE = 'we say "on campus", not "in campus"'


def error(unit_index: int, wrong: str, correction: str, category_code: str, **changes: Any):
    return {
        "unit_index": unit_index,
        "wrong": wrong,
        "correction": correction,
        "alternatives": [],
        "category_code": category_code,
        "proposed_subcategory": None,
        "explanation_en": f"Say '{correction}' here.",
        "explanation_fr": f"Dites « {correction} » ici.",
    } | changes


def output_for(units: list[Unit] | list[tuple[int, str]], **changes: Any) -> dict[str, Any]:
    """A valid answer: every unit `correct`, no error, unless `changes` say otherwise."""
    pairs = [(u.index, u.text) if isinstance(u, Unit) else u for u in units]
    output: dict[str, Any] = {
        "units": [{"index": i, "corrected": text, "status": "correct"} for i, text in pairs],
        "errors": [],
        "naturalness_notes": [],
        "overall_comment": "Good conversation.",
    }
    output.update(deepcopy(changes))
    return output


def example_output() -> dict[str, Any]:
    """The expected answer for the example: three errors, one per first three units."""
    units = split_units("\n\n".join(EXAMPLE_TURNS))
    output = output_for(
        units,
        errors=[
            error(1, "in campus", "on campus", "grammar.preposition.fixed_expression"),
            error(2, "since two years", "for two years", "grammar.preposition.by_for_since"),
            error(
                3,
                "Yesterday I have finished",
                "Yesterday I finished",
                "grammar.tense.past_simple_vs_present_perfect",
            ),
        ],
    )
    for index in (0, 1, 2):
        output["units"][index]["status"] = "corrected"
    output["units"][0]["corrected"] = "I live on campus, in a small room near the library."
    return output


def broken(change: str) -> dict[str, Any]:
    """`example_output()` with one rule broken."""
    output = example_output()
    errors = output["errors"]
    match change:
        case "missing_unit":
            output["units"] = output["units"][:3]
        case "extra_unit":
            output["units"].append({"index": 9, "corrected": "Extra.", "status": "correct"})
        case "wrong_not_in_unit":
            errors[0]["wrong"] = "at university"
        case "wrong_from_the_context":
            errors[0]["wrong"] = "not in campus"  # ChatGPT's words, not the learner's
        case "wrong_in_another_unit":
            errors[0]["unit_index"] = 4
        case "unknown_unit":
            errors[0]["unit_index"] = 12
        case "wrong_equals_correction":
            errors[0]["correction"] = errors[0]["wrong"]
        case "unknown_category":
            errors[0]["category_code"] = "grammar.invented"
        case "spelling_category":
            errors[0]["category_code"] = "spelling"
        case "pronunciation_category":
            errors[0]["category_code"] = "pronunciation.sound"
        case "unknown_parent":
            errors[0]["proposed_subcategory"] = proposal(parent_code="pronunciation")
        case "bad_slug":
            errors[0]["proposed_subcategory"] = proposal(slug="Bad Slug!")
        case "correct_with_error":
            output["units"][0]["status"] = "correct"
        case "unknown_note_unit":
            output["naturalness_notes"] = [
                {"unit_index": 9, "text": "x", "suggestion": "y", "note": "z"}
            ]
        case "too_many_errors":
            output["errors"] = [errors[0]] * 41
        case "too_many_alternatives":
            errors[0]["alternatives"] = ["on the campus", "at the campus", "in the campus"]
        case _:
            raise ValueError(change)
    return output


BROKEN = [
    "missing_unit",
    "extra_unit",
    "wrong_not_in_unit",
    "wrong_from_the_context",
    "wrong_in_another_unit",
    "unknown_unit",
    "wrong_equals_correction",
    "unknown_category",
    "spelling_category",
    "pronunciation_category",
    "unknown_parent",
    "bad_slug",
    "correct_with_error",
    "unknown_note_unit",
    "too_many_errors",
    "too_many_alternatives",
]


def proposal(**changes: Any) -> dict[str, Any]:
    return {
        "parent_code": "grammar.preposition",
        "slug": "campus_words",
        "label_en": "Campus words",
        "label_fr": "Mots du campus",
        "description_en": "Prepositions used with places of the university.",
    } | changes
