"""Usage sheet v1 and the exercise rules (pure domain, M3.b)."""

import pytest
from pydantic import ValidationError

from app.domain import exercises as ex
from app.domain.usage_sheet import (
    SHEET_FIELDS,
    GeneratedSheet,
    UsageSheet,
    read_sheet,
    skeleton_sheet,
)
from tests.enrichment_support import generated_sheet

# --- Sheet models --------------------------------------------------------------------------------


def test_both_models_share_the_same_fields() -> None:
    assert set(SHEET_FIELDS) == set(GeneratedSheet.model_fields)
    assert "schema_version" in UsageSheet.model_fields


def test_a_hand_typed_sheet_may_be_partial() -> None:
    sheet = UsageSheet.model_validate({"translation_fr": ["rendre compte de"]})
    assert sheet.schema_version == 1 and sheet.examples == []
    assert UsageSheet.model_validate({"definition_simple": "to explain"}).definition_simple


@pytest.mark.parametrize(
    "content",
    [{}, {"definition_simple": "  "}, {"translation_fr": []}, {"usage_notes": "only notes"}],
)
def test_a_stored_sheet_needs_a_definition_or_a_translation(content: dict) -> None:
    with pytest.raises(ValidationError, match="simple definition or a French translation"):
        UsageSheet.model_validate(content)


def test_stored_sheet_refuses_unknown_fields_and_long_lists() -> None:
    with pytest.raises(ValidationError):
        UsageSheet.model_validate({"translation_fr": ["a"], "colour": "red"})
    with pytest.raises(ValidationError):
        UsageSheet.model_validate({"translation_fr": ["a", "b", "c", "d"]})
    with pytest.raises(ValidationError):
        UsageSheet.model_validate({"translation_fr": ["a"], "schema_version": 2})


def test_skeleton_is_empty_but_readable() -> None:
    content = skeleton_sheet("noun")
    assert content["part_of_speech"] == "noun" and content["translation_fr"] == []
    assert read_sheet(content).part_of_speech == "noun"
    with pytest.raises(ValidationError):
        UsageSheet.model_validate(content)


def test_generated_sheet_is_strict() -> None:
    good = generated_sheet("to account for")
    GeneratedSheet.model_validate(good)
    for field, value in [
        ("translation_fr", []),
        ("collocations", good["collocations"][:2]),
        ("examples", good["examples"][:2]),
        ("register_level", "slang"),
    ]:
        with pytest.raises(ValidationError):
            GeneratedSheet.model_validate({**good, field: value})
    missing = dict(good)
    del missing["usage_notes"]
    with pytest.raises(ValidationError):
        GeneratedSheet.model_validate(missing)


def test_generated_sheet_converts_to_the_stored_form() -> None:
    stored = GeneratedSheet.model_validate(generated_sheet("heteroskedasticity")).to_stored()
    assert stored.schema_version == 1
    assert stored.pronunciation is not None and stored.pronunciation.ipa_us
    assert stored.model_dump(mode="json")["examples"][0]["kind"] == "academic"


# --- Term forms ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "form", "expected"),
    [
        ("to account for", "account for", True),
        ("to account for", "accounted for", True),
        ("shed light on", "sheds light on", True),
        ("draw a conclusion", "drew a conclusion", True),
        ("draw a conclusion", "drew the conclusion", False),
        ("go ahead", "went ahead", False),
        ("heteroskedasticity", "heteroskedasticity", True),
        ("heteroskedasticity", "variance", False),
        ("to account for sth", "account for", True),
        ("account for", "account", False),
    ],
)
def test_is_form_of(term: str, form: str, expected: bool) -> None:
    assert ex.is_form_of(term, form) is expected


def test_contains_term_accepts_declared_irregular_forms_only() -> None:
    sentence = "She drew a conclusion from the data."
    assert not ex.contains_term("draw a conclusion", sentence)
    assert ex.contains_term("draw a conclusion", sentence, ["drew a conclusion"])
    assert not ex.contains_term("draw a conclusion", sentence, ["the data"])
    assert ex.contains_term("to account for", "We accounted for regional effects.")


