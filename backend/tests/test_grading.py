"""Automatic grading (app/domain/grading.py)."""

import pytest

from app.domain import exercises as ex
from app.domain.grading import (
    DiffPart,
    Outcome,
    char_diff,
    check_production,
    comparable,
    damerau_levenshtein,
    grade_choice,
    grade_typed,
    normalize_answer,
    typo_tolerance,
)
from app.domain.srs import Rating

ESTIMATE = 25.0  # seconds, typed productive class


def typed(
    given: str | None,
    *,
    term: str = "account for",
    answer: str = "account for",
    accepted: tuple[str, ...] = (),
    exercise_type: str = ex.TYPED_RECALL,
    confusions: tuple[str, ...] = (),
    ms: int | None = 5000,
):
    return grade_typed(
        exercise_type=exercise_type,
        term=term,
        answer=answer,
        accepted=accepted,
        given=given,
        confusions=[comparable(c, term) for c in confusions],
        response_time_ms=ms,
        estimate_seconds=ESTIMATE,
    )


# --- Damerau-Levenshtein -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("", "", 0),
        ("effect", "effect", 0),
        ("", "abc", 3),
        ("abc", "", 3),
        ("effect", "efect", 1),  # deletion
        ("effect", "efffect", 1),  # insertion
        ("effect", "effest", 1),  # substitution
        ("effect", "effcet", 1),  # transposition of two adjacent letters
        ("ca", "abc", 3),  # OSA: no substring edited twice
        ("kitten", "sitting", 3),
    ],
)
def test_damerau_levenshtein(a: str, b: str, distance: int) -> None:
    assert damerau_levenshtein(a, b) == distance
    assert damerau_levenshtein(b, a) == distance


def test_typo_tolerance_thresholds() -> None:
    assert [typo_tolerance(n) for n in (1, 3, 4, 8, 9, 20)] == [0, 0, 1, 1, 2, 2]


# --- Normalisation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Account   FOR. ", "account for"),
        ("«rule out»", "rule out"),
        ("it’s worth noting", "it's worth noting"),
        ("ﬁnding", "finding"),  # NFKC ligature
        ("...", ""),
    ],
)
def test_normalize_answer(raw: str, expected: str) -> None:
    assert normalize_answer(raw) == expected


# --- Typed answers -------------------------------------------------------------------------------


def test_exact_and_accepted_forms() -> None:
    assert typed("Account for.").outcome == Outcome.EXACT
    result = typed("accounts for", accepted=("accounts for",))
    assert result.outcome == Outcome.EXACT
    assert result.proposed_rating == Rating.GOOD
    assert result.expected == "account for"
    assert result.accepted == ["accounts for"]
    assert result.diff is None


@pytest.mark.parametrize("given", ["to account for", "account for"])
@pytest.mark.parametrize("answer", ["to account for", "account for"])
def test_initial_to_is_optional_on_both_sides(given: str, answer: str) -> None:
    assert typed(given, term="to account for", answer=answer).outcome == Outcome.EXACT


def test_to_is_not_dropped_for_other_terms() -> None:
    result = typed("to a large extent", term="to a large extent", answer="to a large extent")
    assert result.outcome == Outcome.EXACT
    # "to" is optional only for a term that starts with it.
    assert typed("to rule out", term="rule out", answer="rule out").outcome == Outcome.WRONG


def test_typographic_apostrophes() -> None:
    result = typed("It’s worth noting", term="it's worth noting", answer="it's worth noting")
    assert result.outcome == Outcome.EXACT


def test_regular_form_only_in_typed_recall() -> None:
    assert typed("accounted for").outcome == Outcome.FORM
    assert typed("accounted for").proposed_rating == Rating.GOOD
    # A gap-fill expects the form that fits the sentence.
    gap = typed("accounting for", exercise_type=ex.GAP_FILL, answer="accounts for")
    assert gap.outcome != Outcome.FORM


def test_a_truncated_word_is_a_typo_not_a_form() -> None:
    # The stemmer maps "rule" and "rul" to the same stem; only longer forms are inflections.
    assert typed("rul out", term="rule out", answer="rule out").outcome == Outcome.TYPO
    assert typed("ruled out", term="rule out", answer="rule out").outcome == Outcome.FORM
    assert typed("rules out", term="rule out", answer="rule out").outcome == Outcome.FORM


def test_a_word_with_the_same_first_letter_is_not_a_form() -> None:
    # is_form_of() would accept it (irregular verbs); grading does not.
    result = typed("cat", term="confounder", answer="confounder")
    assert result.outcome == Outcome.WRONG


