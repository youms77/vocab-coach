"""Word-by-word comparison of a transcription with its target (app/domain/speech_compare.py)."""

import random

import pytest

from app.domain.speech_compare import (
    VERSION,
    Comparison,
    Op,
    Unrecognized,
    compare,
    equivalent,
    is_close,
    words,
)


def ops(comparison: Comparison) -> list[tuple[str, str | None, str | None]]:
    return [(step.op.value, step.target, step.heard) for step in comparison.steps]


# --- Words ------------------------------------------------------------------------------------


def test_words_drop_punctuation_and_keep_the_spelling() -> None:
    assert words("We account — for “regional” fixed-effects, don’t we?") == [
        "We",
        "account",
        "for",
        "regional",
        "fixed-effects",
        "don't",
        "we",
    ]


def test_words_keep_numbers_percent_and_final_apostrophes() -> None:
    assert words("1,000 students' notes: 3.5% (or 50 %).") == [
        "1,000",
        "students'",
        "notes",
        "3.5%",
        "or",
        "50",
        "%",
    ]


def test_underscores_and_double_hyphens_separate_words() -> None:
    assert words("snake_case word--another") == ["snake", "case", "word", "another"]


# --- Basic operations -------------------------------------------------------------------------


def test_identical_sentence_is_all_matches() -> None:
    result = compare(
        "We account for regional fixed effects.", "We account for regional fixed effects."
    )
    assert [step.op for step in result.steps] == [Op.MATCH] * 6
    assert result.unrecognized == ()
    assert (result.target_word_count, result.heard_word_count, result.recognized_count) == (6, 6, 6)
    assert result.word_accuracy == 1.0
    assert result.version == VERSION == "speech-compare-1"


def test_case_and_punctuation_do_not_matter() -> None:
    result = compare("We account, for: REGIONAL effects!", "we account for regional effects")
    assert result.word_accuracy == 1.0


def test_a_missing_word() -> None:
    result = compare("We account for regional fixed effects", "we account for fixed effects")
    assert ops(result)[3] == ("missing", "regional", None)
    assert result.unrecognized == (Unrecognized(position=3, word="regional", heard=None),)
    assert result.recognized_count == 5 and result.word_accuracy == pytest.approx(5 / 6)


def test_a_substitution() -> None:
    result = compare("We account for regional fixed effects", "we account for regional fix effects")
    assert ops(result)[4] == ("substituted", "fixed", "fix")
    assert result.unrecognized == (Unrecognized(position=4, word="fixed", heard="fix"),)


def test_an_extra_word() -> None:
    result = compare("We account for effects", "we account for the effects")
    assert ops(result) == [
        ("match", "We", "we"),
        ("match", "account", "account"),
        ("match", "for", "for"),
        ("extra", None, "the"),
        ("match", "effects", "effects"),
    ]
    assert result.unrecognized == () and result.word_accuracy == 1.0


def test_the_owner_example() -> None:
    result = compare("We account for regional fixed effects.", "we account for regional fix effect")
    assert [(u.word, u.heard) for u in result.unrecognized] == [
        ("fixed", "fix"),
        ("effects", "effect"),
    ]
    assert result.word_accuracy == pytest.approx(4 / 6)


def test_empty_transcription_leaves_every_word_missing() -> None:
    result = compare("Fixed effects matter.", "")
    assert [step.op for step in result.steps] == [Op.MISSING] * 3
    assert [u.position for u in result.unrecognized] == [0, 1, 2]
    assert result.heard_word_count == 0 and result.word_accuracy == 0.0


def test_empty_target_gives_extras_and_no_division_by_zero() -> None:
    result = compare("", "hello there")
    assert [step.op for step in result.steps] == [Op.EXTRA, Op.EXTRA]
    assert result.target_word_count == 0 and result.word_accuracy == 0.0


def test_both_empty() -> None:
    result = compare("...", "")
    assert result.steps == () and result.word_accuracy == 0.0


# --- Tolerances -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "heard"),
    [
        ("It's late", "it is late"),
        ("It's gone", "it has gone"),
        ("It's colour", "its colour"),
        ("I don't know", "I do not know"),
        ("They can't stay", "they cannot stay"),
        ("They cannot stay", "they can not stay"),
        ("We won't go", "we will not go"),
        ("We shan't go", "we shall not go"),
        ("She isn't here", "she is not here"),
        ("They're here", "they are here"),
        ("I'm here", "I am here"),
        ("We've seen it", "we have seen it"),
        ("You'll see", "you will see"),
        ("He'd say so", "he would say so"),
        ("He'd said so", "he had said so"),
        ("Let's go", "let us go"),
        ("There's a model", "there is a model"),
        ("What's new", "what has new"),
        ("The model's fit", "the models fit"),
        ("The model's good", "the model is good"),
        ("The students' notes", "the students notes"),
        ("The student's notes", "the students' notes"),
    ],
)
def test_contractions(target: str, heard: str) -> None:
    result = compare(target, heard)
    assert result.word_accuracy == 1.0, ops(result)


@pytest.mark.parametrize(
    ("target", "heard"),
    [
        ("seven samples", "7 samples"),
        ("zero errors", "0 errors"),
        ("nineteen models", "19 models"),
        ("twenty-one people", "21 people"),
        ("twenty one people", "21 people"),
        ("ninety-nine people", "99 people"),
        ("forty people", "40 people"),
        ("a hundred people", "100 people"),
        ("one hundred people", "100 people"),
        ("1,000 people", "1000 people"),
        ("50% of them", "fifty percent of them"),
        ("50% of them", "50 per cent of them"),
        ("50 % of them", "fifty per cent of them"),
        ("ten percent", "10%"),
    ],
)
def test_numbers_and_percent(target: str, heard: str) -> None:
    result = compare(target, heard)
    assert result.word_accuracy == 1.0, ops(result)