def test_without_to() -> None:
    assert ex.without_to("to account for") == "account for"
    assert ex.without_to("tomato") == "tomato"
    assert ex.without_to("To Be Honest") == "Be Honest"


# --- Rules ---------------------------------------------------------------------------------------


def test_examples_must_contain_the_term_and_cover_academic_and_spoken() -> None:
    term = "to account for"
    good = [
        ("Our model accounts for regional effects.", "academic"),
        ("That accounts for the delay, I think.", "spoken"),
    ]
    assert ex.check_examples(term, good, [], "sheets[0]") == []
    bad = [("The weather was nice.", "academic"), ("It explains a lot.", "general")]
    problems = ex.check_examples(term, bad, [], "sheets[0]")
    assert "sheets[0].examples[0]: the sentence must contain the term" in problems
    assert any("'spoken'" in p for p in problems)
    assert not any("'academic'" in p for p in problems)


@pytest.mark.parametrize(
    ("sentence", "answer", "accepted", "fragment"),
    [
        ("We ___ regional effects.", "account for", ["accounted for"], None),
        ("We ___ regional ___ effects.", "account for", [], "exactly one ___"),
        ("We account for regional effects.", "account for", [], "exactly one ___"),
        ("We ___ regional effects.", "to account for", [], "initial 'to'"),
        ("We ___ regional effects.", "explain", [], "inflected form"),
        ("We ___ regional effects.", "account for", ["explain"], "accepted[0]"),
    ],
)
def test_gap_fill_rules(
    sentence: str, answer: str, accepted: list[str], fragment: str | None
) -> None:
    problems = ex.check_gap_fill("to account for", sentence, answer, accepted, "g")
    if fragment is None:
        assert problems == []
    else:
        assert any(fragment in p for p in problems), problems


def test_gap_fill_completed_sentence_must_contain_the_term() -> None:
    # The answer is a form of the term but the gap splits it from the rest of the sentence.
    problems = ex.check_gap_fill("shed light on", "Results ___ the issue.", "shed light", [], "g")
    assert any("inflected form" in p for p in problems)


def test_active_recall_prompts_never_contain_the_term_or_its_family() -> None:
    family = ["accountable", "accountability"]
    assert ex.check_no_term("to account for", "Explain why prices rose.", family, "p") == []
    assert ex.check_no_term("to account for", "What accounts for the rise?", family, "p")
    assert ex.check_no_term("to account for", "Who is accountable here?", family, "p")


def test_exercise_sentences_must_not_copy_an_example() -> None:
    examples = ["Our model accounts for regional effects."]
    assert ex.check_not_copied("our model accounts for regional effects", examples, "r")
    assert ex.check_not_copied("Their model accounts for time effects.", examples, "r") == []


def test_typed_recall_is_derived_from_the_sheet() -> None:
    content = ex.typed_recall_content(
        "to account for", ["rendre compte de"], "to explain", ["accounted for", "account for"]
    )
    assert content == {
        "cue_fr": "rendre compte de",
        "cue_definition": "to explain",
        "answer": "account for",
        "accepted": ["accounted for"],
    }
    assert ex.typed_recall_content("x", [], None) is None


def test_validate_content_per_type() -> None:
    assert ex.validate_content("gap_fill", {"sentence": "a ___ b", "answer": "x"})["accepted"] == []
    with pytest.raises(ValidationError):
        ex.validate_content("gap_fill", {"sentence": "no gap", "answer": "x"})
    with pytest.raises(ValidationError):
        ex.validate_content(
            "recognition_in_sentence",
            {"sentence": "s", "meaning": "m", "meaning_fr": "f", "distractors": ["a", "b"]},
        )
    with pytest.raises(ValueError, match="unknown exercise type"):
        ex.validate_content("crossword", {})
    directions = {name: d.value for name, (d, _) in ex.EXERCISE_TYPES.items()}
    assert directions["recognition_in_sentence"] == directions["listening_comprehension"]
    assert directions["recognition_in_sentence"] == "receptive"
