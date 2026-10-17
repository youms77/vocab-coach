"""Builders of valid (and deliberately broken) `production_correction` outputs (fictional data)."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.domain.sentences import split_sentences

PARAGRAPH = (
    "Last year I moved to Yaoundé to start my master's degree. "
    "Since then, I lived in campus with two friends from my class."
)
# Sentences as numbered by `split_sentences` (1-based).
SENTENCES = {
    1: "Last year I moved to Yaoundé to start my master's degree.",
    2: "Since then, I lived in campus with two friends from my class.",
}
CODES = {
    "grammar",
    "grammar.preposition",
    "grammar.preposition.fixed_expression",
    "grammar.tense",
    "grammar.tense.past_simple_vs_present_perfect",
    "lexis",
    "lexis.wrong_word",
}

EXAMPLE_FILE = Path(__file__).resolve().parents[2] / "content" / "examples" / "m5_paragraph.txt"


def error(
    sentence_index: int, wrong: str, correction: str, category_code: str, **changes: Any
) -> dict[str, Any]:
    return {
        "sentence_index": sentence_index,
        "wrong": wrong,
        "correction": correction,
        "alternatives": [],
        "category_code": category_code,
        "proposed_subcategory": None,
        "explanation_en": f"Use '{correction}' here.",
        "explanation_fr": f"Utilisez « {correction} » ici.",
        "target_ref": None,
    } | changes


def correction_output(**changes: Any) -> dict[str, Any]:
    """The expected answer for `PARAGRAPH`: two errors in the second sentence."""
    output: dict[str, Any] = {
        "sentences": [
            {"index": 1, "corrected": SENTENCES[1], "status": "correct"},
            {
                "index": 2,
                "corrected": "Since then, I have lived on campus with two friends from my class.",
                "status": "corrected",
            },
        ],
        "corrected_text": (
            "Last year I moved to Yaoundé to start my master's degree. "
            "Since then, I have lived on campus with two friends from my class."
        ),
        "natural_text": (
            "Last year I moved to Yaoundé to start my master's degree, and I have lived on "
            "campus with two classmates ever since."
        ),
        "errors": [
            error(2, "in campus", "on campus", "grammar.preposition.fixed_expression"),
            error(
                2,
                "lived",
                "have lived",
                "grammar.tense.past_simple_vs_present_perfect",
                alternatives=["have been living"],
            ),
        ],
        "naturalness_notes": [],
        "targets": [],
        "overall_comment": "Good paragraph. Watch the preposition and the tense.",
    }
    output.update(deepcopy(changes))
    return output


def broken(change: str) -> dict[str, Any]:
    """`correction_output()` with one rule broken. The keys are the messages' locations."""
    output = correction_output()
    errors = output["errors"]
    match change:
        case "missing_sentence":
            output["sentences"] = output["sentences"][:1]
        case "extra_sentence":
            output["sentences"].append({"index": 3, "corrected": "Extra.", "status": "correct"})
        case "wrong_not_in_sentence":
            errors[0]["wrong"] = "at university"
        case "wrong_in_another_sentence":
            errors[0]["sentence_index"] = 1
        case "wrong_equals_correction":
            errors[0]["correction"] = errors[0]["wrong"]
        case "unknown_category":
            errors[0]["category_code"] = "grammar.invented"
        case "unknown_parent":
            errors[0]["proposed_subcategory"] = proposal(parent_code="nothing")
        case "bad_slug":
            errors[0]["proposed_subcategory"] = proposal(slug="Bad Slug!")
        case "correct_with_error":
            output["sentences"][1]["status"] = "correct"
        case "unknown_target_ref":
            errors[0]["target_ref"] = 4
        case "unknown_target_check":
            output["targets"] = [{"ref": 7, "used": True, "used_correctly": True, "comment": ""}]
        case "unknown_note_sentence":
            output["naturalness_notes"] = [
                {"sentence_index": 9, "text": "x", "suggestion": "y", "note": "z"}
            ]
        case "too_many_errors":
            output["errors"] = [errors[0]] * 31
        case _:
            raise ValueError(change)
    return output


BROKEN = [
    "missing_sentence",
    "extra_sentence",
    "wrong_not_in_sentence",
    "wrong_in_another_sentence",
    "wrong_equals_correction",
    "unknown_category",
    "unknown_parent",
    "bad_slug",
    "correct_with_error",
    "unknown_target_ref",
    "unknown_target_check",
    "unknown_note_sentence",
    "too_many_errors",
]


def proposal(**changes: Any) -> dict[str, Any]:
    return {
        "parent_code": "grammar.preposition",
        "slug": "campus_words",
        "label_en": "Campus words",
        "label_fr": "Mots du campus",
        "description_en": "Prepositions used with places of the university.",
    } | changes


def output_for(text: str, **changes: Any) -> dict[str, Any]:
    """A correct answer for any `text`: every sentence `correct`, no error."""
    sentences = split_sentences(text)
    output: dict[str, Any] = {
        "sentences": [
            {"index": s.index, "corrected": s.text, "status": "correct"} for s in sentences
        ],
        "corrected_text": text,
        "natural_text": text,
        "errors": [],
        "naturalness_notes": [],
        "targets": [],
        "overall_comment": "Well done.",
    }
    output.update(deepcopy(changes))
    return output
