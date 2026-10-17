"""Transcript parser (app/domain/transcript_import.py): table-driven, pure."""

import pytest

from app.domain.transcript_import import (
    CONTEXT_MAX_CHARS,
    MAX_PASTED_CHARS,
    MAX_USER_CHARS,
    UNIT_MAX_CHARS,
    ProblemCode,
    Severity,
    TranscriptParse,
    UserByLabel,
    UserByMode,
    chunk_units,
    cut_context,
    parse_transcript,
    split_units,
    user_turns_of,
)

C = ProblemCode


def codes(parsed: TranscriptParse) -> list[ProblemCode]:
    return [problem.code for problem in parsed.problems]


def texts(parsed: TranscriptParse) -> list[str]:
    return [turn.text for turn in parsed.turns]


# --- Labels --------------------------------------------------------------------------------------


def test_known_labels_and_suggested_user() -> None:
    parsed = parse_transcript("ChatGPT: Hi! How are you?\nYou: I am fine.\nChatGPT: Good.\n")
    assert parsed.labelled
    assert [(t.speaker_label, t.text, t.is_user) for t in parsed.turns] == [
        ("ChatGPT", "Hi! How are you?", False),
        ("You", "I am fine.", True),
        ("ChatGPT", "Good.", False),
    ]
    assert parsed.suggested_user_label == "You"
    assert parsed.designation == UserByLabel(label="You")
    assert [(lc.label, lc.turns, lc.known) for lc in parsed.labels] == [
        ("ChatGPT", 2, "other"),
        ("You", 1, "user"),
    ]
    assert parsed.labels[1].words == 3
    assert parsed.labels[1].chars == len("I am fine.")
    assert codes(parsed) == []
    assert parsed.user_text == "I am fine."


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("you", "user"),
        ("USER", "user"),
        ("Me", "user"),
        ("moi", "user"),
        ("Vous", "user"),
        ("chatgpt", "other"),
        ("Assistant", "other"),
        ("AI", "other"),
        ("gpt", "other"),
        ("Tutor", "other"),
        ("Jordan", None),
    ],
)
def test_label_kinds_ignore_case(label: str, kind: str | None) -> None:
    parsed = parse_transcript(f"{label}: hello there\nOther Person: hi\n")
    assert parsed.labels[0].known == kind


def test_unknown_labels_give_no_suggestion_and_need_a_choice() -> None:
    text = "Jordan: I live in Yaoundé.\nAmina: Nice.\nJordan: Yes.\n"
    parsed = parse_transcript(text)
    assert parsed.suggested_user_label is None
    assert all(turn.is_user is None for turn in parsed.turns)
    assert parsed.designation is None
    chosen = parse_transcript(text, UserByLabel(label="jordan"))
    assert [t.text for t in chosen.user_turns] == ["I live in Yaoundé.", "Yes."]
    assert chosen.user_text == "I live in Yaoundé.\n\nYes."


def test_two_user_labels_give_no_suggestion() -> None:
    parsed = parse_transcript("You: a\nMe: b\nChatGPT: c\n")
    assert parsed.suggested_user_label is None


@pytest.mark.parametrize(
    ("line", "is_label"),
    [
        ("You: hi", True),
        ("Jordan Youmbi: hi", True),
        ("Dr. Amina Bello: hi", True),
        ("You:", True),
        ("one two three four: no", False),  # more than 3 words
        ("A" * 31 + ": no", False),  # more than 30 characters
        ("See https://example.com for it", False),
        ("https://example.com", False),
        ("10 things: no", False),  # starts with a digit
        ("Ratio:3", False),  # no space after the colon
    ],
)
def test_what_opens_a_turn(line: str, is_label: bool) -> None:
    parsed = parse_transcript(f"{line}\n")
    assert parsed.labelled is is_label


def test_lines_after_a_label_belong_to_its_turn_and_blank_lines_are_dropped() -> None:
    text = "You:\nFirst line.\n\nSecond line.\nChatGPT: ok\n"
    parsed = parse_transcript(text)
    assert texts(parsed) == ["First line.\nSecond line.", "ok"]
    assert "\n\n" not in parsed.user_text
    assert user_turns_of(parsed.user_text) == ["First line.\nSecond line."]


def test_text_before_the_first_label_is_an_unlabelled_turn() -> None:
    parsed = parse_transcript("Transcript of my call\n\nYou: hello\nChatGPT: hi\n")
    assert [(t.speaker_label, t.is_user) for t in parsed.turns] == [
        (None, False),
        ("You", True),
        ("ChatGPT", False),
    ]
    problem = parsed.problems[0]
    assert (problem.code, problem.severity, problem.line) == (
        C.UNLABELLED_TEXT,
        Severity.WARNING,
        1,
    )
    all_mine = parse_transcript(
        "Transcript\nYou: hello\nChatGPT: hi\n", UserByMode(mode="all_mine")
    )
    assert all(turn.is_user for turn in all_mine.turns)


