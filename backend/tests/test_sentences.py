"""Sentence splitting and fragment search (app/domain/sentences.py), on hand-built cases."""

import pytest

from app.domain.sentences import MAX_SENTENCES, TextTooLong, find_fragment, split_sentences


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # The acceptance paragraph of M5.a1.
        (
            "Last year I moved to Yaoundé to start my master's degree. Since then, I lived in "
            "campus with two friends from my class.",
            [
                "Last year I moved to Yaoundé to start my master's degree.",
                "Since then, I lived in campus with two friends from my class.",
            ],
        ),
        ("One sentence without a final point", ["One sentence without a final point"]),
        ("Is it true? Yes! Really?! Sure.", ["Is it true?", "Yes!", "Really?!", "Sure."]),
        # Line breaks always end a sentence, blank lines are ignored.
        ("First line\nsecond line\n\n  Third.  ", ["First line", "second line", "Third."]),
        ("Windows line.\r\nNext line.", ["Windows line.", "Next line."]),
        # Abbreviations that never end a sentence.
        (
            "Some tests, e.g. the t-test, are robust. Others are not.",
            ["Some tests, e.g. the t-test, are robust.", "Others are not."],
        ),
        ("I mean, i.e. the mean. Fine.", ["I mean, i.e. the mean.", "Fine."]),
        ("Dr. Smith met Mr. Jones. They talked.", ["Dr. Smith met Mr. Jones.", "They talked."]),
        ("See p. 12 and pp. 30-31. Then stop.", ["See p. 12 and pp. 30-31.", "Then stop."]),
        (
            "Card et al. found an effect. We agree.",
            ["Card et al. found an effect.", "We agree."],
        ),
        ("OLS vs. IV estimates differ. Why?", ["OLS vs. IV estimates differ.", "Why?"]),
        ("J. Smith wrote it. I read it.", ["J. Smith wrote it.", "I read it."]),
        # "etc." and acronyms end a sentence only before a capital letter.
        (
            "We need data, code, etc. and time. Then we start.",
            ["We need data, code, etc. and time.", "Then we start."],
        ),
        ("We need data, code, etc. Then we start.", ["We need data, code, etc.", "Then we start."]),
        ("The U.S. economy grew. It slowed later.", ["The U.S. economy grew.", "It slowed later."]),
        # Numbers.
        (
            "The mean is 3.5 and the median 2.75. It is skewed.",
            ["The mean is 3.5 and the median 2.75.", "It is skewed."],
        ),
        ("I was 25. Then I moved.", ["I was 25.", "Then I moved."]),
        # A learner may forget the capital letter after a full stop.
        ("I moved. then I studied.", ["I moved.", "then I studied."]),
        # Ellipsis.
        ("I was... tired. Then I slept.", ["I was... tired.", "Then I slept."]),
        ("I waited... Nothing happened.", ["I waited...", "Nothing happened."]),
        ("I waited… Nothing happened… at all.", ["I waited…", "Nothing happened… at all."]),
        # Quotes and brackets.
        (
            'He said "Stop." Then he left.',
            ['He said "Stop."', "Then he left."],
        ),
        ("She asked “Why?” I did not know.", ["She asked “Why?”", "I did not know."]),
        ("It works (mostly.) We use it.", ["It works (mostly.)", "We use it."]),
        ('"Really?" she said.', ['"Really?" she said.']),
        ("It ended. “Then what?” he asked.", ["It ended.", "“Then what?” he asked."]),
        # Punctuation without a space after it is not a boundary.
        ("Visit example.com today.", ["Visit example.com today."]),
        ("", []),
        ("   \n  \n", []),
    ],
)
def test_split_sentences(text: str, expected: list[str]) -> None:
    assert [s.text for s in split_sentences(text)] == expected


def test_sentences_are_numbered_from_one_with_their_offsets() -> None:
    text = "  First one.  Second one!\nThird"
    sentences = split_sentences(text)
    assert [s.index for s in sentences] == [1, 2, 3]
    for sentence in sentences:
        assert text[sentence.start : sentence.end] == sentence.text


def test_offsets_count_code_points_after_non_ascii_text() -> None:
    text = "Je suis à Yaoundé. I lived in campus."
    second = split_sentences(text)[1]
    assert (second.start, text[second.start : second.end]) == (19, "I lived in campus.")


def test_more_than_the_maximum_is_refused() -> None:
    assert len(split_sentences("Yes. " * MAX_SENTENCES)) == MAX_SENTENCES
    with pytest.raises(TextTooLong):
        split_sentences("Yes. " * (MAX_SENTENCES + 1))


@pytest.mark.parametrize(
    ("sentence", "fragment", "found"),
    [
        ("I lived in campus.", "in campus", "in campus"),
        ("I lived  in   campus.", "in campus", "in   campus"),  # spaces
        ("It’s my master’s degree.", "master's degree", "master’s degree"),  # apostrophes
        ("I moved to Yaoundé last year.", "Yaoundé", "Yaoundé"),  # composition
        ("Since then, I lived here.", "since then", "Since then"),  # case, as a fallback
        ("I lived in campus.", "on campus", None),
        ("I lived in campus.", "   ", None),
    ],
)
def test_find_fragment(sentence: str, fragment: str, found: str | None) -> None:
    position = find_fragment(sentence, fragment)
    if found is None:
        assert position is None
    else:
        assert position is not None
        assert sentence[position[0] : position[1]] == found


def test_find_fragment_prefers_the_exact_case() -> None:
    sentence = "Then, then it stopped."
    assert find_fragment(sentence, "then") == (6, 10)
