"""Builders of `consolidation_task` outputs for the tests (fictional data)."""

from copy import deepcopy
from typing import Any

from app.domain.consolidation import term_ref


def task_output(
    refs: list[str] | None = None, task_type: str = "talk", **changes: Any
) -> dict[str, Any]:
    """A valid task: the references spread over four sections."""
    refs = refs if refs is not None else [term_ref(i) for i in range(10)]
    sections = []
    for n, name in enumerate(["Introduction", "Context", "Method", "Results"]):
        sections.append(
            {
                "heading_en": name,
                "heading_fr": f"{name} (fr)",
                "guidance_en": f"Say what belongs to {name.lower()}.",
                "guidance_fr": f"Dites ce qui appartient à {name.lower()}.",
                "term_refs": refs[n::4],
            }
        )
    output: dict[str, Any] = {
        "task_type": task_type,
        "title_en": "Presenting a reading on causal inference",
        "title_fr": "Présenter une lecture sur l'inférence causale",
        "prompt_en": "Present the main ideas of the reading to your seminar group.",
        "prompt_fr": "Présentez les idées principales de la lecture à votre groupe de séminaire.",
        "audience_en": "Your seminar group",
        "audience_fr": "Votre groupe de séminaire",
        "target_minutes": 3,
        "sections": sections,
    }
    output.update(deepcopy(changes))
    return output


BROKEN = [
    "unknown_ref",
    "missing_ref",
    "repeated_ref",
    "wrong_type",
    "empty_title",
    "empty_guidance",
    "too_few_sections",
    "too_many_sections",
    "minutes_zero",
    "minutes_seven",
    "long_title",
    "long_guidance",
]


def broken(change: str) -> dict[str, Any]:
    output = task_output()
    sections = output["sections"]
    match change:
        case "unknown_ref":
            sections[0]["term_refs"].append("t99")
        case "missing_ref":
            sections[0]["term_refs"].pop(0)
        case "repeated_ref":
            sections[1]["term_refs"].append(sections[0]["term_refs"][0])
        case "wrong_type":
            output["task_type"] = "speech"
        case "empty_title":
            output["title_fr"] = "  "
        case "empty_guidance":
            sections[2]["guidance_en"] = " "
        case "too_few_sections":
            output["sections"] = sections[:2]
        case "too_many_sections":
            output["sections"] = [*sections, *deepcopy(sections[:3])]
        case "minutes_zero":
            output["target_minutes"] = 0
        case "minutes_seven":
            output["target_minutes"] = 7
        case "long_title":
            output["title_en"] = "x" * 151
        case "long_guidance":
            sections[0]["guidance_fr"] = "x" * 401
        case _:
            raise ValueError(change)
    return output


TERMS = [
    "shed light on",
    "causal effect",
    "control for",
    "confounder",
    "treatment group",
    "sample size",
    "fixed effects",
    "robust to",
    "selection bias",
    "standard error",
]
# Eight terms used well, "selection bias" used wrongly (the verb does not agree), the last absent.
TEXT = (
    "In this reading the authors want to shed light on a causal effect. "
    "They control for a confounder in every model. "
    "The treatment group is compared with a control group and the sample size is large. "
    "Fixed effects are robust to many problems. "
    "Selection bias are a big problem."
)
WRONG = "Selection bias are"
MISUSED_REF = 8


def corrected_output(text: str = TEXT, *, misused: bool = True, checks: bool = True) -> dict:
    """A valid `production_correction` answer for `TEXT`: one error tied to "selection bias"."""
    from app.domain.sentences import split_sentences
    from tests.correction_support import error

    sentences = split_sentences(text)
    last = sentences[-1].index
    errors = (
        [error(last, WRONG, "Selection bias is", "lexis.wrong_word", target_ref=MISUSED_REF)]
        if misused
        else []
    )
    target_checks = []
    if checks:
        for ref in range(9):
            wrong = misused and ref == MISUSED_REF
            target_checks.append(
                {"ref": ref, "used": True, "used_correctly": not wrong, "comment": ""}
            )
    return {
        "sentences": [
            {
                "index": s.index,
                "corrected": "Selection bias is a big problem."
                if misused and s.index == last
                else s.text,
                "status": "corrected" if misused and s.index == last else "correct",
            }
            for s in sentences
        ],
        "corrected_text": text,
        "natural_text": text,
        "errors": errors,
        "naturalness_notes": [],
        "targets": target_checks,
        "overall_comment": "Clear. Watch the agreement.",
    }