# --- Timestamps ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "turn"),
    [
        ("[00:12] You: hello", "hello"),
        ("(12:03 PM) You: hello", "hello"),
        ("00:12:33 You: hello", "hello"),
        ("12:03 PM You: hello", "hello"),
        ("12:03 pm - You: hello", "hello"),
        ("00:12 You: hello", "hello"),  # a label follows
        ("You: [00:12] hello", "[00:12] hello"),  # not at the start of the line
    ],
)
def test_leading_timestamps_are_removed(line: str, turn: str) -> None:
    parsed = parse_transcript(f"{line}\nChatGPT: hi\n")
    assert parsed.turns[0].speaker_label == "You"
    assert parsed.turns[0].text == turn


def test_a_bare_time_inside_a_sentence_is_kept() -> None:
    parsed = parse_transcript("You:\n10:30 is fine for me.\nChatGPT: ok\n")
    assert parsed.turns[0].text == "10:30 is fine for me."


def test_a_timestamp_alone_on_its_line_is_dropped_without_splitting_paragraphs() -> None:
    parsed = parse_transcript("[00:01]\nHello there.\n[00:05]\nHow are you?\n\nFine.\n")
    assert texts(parsed) == ["Hello there.\nHow are you?", "Fine."]


# --- Without labels ------------------------------------------------------------------------------

UNLABELLED = "Hello, how are you?\n\nI am fine. I study here.\n\nGreat.\n\nThanks.\n"


def test_paragraphs_are_turns_without_labels() -> None:
    parsed = parse_transcript(UNLABELLED)
    assert not parsed.labelled
    assert texts(parsed) == ["Hello, how are you?", "I am fine. I study here.", "Great.", "Thanks."]
    assert [t.line_start for t in parsed.turns] == [1, 3, 5, 7]
    assert codes(parsed) == [C.NO_SPEAKER_LABELS]
    assert parsed.designation is None
    assert all(turn.is_user is None for turn in parsed.turns)


@pytest.mark.parametrize(
    ("mode", "mine"),
    [
        ("alternating_user_first", ["Hello, how are you?", "Great."]),
        ("alternating_user_second", ["I am fine. I study here.", "Thanks."]),
        ("all_mine", ["Hello, how are you?", "I am fine. I study here.", "Great.", "Thanks."]),
    ],
)
def test_the_three_modes(mode: str, mine: list[str]) -> None:
    parsed = parse_transcript(UNLABELLED, UserByMode(mode=mode))  # type: ignore[arg-type]
    assert [t.text for t in parsed.user_turns] == mine
    assert parsed.designation == UserByMode(mode=mode)  # type: ignore[arg-type]


def test_a_label_on_an_unlabelled_text_is_unknown() -> None:
    parsed = parse_transcript(UNLABELLED, UserByLabel(label="You"))
    assert C.UNKNOWN_LABEL in codes(parsed)
    assert C.NO_USER_TURNS in codes(parsed)
    assert parsed.has_errors


# --- Problems ------------------------------------------------------------------------------------


def test_single_speaker() -> None:
    assert C.SINGLE_SPEAKER in codes(parse_transcript("You: one\nYou: two\n"))
    assert C.SINGLE_SPEAKER in codes(parse_transcript("Just one paragraph.\n"))


def test_empty_turn_is_ignored_with_its_line() -> None:
    parsed = parse_transcript("You: hi\nChatGPT:\nYou: again\nChatGPT: ok\n")
    assert texts(parsed) == ["hi", "again", "ok"]
    empty = [p for p in parsed.problems if p.code is C.EMPTY_TURN]
    assert [(p.line, p.severity) for p in empty] == [(2, Severity.WARNING)]
    assert [t.index for t in parsed.turns] == [1, 2, 3]


def test_unknown_label_and_no_user_turns() -> None:
    parsed = parse_transcript("You: hi\nChatGPT: ok\n", UserByLabel(label="Jordan"))
    assert codes(parsed) == [C.UNKNOWN_LABEL, C.NO_USER_TURNS]
    assert parsed.user_text == ""


def test_empty_text() -> None:
    for text in ("", "   \n\n", "﻿", "[00:12]\n"):
        parsed = parse_transcript(text)
        assert codes(parsed) == [C.EMPTY_TEXT]
        assert parsed.turns == []