@pytest.mark.parametrize(
    ("target", "heard"),
    [
        ("a well-known result", "a well known result"),
        ("send an e-mail", "send an email"),
        ("a well known result", "a well-known result"),
    ],
)
def test_hyphens(target: str, heard: str) -> None:
    result = compare(target, heard)
    assert result.word_accuracy == 1.0, ops(result)


def test_a_merge_keeps_both_ranges() -> None:
    [step] = compare("It's", "it is").steps
    assert (step.op, step.target_start, step.target_end, step.heard_start, step.heard_end) == (
        Op.MATCH,
        0,
        1,
        0,
        2,
    )
    assert (step.target, step.heard) == ("It's", "it is")


def test_numbers_above_a_hundred_in_words_are_different() -> None:
    result = compare("two hundred people", "200 people")
    assert result.word_accuracy < 1.0


def test_equivalent_compares_runs_of_keys() -> None:
    assert equivalent(["it's"], ["it", "is"])
    assert equivalent(["per", "cent"], ["%"])
    assert not equivalent(["it's"], ["it", "was"])


# --- Close ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "heard"),
    [
        ("colour", "color"),
        ("realise", "realize"),
        ("centre", "center"),
        ("travelled", "traveled"),
        ("defence", "defense"),
        ("catalogue", "catalog"),
        ("catalogues", "catalogs"),
        ("programme", "program"),
        ("grey", "gray"),
        ("specifications", "specificatons"),  # one slip on a long word
        ("regional", "regoinal"),  # a transposition is one edit
    ],
)
def test_close_spellings(target: str, heard: str) -> None:
    assert is_close(target, heard)
    [step] = compare(target, heard).steps
    assert step.op is Op.CLOSE
    assert compare(target, heard).word_accuracy == 1.0


@pytest.mark.parametrize(
    ("target", "heard"),
    [
        ("effects", "effect"),  # final -s removed
        ("effect", "effects"),  # final -s added
        ("used", "use"),  # final -d removed
        ("fixed", "fix"),  # two edits
        ("model", "nodel"),  # first letter
        ("cats", "cat"),  # short word
        ("five", "fife"),  # four letters
        ("cat", "car"),
        ("model", "model"),  # identical: a match, not close
        ("2020", "2021"),  # not alphabetic
    ],
)
def test_not_close(target: str, heard: str) -> None:
    assert not is_close(target, heard)


def test_known_limits_stay_close() -> None:
    # These / those and quite / quiet are one edit apart: recognised as close (D-173).
    assert is_close("these", "those") and is_close("quite", "quiet")


def test_close_counts_as_recognised_but_substitution_does_not() -> None:
    result = compare("The colour effects", "the color effect")
    assert ops(result) == [
        ("match", "The", "the"),
        ("close", "colour", "color"),
        ("substituted", "effects", "effect"),
    ]
    assert result.recognized_count == 2
    assert [u.word for u in result.unrecognized] == ["effects"]


# --- Alignment properties ---------------------------------------------------------------------


def test_substitution_is_cheaper_than_a_missing_and_an_extra_word() -> None:
    assert ops(compare("a b c", "a x c"))[1] == ("substituted", "b", "x")


def test_ties_are_broken_the_same_way_every_time() -> None:
    first = compare("the the the model", "the model the")
    for _ in range(5):
        assert compare("the the the model", "the model the") == first


VOCAB_TEXT = (
    "we account for regional fixed effects in all specifications it's it is the of a to and "
    "50% fifty per cent percent well-known well known don't do not twenty-one 21 colour color "
    "effect students' student's model models"
)
VOCAB = VOCAB_TEXT.split()


def _sentence(rng: random.Random, length: int) -> str:
    return " ".join(rng.choice(VOCAB) for _ in range(length))


@pytest.mark.parametrize("seed", range(5))
def test_every_word_appears_exactly_once_in_order(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(100):
        target = _sentence(rng, rng.randint(0, 12))
        heard = _sentence(rng, rng.randint(0, 12))
        result = compare(target, heard)
        target_cursor = heard_cursor = 0
        for step in result.steps:
            assert step.target_start == target_cursor and step.heard_start == heard_cursor
            assert step.target_end >= step.target_start and step.heard_end >= step.heard_start
            assert (step.target_end, step.heard_end) != (step.target_start, step.heard_start)
            if step.op is Op.MISSING:
                assert step.heard_end == step.heard_start and step.target_end > step.target_start
            if step.op is Op.EXTRA:
                assert step.target_end == step.target_start and step.heard_end > step.heard_start
            if step.op in (Op.CLOSE, Op.SUBSTITUTED):
                assert step.target_end - step.target_start == 1
                assert step.heard_end - step.heard_start == 1
            target_cursor, heard_cursor = step.target_end, step.heard_end
        assert target_cursor == result.target_word_count == len(words(target))
        assert heard_cursor == result.heard_word_count == len(words(heard))
        unrecognized = sum(
            step.target_end - step.target_start
            for step in result.steps
            if step.op in (Op.SUBSTITUTED, Op.MISSING)
        )
        assert result.recognized_count + unrecognized == result.target_word_count
        assert len(result.unrecognized) == unrecognized
        assert compare(target, heard) == result  # deterministic


def test_a_sentence_against_itself_is_always_perfect() -> None:
    rng = random.Random(7)
    for _ in range(50):
        sentence = _sentence(rng, rng.randint(1, 15))
        assert compare(sentence, sentence).word_accuracy == 1.0
