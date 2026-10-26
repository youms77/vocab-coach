"""A valid `curriculum_unit` output (a job interview) and the ways to break it (M8.a2)."""

import copy
from typing import Any

FORMULAS = [
    ("Thank you for having me", "spoken_formula", "neutral"),
    ("I am particularly interested in", "spoken_formula", "formal"),
    ("my greatest strength is", "spoken_formula", "neutral"),
    ("work under pressure", "collocation", "neutral"),
    ("meet a deadline", "collocation", "neutral"),
    ("take the initiative", "collocation", "formal"),
    ("a team player", "phrase", "neutral"),
    ("I would be glad to", "spoken_formula", "formal"),
    ("to be honest", "phrase", "informal"),
]

LINES = [
    ("Maya", "Thank you for having me, it is a pleasure to be here."),
    ("Paul", "Welcome. Tell me why you applied for this role."),
    ("Maya", "I am particularly interested in data work for a growing team."),
    ("Paul", "What would you say is your greatest quality?"),
    ("Maya", "My greatest strength is staying calm and organised."),
    ("Paul", "Can you work under pressure?"),
    ("Maya", "Yes, I can work under pressure and still meet a deadline."),
    ("Paul", "Do you prefer working alone?"),
    ("Maya", "To be honest, I am a team player and I like to take the initiative."),
    ("Paul", "Good. Do you have any questions for us?"),
]


def unit_output() -> dict[str, Any]:
    return {
        "formulas": [
            {
                "text": text,
                "item_type": kind,
                "function_en": f"Function {i}",
                "function_fr": f"Fonction {i}",
                "register": register,
            }
            for i, (text, kind, register) in enumerate(FORMULAS)
        ],
        "dialogue": {
            "setting_en": "A job interview in a small office.",
            "setting_fr": "Un entretien d'embauche dans un petit bureau.",
            "speakers": ["Maya", "Paul"],
            "lines": [{"speaker": s, "text": t} for s, t in LINES],
        },
        "shadowing": [1, 3, 5, 7, 9],
        "final_task": {
            "prompt_en": "You are in an interview. Explain why you suit the job.",
            "prompt_fr": "Vous êtes en entretien. Expliquez pourquoi le poste vous convient.",
            "minutes": 1,
            "formula_refs": ["f1", "f2", "f3"],
        },
    }


def _short_line(data: dict[str, Any]) -> None:
    data["dialogue"]["lines"][2]["text"] = "Welcome."


def _long_line(data: dict[str, Any]) -> None:
    data["dialogue"]["lines"][4]["text"] = " ".join(["word"] * 26)


def _duplicate_formula(data: dict[str, Any]) -> None:
    data["formulas"][1]["text"] = "  THANK YOU for having me. "


def _absent_formulas(data: dict[str, Any]) -> None:
    for line in data["dialogue"]["lines"]:
        line["text"] = "Nothing from the list is said in this very long line."


def _unknown_ref(data: dict[str, Any]) -> None:
    data["final_task"]["formula_refs"] = ["f1", "f2", "f99"]


def _bad_ref_format(data: dict[str, Any]) -> None:
    data["final_task"]["formula_refs"] = ["f1", "f2", "one"]


def _duplicate_ref(data: dict[str, Any]) -> None:
    data["final_task"]["formula_refs"] = ["f1", "f2", "f2"]


def _line_out_of_range(data: dict[str, Any]) -> None:
    data["shadowing"] = [1, 3, 5, 7, 11]


def _repeated_line(data: dict[str, Any]) -> None:
    data["shadowing"] = [1, 3, 5, 7, 7]


def _empty_text(data: dict[str, Any]) -> None:
    data["formulas"][0]["function_fr"] = "  "


def _unknown_speaker(data: dict[str, Any]) -> None:
    data["dialogue"]["lines"][0]["speaker"] = "Zed"


def _same_speakers(data: dict[str, Any]) -> None:
    data["dialogue"]["speakers"] = ["Maya", "maya"]


def _too_few_formulas(data: dict[str, Any]) -> None:
    data["formulas"] = data["formulas"][:7]


def _two_refs(data: dict[str, Any]) -> None:
    data["final_task"]["formula_refs"] = ["f1", "f2"]


def _three_minutes(data: dict[str, Any]) -> None:
    data["final_task"]["minutes"] = 3


def _too_long_formula(data: dict[str, Any]) -> None:
    data["formulas"][0]["text"] = "x" * 121


BREAKS = {
    "short_line": _short_line,
    "long_line": _long_line,
    "duplicate_formula": _duplicate_formula,
    "absent_formulas": _absent_formulas,
    "unknown_ref": _unknown_ref,
    "bad_ref_format": _bad_ref_format,
    "duplicate_ref": _duplicate_ref,
    "line_out_of_range": _line_out_of_range,
    "repeated_line": _repeated_line,
    "empty_text": _empty_text,
    "unknown_speaker": _unknown_speaker,
    "same_speakers": _same_speakers,
    "too_few_formulas": _too_few_formulas,
    "two_refs": _two_refs,
    "three_minutes": _three_minutes,
    "too_long_formula": _too_long_formula,
}


def broken(change: str) -> dict[str, Any]:
    data = copy.deepcopy(unit_output())
    BREAKS[change](data)
    return data
