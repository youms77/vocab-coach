"""Builders of valid (and deliberately broken) AI outputs for the enrichment tests (fictional)."""

from typing import Any

from app.domain.exercises import without_to


def generated_sheet(term: str) -> dict[str, Any]:
    """Sheet fields that satisfy `GeneratedSheet` and every business rule for `term`."""
    t = without_to(term)
    return {
        "part_of_speech": "verb phrase",
        "register_level": "academic",
        "register_note": None,
        "meaning_in_context": f"Here, {t} means to explain a cause.",
        "definition_simple": "to be the reason for something",
        "translation_fr": ["expliquer", "rendre compte de"],
        "other_meanings": [{"definition": "to make up a share", "translation_fr": "représenter"}],
        "usage_notes": "Common in reports and papers.",
        "collocations": [
            {"pattern": f"{t} the difference", "example": None},
            {"pattern": f"fully {t}", "example": None},
            {"pattern": f"{t} most of", "example": None},
        ],
        "examples": [
            {"sentence": f"Our regression must {t} regional effects.", "kind": "academic"},
            {"sentence": f"Honestly, that would {t} the delay.", "kind": "spoken"},
            {"sentence": f"Rain may {t} the late trains.", "kind": "general"},
        ],
        "word_family": [],
        "pronunciation": {"ipa_us": "əˈkaʊnt fɔr", "stressed_syllable": "COUNT", "note": None},
        "french_speaker_pitfalls": [
            {"wrong": "explain of", "right": "explain", "explanation": "No preposition."}
        ],
        "confusables": [{"term": "count on", "difference": "means to rely on"}],
    }


def generated_entry(ref: int, term: str) -> dict[str, Any]:
    """One entry of `EnrichmentBatchOutput.sheets`: sheet fields and exercises, flat."""
    t = without_to(term)
    return {
        "ref": ref,
        "term": term,
        **generated_sheet(term),
        "gap_fills": [
            {
                "sentence": "In the first study, we ___ the main effect.",
                "answer": t,
                "accepted": [],
            },
            {"sentence": "Lower costs ___ the higher profit.", "answer": t, "accepted": []},
        ],
        "recognitions": [
            {
                "sentence": f"During the meeting, she tried to {t} the gap.",
                "meaning": "to explain",
                "meaning_fr": "expliquer",
                "distractors": ["to hide", "to measure", "to forget"],
            },
            {
                "sentence": f"Can anyone {t} these numbers?",
                "meaning": "to explain",
                "meaning_fr": "expliquer",
                "distractors": ["to print", "to add", "to sell"],
            },
        ],
        "productions": [
            {
                "situation": "Tell your supervisor why the survey answers changed.",
                "example_answer": f"New questions {t} the change.",
            },
            {
                "situation": "Explain to a friend why the bus was late.",
                "example_answer": f"The snow should {t} it.",
            },
        ],
        "spoken": {
            "question": "Why did your results change between the two years?",
            "example_answer": f"A new policy may {t} most of it.",
        },
    }


def batch_output(terms: list[str]) -> dict[str, Any]:
    return {"sheets": [generated_entry(ref, term) for ref, term in enumerate(terms)]}


def broken_entry(ref: int, term: str) -> dict[str, Any]:
    """An entry whose first example does not contain the term (repairable rule)."""
    entry = generated_entry(ref, term)
    entry["examples"][0]["sentence"] = "The weather was lovely."
    return entry
