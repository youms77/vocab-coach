"""Builders of valid (and deliberately broken) `speaking_correction` outputs (fictional data)."""

from copy import deepcopy
from typing import Any

from app.domain.speech_rules import speech_units
from tests.correction_support import CODES as WRITTEN_CODES

# A transcription as Whisper writes it: hesitations, a self-correction, three real errors.
SPEECH = (
    "Um, so, I'm a master's student in statistics and I live in campus. "
    "I study here since two years. "
    "Last week I, uh, I present— I presented my first results to my supervisor. "
    "Next month I have to present them to the department, and I never presented in English "
    "before, so I'm a bit nervous."
)
UNITS = {unit.index: unit.text for unit in speech_units(SPEECH)}
CODES = WRITTEN_CODES | {
    "grammar.preposition.by_for_since",
    "discourse",
    "discourse.connectors",
    "register",
}
PROMPT = "Describe where you study and for how long."


def error(unit: int, wrong: str, correction: str, category_code: str, **changes: Any):
    return {
        "sentence_index": unit,
        "wrong": wrong,
        "correction": correction,
        "alternatives": [],
        "category_code": category_code,
        "proposed_subcategory": None,
        "explanation_en": f"Say '{correction}' here.",
        "explanation_fr": f"Dites « {correction} » ici.",
        "target_ref": None,
    } | changes


def structure(**changes: Any) -> dict[str, Any]:
    return {
        "comment_en": "You give your situation, then one example. Add a short ending.",
        "comment_fr": "Vous donnez votre situation, puis un exemple. Ajoutez une courte fin.",
        "connectors_used": ["so", "and"],
        "suggestions": [{"text_en": "To sum up, ...", "text_fr": "Pour résumer, ..."}],
    } | changes


EXPECTED_CODES = [
    "grammar.preposition.fixed_expression",
    "grammar.preposition.by_for_since",
    "grammar.tense.past_simple_vs_present_perfect",
]


def speaking_output(**changes: Any) -> dict[str, Any]:
    """The expected answer for `SPEECH`: the three errors, nothing for the self-correction."""
    output: dict[str, Any] = {
        "sentences": [
            {
                "index": 1,
                "corrected": "I'm a master's student in statistics and I live on campus.",
                "status": "corrected",
            },
            {
                "index": 2,
                "corrected": "I have been studying here for two years.",
                "status": "corrected",
            },
            {
                "index": 3,
                "corrected": "Last week I presented my first results to my supervisor.",
                "status": "correct",
            },
            {
                "index": 4,
                "corrected": "Next month I have to present them to the department, and I have "
                "never presented in English before, so I'm a bit nervous.",
                "status": "corrected",
            },
        ],
        "corrected_text": "I'm a master's student in statistics and I live on campus. ...",
        "natural_text": "I'm doing a master's in statistics and I live on campus. ...",
        "errors": [
            error(1, "in campus", "on campus", EXPECTED_CODES[0]),
            error(
                2,
                "study here since two years",
                "have been studying here for two years",
                EXPECTED_CODES[1],
            ),
            error(4, "I never presented", "I have never presented", EXPECTED_CODES[2]),
        ],
        "naturalness_notes": [],
        "targets": [],
        "structure": structure(),
        "overall_comment": "Clear and well organised. Watch two prepositions and one tense.",
    }
    output.update(deepcopy(changes))
    return output


def clean_output(text: str, **changes: Any) -> dict[str, Any]:
    """A valid answer for any `text`: every unit `correct`, no error, a structure comment."""
    units = speech_units(text)
    output: dict[str, Any] = {
        "sentences": [{"index": u.index, "corrected": u.text, "status": "correct"} for u in units],
        "corrected_text": text,
        "natural_text": text,
        "errors": [],
        "naturalness_notes": [],
        "targets": [],
        "structure": structure(connectors_used=[]),
        "overall_comment": "Well done.",
    }
    output.update(deepcopy(changes))
    return output


def broken(change: str) -> dict[str, Any]:
    """`speaking_output()` with one rule broken (in monologue mode)."""
    output = speaking_output()
    match change:
        # The rules inherited from `production_correction`.
        case "missing_unit":
            output["sentences"] = output["sentences"][:3]
        case "wrong_not_in_unit":
            output["errors"][0]["wrong"] = "at university"
        case "spelling_code":
            output["errors"][0]["category_code"] = "spelling"
        case "correct_with_error":
            output["sentences"][0]["status"] = "correct"
        # The rules of the spoken output.
        case "no_structure_in_monologue":
            output["structure"] = None
        case "four_comment_sentences":
            output["structure"]["comment_en"] = "One. Two. Three. Four."
        case "connector_not_said":
            output["structure"]["connectors_used"] = ["so", "moreover"]
        case "too_many_connectors":
            output["structure"]["connectors_used"] = ["so"] * 11
        case "too_many_suggestions":
            output["structure"]["suggestions"] = [{"text_en": "x", "text_fr": "y"}] * 4
        case "unit_too_long":
            output["sentences"][0]["corrected"] = "x" * 4501
        case _:
            raise ValueError(change)
    return output


BROKEN = [
    "missing_unit",
    "wrong_not_in_unit",
    "spelling_code",
    "correct_with_error",
    "no_structure_in_monologue",
    "four_comment_sentences",
    "connector_not_said",
    "too_many_connectors",
    "too_many_suggestions",
    "unit_too_long",
]