def test_too_large_pasted_text_gives_no_turn() -> None:
    parsed = parse_transcript("You: " + "a" * MAX_PASTED_CHARS)
    assert codes(parsed) == [C.TOO_LARGE]
    assert parsed.turns == []


def test_limits_on_the_users_speech() -> None:
    turn = "word " * 300  # 1 500 characters once stripped
    at_limit = "x" * MAX_USER_CHARS
    assert C.TOO_LARGE not in codes(parse_transcript(f"You: {at_limit}\nChatGPT: ok\n"))
    over = parse_transcript(f"You: {at_limit}x\nChatGPT: {turn}\n")
    assert codes(over) == [C.TOO_LARGE]
    assert over.user_chars == MAX_USER_CHARS + 1
    # The other speaker's text does not count.
    long_other = parse_transcript(f"You: hi\nChatGPT: {'y' * (MAX_USER_CHARS * 2)}\n")
    assert C.TOO_LARGE not in codes(long_other)


# --- Line endings, BOM, line numbers -------------------------------------------------------------


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_line_endings_and_bom(newline: str) -> None:
    lines = ["﻿ChatGPT: Hello.", "", "You: I study", "here since two years.", "ChatGPT: Ok."]
    parsed = parse_transcript(newline.join(lines))
    assert texts(parsed) == ["Hello.", "I study\nhere since two years.", "Ok."]
    assert [t.line_start for t in parsed.turns] == [1, 3, 5]
    assert parsed.turns[0].speaker_label == "ChatGPT"


def test_unicode_line_separators_do_not_shift_line_numbers() -> None:
    parsed = parse_transcript("You: a b\nChatGPT: c\n")
    assert [t.line_start for t in parsed.turns] == [1, 2]


def test_punctuation_and_hesitations_are_kept() -> None:
    parsed = parse_transcript("You: uh I go— I went, um, there\nChatGPT: ok\n")
    assert parsed.turns[0].text == "uh I go— I went, um, there"


# --- Context -------------------------------------------------------------------------------------


def test_contexts_are_the_other_turn_before_each_user_turn() -> None:
    long_question = "Tell me more. " * 40 + "Where do you study?"
    text = f"You: hi\nChatGPT: {long_question}\nYou: In campus.\nYou: Since two years.\n"
    parsed = parse_transcript(text)
    contexts = parsed.user_contexts()
    assert contexts[0] is None and contexts[2] is None
    assert contexts[1] is not None
    assert len(contexts[1]) <= CONTEXT_MAX_CHARS
    assert contexts[1].startswith("…") and contexts[1].endswith("Where do you study?")
    assert cut_context("short") == "short"


# --- Units and chunks ----------------------------------------------------------------------------


def test_each_turn_is_a_unit_with_offsets_in_the_stored_text() -> None:
    stored = "I live in Yaoundé.\n\nI study here since two years."
    units = split_units(stored)
    assert [(u.index, u.turn, u.opens_turn) for u in units] == [(1, 0, True), (2, 1, True)]
    for unit in units:
        assert stored[unit.start : unit.end] == unit.text


def test_a_long_turn_is_cut_on_sentence_ends_then_on_spaces() -> None:
    sentence = "This is a sentence about my statistics course. "
    long_turn = (sentence * 30).strip()  # about 1 400 characters
    no_stop = " ".join(["word"] * 300)  # 1 499 characters without any sentence end
    stored = f"Short one.\n\n{long_turn}\n\n{no_stop}"
    units = split_units(stored)
    assert all(len(u.text) <= UNIT_MAX_CHARS for u in units)
    assert all(stored[u.start : u.end] == u.text for u in units)
    second = [u for u in units if u.turn == 1]
    assert len(second) == 3
    assert all(u.text.endswith(".") for u in second)
    assert [u.opens_turn for u in second] == [True, False, False]
    third = [u for u in units if u.turn == 2]
    assert len(third) == 3
    assert [u.index for u in units] == list(range(1, len(units) + 1))


def test_a_word_longer_than_a_unit_is_cut() -> None:
    units = split_units("z" * (UNIT_MAX_CHARS * 2 + 5))
    assert [len(u.text) for u in units] == [UNIT_MAX_CHARS, UNIT_MAX_CHARS, 5]


def test_chunks_keep_units_whole_within_both_limits() -> None:
    stored = "\n\n".join(["a" * 500] * 7 + ["b"] * 30)
    units = split_units(stored)
    chunks = chunk_units(units, max_chars=2500, max_units=20)
    assert [u for chunk in chunks for u in chunk] == units
    for chunk in chunks:
        assert sum(len(u.text) for u in chunk) <= 2500
        assert len(chunk) <= 20
    assert [len(chunk) for chunk in chunks] == [5, 20, 12]