@pytest.mark.parametrize(
    ("answer", "given", "outcome"),
    [
        # up to 3 characters: no typo allowed
        ("set", "sat", Outcome.WRONG),
        ("set", "set", Outcome.EXACT),
        # 4 to 8 characters: one edit
        ("effect", "efect", Outcome.TYPO),
        ("effect", "effcet", Outcome.TYPO),
        ("effect", "efct", Outcome.WRONG),
        ("question", "qeustion", Outcome.TYPO),
        # 9 characters and more: two edits
        ("counterfactual", "conterfactul", Outcome.TYPO),
        ("counterfactual", "contrfactul", Outcome.WRONG),
    ],
)
def test_typo_thresholds(answer: str, given: str, outcome: Outcome) -> None:
    result = typed(given, term=answer, answer=answer, exercise_type=ex.GAP_FILL)
    assert result.outcome == outcome
    if outcome == Outcome.TYPO:
        assert result.proposed_rating == Rating.HARD
        assert result.diff is not None


def test_typo_diff_is_character_by_character() -> None:
    result = typed("efect", term="effect", answer="effect")
    assert result.diff == [
        DiffPart("equal", "e", "e"),
        DiffPart("insert", "", "f"),
        DiffPart("equal", "fect", "fect"),
    ]
    assert char_diff("abc", "abc") == [DiffPart("equal", "abc", "abc")]


def test_confusion_is_wrong_not_a_typo() -> None:
    # "affect" is one edit from "effect", but it is a word of its own.
    plain = typed("affect", term="effect", answer="effect")
    assert plain.outcome == Outcome.TYPO
    confused = typed("affect", term="effect", answer="effect", confusions=("Affect",))
    assert confused.outcome == Outcome.WRONG
    assert confused.proposed_rating == Rating.AGAIN
    assert confused.diff is None


@pytest.mark.parametrize("given", [None, "", "   ", "?!"])
def test_empty(given: str | None) -> None:
    result = typed(given)
    assert result.outcome == Outcome.EMPTY
    assert result.proposed_rating == Rating.AGAIN


def test_wrong() -> None:
    result = typed("explain")
    assert result.outcome == Outcome.WRONG
    assert result.proposed_rating == Rating.AGAIN


def test_slow_correct_answer_is_hard() -> None:
    assert typed("account for", ms=int(2 * ESTIMATE * 1000)).proposed_rating == Rating.GOOD
    assert typed("account for", ms=int(2 * ESTIMATE * 1000) + 1).proposed_rating == Rating.HARD
    assert typed("accounted for", ms=60_000).proposed_rating == Rating.HARD
    assert typed("account for", ms=None).proposed_rating == Rating.GOOD


def test_easy_is_never_proposed() -> None:
    for given in ("account for", "accounted for", "acount for", "nothing", "", None):
        for ms in (0, 1, 10_000, 300_000, None):
            assert typed(given, ms=ms).proposed_rating != Rating.EASY


# --- Choice answers ------------------------------------------------------------------------------


def test_choice() -> None:
    options = ["a", "b", "c", "d"]
    right = grade_choice(options=options, correct_index=2, chosen_index=2, estimate_seconds=15)
    assert (right.outcome, right.proposed_rating, right.expected) == (
        Outcome.EXACT,
        Rating.GOOD,
        "c",
    )
    wrong = grade_choice(options=options, correct_index=2, chosen_index=0, estimate_seconds=15)
    assert (wrong.outcome, wrong.proposed_rating) == (Outcome.WRONG, Rating.AGAIN)
    slow = grade_choice(
        options=options,
        correct_index=2,
        chosen_index=2,
        response_time_ms=31_000,
        estimate_seconds=15,
    )
    assert slow.proposed_rating == Rating.HARD
    none = grade_choice(options=options, correct_index=1, chosen_index=None, estimate_seconds=15)
    assert none.outcome == Outcome.EMPTY


# --- Productions ---------------------------------------------------------------------------------


def test_production_is_self_graded_and_checks_the_term() -> None:
    ok = check_production("rule out", "We ruled out reverse causality.")
    assert (ok.outcome, ok.proposed_rating, ok.warnings) == (None, None, [])
    missing = check_production("rule out", "We excluded reverse causality.")
    assert missing.warnings == ["term_missing"]
    assert missing.proposed_rating is None
    assert check_production("rule out", "").warnings == []
