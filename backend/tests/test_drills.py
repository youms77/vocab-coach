"""Drill rules (app/domain/drills.py) and the `targeted_drill` schema: pure."""

import random

import pytest
from pydantic import ValidationError

from app.ai.schemas.targeted_drill import TargetedDrillOutput, drill_context
from app.domain.drills import (
    SOLUTION_KEYS,
    correct_index,
    fill_gap,
    grade_item,
    item_result,
    options_order,
    public_item,
    score,
)
from tests.drill_support import BROKEN, FIXED, broken, choice_item, drill_output, gap_item

CODES = {FIXED}


def tense_item() -> dict[str, object]:
    return gap_item(
        0,
        sentence="The data ___ cleaned since Monday.",
        answer="has been",
        accepted=["'s been"],
        category_code="grammar.tense.past_simple_vs_present_perfect",
    )


def test_fill_gap() -> None:
    assert fill_gap("I live ___ campus.", " on ") == "I live on campus."
    assert fill_gap("I live ___ campus.", "") == "I live ___ campus."


@pytest.mark.parametrize(
    ("given", "outcome"),
    [
        ("has been", "exact"),
        ("  Has   Been. ", "exact"),  # case, spaces, punctuation at the ends
        ("’s been", "exact"),  # typographic apostrophe, an accepted form
        ("had been", "wrong"),  # no tolerance: a different tense is wrong
        ("has ben", "wrong"),  # no typo tolerance
        ("been", "wrong"),  # no "form"
        ("", "empty"),
        (" ... ", "empty"),
    ],
)
def test_gap_fill_grading_is_exact(given: str, outcome: str) -> None:
    graded = grade_item(tense_item(), None, answer=given, choice_index=None)
    assert graded.outcome == outcome


def test_a_preposition_answer_to_is_not_dropped() -> None:
    item = gap_item(0, sentence="I went ___ the library.", answer="to")
    assert grade_item(item, None, answer="to", choice_index=None).outcome == "exact"
    assert grade_item(item, None, answer="at", choice_index=None).outcome == "wrong"


def test_choice_grading_uses_the_shown_order() -> None:
    item = choice_item(1)
    shown = options_order(7, 1, item["options"])
    right = correct_index(shown, "at")
    assert right is not None and shown[right] == "at"
    assert grade_item(item, shown, answer=None, choice_index=right).outcome == "exact"
    wrong = (right + 1) % len(shown)
    graded = grade_item(item, shown, answer=None, choice_index=wrong)
    assert (graded.outcome, graded.given) == ("wrong", shown[wrong])
    assert grade_item(item, shown, answer=None, choice_index=None).outcome == "empty"


def test_the_shuffle_is_deterministic_and_not_stored() -> None:
    options = ["at", "in", "on", "by"]
    first = options_order(12, 3, options)
    assert first == options_order(12, 3, options)
    expected = list(options)
    random.Random("drill:12:3").shuffle(expected)
    assert first == expected
    assert options == ["at", "in", "on", "by"]  # the stored list is not changed
    orders = {tuple(options_order(drill, 3, options)) for drill in range(1, 30)}
    assert len(orders) > 1  # the order depends on the drill


def test_a_public_item_carries_no_solution() -> None:
    for item in (gap_item(0), choice_item(1)):
        public = public_item(5, 0, item)
        assert not SOLUTION_KEYS & set(public)
        assert set(public) == {"index", "kind", "sentence", "options"}
    assert public_item(5, 0, gap_item(0))["options"] is None


def test_item_result_and_score() -> None:
    item = choice_item(1)
    result = item_result(9, 1, item, outcome="wrong", given="in")
    shown = options_order(9, 1, item["options"])
    assert result["correct_index"] == shown.index("at")
    assert result["expected"] == "at" and result["given"] == "in"
    assert item_result(9, 0, gap_item(0), outcome="exact", given="on")["correct_index"] is None
    answers = [{"outcome": o} for o in ("exact", "wrong", "empty", "exact")]
    assert score(10, answers) == {"correct": 2, "wrong": 1, "empty": 1, "answered": 4, "total": 10}


# --- Schema --------------------------------------------------------------------------------------


def validate(output: dict[str, object], count: int = 10) -> TargetedDrillOutput:
    return TargetedDrillOutput.model_validate(output, context=drill_context(count, CODES))


def test_a_valid_drill_passes() -> None:
    drill = validate(drill_output())
    assert len(drill.items) == 10
    assert validate(drill_output(5), count=5).items[0].kind == "gap_fill"


@pytest.mark.parametrize("change", BROKEN)
def test_each_rule_is_checked(change: str) -> None:
    with pytest.raises(ValidationError) as caught:
        validate(broken(change))
    message = " ".join(str(error["msg"]) for error in caught.value.errors())
    assert "campus" not in message.replace("'campus'", "")  # locations, not the items' text


def test_without_context_only_the_shape_is_checked() -> None:
    TargetedDrillOutput.model_validate(broken("too_few_items"))
