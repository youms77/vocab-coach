"""Cards made from errors and recurring errors (app/domain/error_cards.py): pure."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import exercises as ex
from app.domain.error_cards import (
    ErrorRow,
    NotCardable,
    group_recurring,
    pair_key,
    plan_card,
    without_keys,
)
from app.domain.grading import Outcome, grade_typed
from app.domain.usage_sheet import is_usable, read_sheet

DAY = datetime(2026, 9, 1, 12, tzinfo=UTC)


def campus(**changes: str) -> dict[str, str]:
    base = {
        "erroneous_text": "in campus",
        "correction": "on campus",
        "original_text": "Most of my friends live in campus this year.",
        "explanation": "With 'campus', English uses 'on': on campus.",
    }
    return {**base, **changes}


def test_the_term_is_the_correction_and_the_gap_blanks_the_changed_word() -> None:
    plan = plan_card(**campus())
    assert plan.term == "on campus"
    assert plan.sentence == "Most of my friends live on campus this year."
    assert plan.gap_fill == {
        "sentence": "Most of my friends live ___ campus this year.",
        "answer": "on",
        "accepted": [],
    }
    ex.validate_content(ex.GAP_FILL, plan.gap_fill or {})


def test_the_sheet_is_usable_and_declares_the_wrong_forms_as_pitfalls() -> None:
    plan = plan_card(**campus())
    assert is_usable("complete", plan.sheet)
    sheet = read_sheet(plan.sheet)
    assert sheet.definition_simple == "With 'campus', English uses 'on': on campus."
    assert [p.wrong for p in sheet.french_speaker_pitfalls] == ["in campus", "in"]
    assert [e.sentence for e in sheet.examples] == [plan.sentence]


def test_without_an_explanation_the_rule_is_generated() -> None:
    sheet = read_sheet(plan_card(**campus(explanation="")).sheet)
    assert sheet.definition_simple == 'Say "on campus", not "in campus".'


def test_without_the_original_sentence_a_sentence_must_be_given() -> None:
    with pytest.raises(NotCardable) as excinfo:
        plan_card(**campus(original_text=""))
    assert excinfo.value.reason == "no_context"
    plan = plan_card(**campus(original_text=""), sentence="We met on campus last week.")
    assert plan.sentence == "We met on campus last week."
    assert plan.gap_fill is not None
    assert plan.gap_fill["sentence"] == "We met ___ campus last week."


def test_a_given_sentence_replaces_the_original_one() -> None:
    plan = plan_card(**campus(), sentence="They study on campus.")
    assert plan.sentence == "They study on campus."
    assert read_sheet(plan.sheet).examples[0].sentence == "They study on campus."


@pytest.mark.parametrize("sentence", ["They study at home.", "x" * 500 + " on campus"])
def test_a_sentence_without_the_correction_or_too_long_is_refused(sentence: str) -> None:
    with pytest.raises(NotCardable) as excinfo:
        plan_card(**campus(), sentence=sentence)
    assert excinfo.value.reason in {"invalid_sentence", "no_context"}


def test_an_original_sentence_that_lacks_the_wrong_form_needs_a_sentence() -> None:
    with pytest.raises(NotCardable) as excinfo:
        plan_card(**campus(original_text="Nothing to see here."))
    assert excinfo.value.reason == "no_context"


def test_a_correction_that_only_removes_words_blanks_the_whole_fragment() -> None:
    plan = plan_card(
        erroneous_text="go to home",
        correction="go home",
        original_text="I go to home every evening.",
        explanation="",
    )
    assert plan.term == "go home"
    assert plan.gap_fill is not None
    assert plan.gap_fill["sentence"] == "I ___ every evening."
    assert plan.gap_fill["answer"] == "go home"


def test_a_drill_error_gives_a_short_term_and_the_sentence_as_context() -> None:
    plan = plan_card(
        erroneous_text="The data have been cleaned since Monday.",
        correction="The data has been cleaned since Monday.",
        original_text="The data ___ been cleaned since Monday.",
        explanation="Data is treated as singular here.",
    )
    assert plan.sentence == "The data has been cleaned since Monday."
    assert plan.term == "data has been"
    assert plan.gap_fill is not None
    assert plan.gap_fill["sentence"] == "The data ___ been cleaned since Monday."
    assert plan.gap_fill["answer"] == "has"
    assert [p.wrong for p in read_sheet(plan.sheet).french_speaker_pitfalls] == [
        "The data have been cleaned since Monday",
        "have",
    ]


def test_a_correction_too_long_for_a_term_needs_a_term_of_the_user() -> None:
    long_sentence = "One two three four five six seven eight nine ten."
    wrong = "Uno dos tres cuatro cinco seis siete ocho nueve diez."
    with pytest.raises(NotCardable) as excinfo:
        plan_card(
            erroneous_text=wrong,
            correction=long_sentence,
        )
    assert excinfo.value.reason == "too_long"
    plan = plan_card(
        erroneous_text=wrong,
        correction=long_sentence,
        term="nine ten",
    )
    assert plan.term == "nine ten"


@pytest.mark.parametrize("term", ["", "  ", "a b c d e f g", "x" * 61])
def test_an_unusable_term_is_refused(term: str) -> None:
    with pytest.raises(NotCardable) as excinfo:
        plan_card(**campus(), term=term)
    assert excinfo.value.reason == "invalid_term"


@pytest.mark.parametrize(
    ("wrong", "right"),
    [("on campus", "On campus"), ("on campus.", "on campus"), ("", "on campus"), ("x", " ")],
)
def test_an_error_without_a_real_correction_is_refused(wrong: str, right: str) -> None:
    with pytest.raises(NotCardable) as excinfo:
        plan_card(erroneous_text=wrong, correction=right)
    assert excinfo.value.reason == "no_correction"


def test_the_wrong_form_is_a_mistake_in_a_review_not_a_typo() -> None:
    """The point of the pitfalls: "in campus" is one edit from "on campus"."""
    plan = plan_card(**campus())
    sheet = read_sheet(plan.sheet)
    confusions = {
        "in campus": object(),
        "in": object(),
    }
    typed = grade_typed(
        exercise_type=ex.TYPED_RECALL,
        term=plan.term,
        answer=plan.term,
        accepted=[],
        given="in campus",
        estimate_seconds=10,
    )
    assert typed.outcome is Outcome.TYPO  # without the pitfall it would be a typo...
    assert {p.wrong for p in sheet.french_speaker_pitfalls} >= set(
        confusions
    )  # ...and it is listed


# --- Recurring errors ----------------------------------------------------------------------------


def row(error_id: int, wrong: str, right: str, code: str, days: int) -> ErrorRow:
    return ErrorRow(error_id, wrong, right, code, DAY + timedelta(days=days))


def test_the_same_pair_seen_twice_is_a_suggestion_with_its_latest_occurrence() -> None:
    suggestions = group_recurring(
        [
            row(1, "in campus", "on campus", "grammar.preposition.place", 0),
            row(2, "in university", "at university", "grammar.preposition.fixed_expression", 1),
            row(3, "In  Campus", "on campus.", "grammar.preposition.fixed_expression", 5),
            row(4, "in campus", "on campus", "grammar.preposition.fixed_expression", 3),
        ]
    )
    assert len(suggestions) == 1
    only = suggestions[0]
    assert only.key == pair_key("in campus", "on campus") == "in campus => on campus"
    assert only.count == 3
    assert only.latest_error_id == 3
    assert only.erroneous_text == "In  Campus"
    assert only.error_ids == (3, 4, 1)
    assert only.category_code == "grammar.preposition.fixed_expression"
    assert only.first_at == DAY and only.last_at == DAY + timedelta(days=5)


def test_a_single_occurrence_is_not_recurring_and_min_count_can_change() -> None:
    rows = [row(1, "in campus", "on campus", "grammar.preposition.place", 0)]
    assert group_recurring(rows) == []
    assert len(group_recurring(rows, min_count=1)) == 1


def test_the_most_frequent_comes_first_then_the_most_recent_then_the_key() -> None:
    rows = [
        row(1, "a1", "b1", "x.y", 5),
        row(2, "a1", "b1", "x.y", 6),
        row(3, "a2", "b2", "x.y", 0),
        row(4, "a2", "b2", "x.y", 1),
        row(5, "a2", "b2", "x.y", 2),
        row(6, "a3", "b3", "x.y", 6),
        row(7, "a3", "b3", "x.y", 6),
    ]
    assert [s.key for s in group_recurring(rows)] == ["a2 => b2", "a1 => b1", "a3 => b3"]
    assert [s.key for s in group_recurring(list(reversed(rows)))] == [
        "a2 => b2",
        "a1 => b1",
        "a3 => b3",
    ]


def test_words_without_letters_do_not_make_a_group() -> None:
    assert group_recurring([row(1, "...", "!", "x.y", 0), row(2, "...", "!", "x.y", 1)]) == []


def test_hidden_keys_are_left_out() -> None:
    rows = [row(i, "a", "b", "x.y", i) for i in range(3)] + [row(9, "c", "d", "x.y", 0)] * 2
    suggestions = group_recurring(rows)
    assert [s.key for s in without_keys(suggestions, ["a => b"])] == ["c => d"]
