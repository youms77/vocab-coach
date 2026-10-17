"""Markdown import parser (app/domain/markdown_import.py): table-driven, pure."""

from datetime import date

import pytest

from app.domain.enums import ItemType
from app.domain.markdown_import import (
    MAX_BODY_LINES,
    MAX_BYTES,
    ImportHeader,
    ParsedImport,
    ParsedRow,
    ProblemCode,
    Severity,
    check_term,
    clean_term,
    decode_import_bytes,
    guess_item_type,
    parse_import,
)

TODAY = date(2026, 10, 16)
C = ProblemCode


def parse(text: str) -> ParsedImport:
    return parse_import(text, TODAY)


def only_row(text: str) -> ParsedRow:
    result = parse(text)
    assert len(result.rows) == 1, result.rows
    return result.rows[0]


def codes(row: ParsedRow) -> list[ProblemCode]:
    return [problem.code for problem in row.problems]


# --- Body lines ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "term", "sentence"),
    [
        ("- heteroskedasticity", "heteroskedasticity", None),
        ("* heteroskedasticity", "heteroskedasticity", None),
        ("+ heteroskedasticity", "heteroskedasticity", None),
        ("1. heteroskedasticity", "heteroskedasticity", None),
        ("12) heteroskedasticity", "heteroskedasticity", None),
        ("- [ ] heteroskedasticity", "heteroskedasticity", None),
        ("- [x] heteroskedasticity", "heteroskedasticity", None),
        ("- [X] heteroskedasticity", "heteroskedasticity", None),
        ("heteroskedasticity", "heteroskedasticity", None),
        ("- **heteroskedasticity**", "heteroskedasticity", None),
        ("- __heteroskedasticity__", "heteroskedasticity", None),
        ("- *heteroskedasticity*", "heteroskedasticity", None),
        ("- _heteroskedasticity_", "heteroskedasticity", None),
        ("- `heteroskedasticity`", "heteroskedasticity", None),
        ("- ***shed light on***", "shed light on", None),
        (
            "- to account for | We account for regional fixed effects.",
            "to account for",
            "We account for regional fixed effects.",
        ),
        ("- **shed light on** | It sheds light on it.", "shed light on", "It sheds light on it."),
        ("- shed light on |   ", "shed light on", None),
        ("*important*", "important", None),  # emphasis, not a bullet
    ],
)
def test_bullet_styles_and_wrappers(line: str, term: str, sentence: str | None) -> None:
    row = only_row(line)
    assert (row.term, row.sentence) == (term, sentence)
    assert row.include and not row.ambiguous
    assert row.problems == []


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("- bias = biais", C.LOOKS_LIKE_DEFINITION),
        ("- bias : biais", C.LOOKS_LIKE_DEFINITION),
        ("- bias: a systematic error", C.LOOKS_LIKE_DEFINITION),
        ("- bias -> biais", C.LOOKS_LIKE_DEFINITION),
        ("- bias – biais", C.LOOKS_LIKE_DEFINITION),
        ("- bias - biais", C.LOOKS_LIKE_DEFINITION),
        ("- a | b | c", C.MULTIPLE_SEPARATORS),
        ("- one two three four five six seven eight nine", C.LOOKS_LIKE_SENTENCE),
        ("- " + "x" * 81, C.LOOKS_LIKE_SENTENCE),
        ("- ", C.EMPTY_TERM),
        ("- [ ]", C.EMPTY_TERM),
        ("- ** ** | a sentence", C.EMPTY_TERM),
        ("- " + "x" * 301 + " | a sentence", C.TERM_TOO_LONG),
    ],
)
def test_ambiguous_lines_are_reported_not_included(line: str, code: ProblemCode) -> None:
    row = only_row(line)
    assert codes(row) == [code]
    assert row.problems[0].severity == Severity.AMBIGUOUS
    assert row.ambiguous and not row.include
    assert row.problems[0].line == 1


def test_definition_suggests_a_split() -> None:
    row = only_row("- **bias** = biais")
    assert row.problems[0].suggestion == {"term": "bias", "note": "biais"}


def test_hyphenated_and_long_with_sentence_are_fine() -> None:
    assert only_row("- state-of-the-art").problems == []
    row = only_row(
        "- it is worth noting that the results hold | It is worth noting that the results hold."
    )
    assert row.problems == [] and row.item_type == ItemType.PHRASE


def test_nested_item() -> None:
    result = parse("- shed light on\n  - a note on it\n    plain continuation\n- account for")
    rows = {row.line: row for row in result.rows}
    assert codes(rows[1]) == []
    assert codes(rows[2]) == [C.NESTED_ITEM] and not rows[2].include
    assert codes(rows[3]) == []  # not a bullet: a plain line
    assert codes(rows[4]) == []


def test_uniformly_indented_list_is_not_nested() -> None:
    result = parse("  - shed light on\n  - account for")
    assert all(row.include for row in result.rows)


def test_headings_rules_and_blank_lines() -> None:
    result = parse("# Week 1\n\n- shed light on\n\n## More\n***\n- account for\n   \n")
    assert [row.term for row in result.rows] == ["shed light on", "account for"]
    assert [(p.line, p.code, p.severity) for p in result.problems] == [
        (1, C.HEADING_IGNORED, Severity.INFO),
        (5, C.HEADING_IGNORED, Severity.INFO),
        (6, C.HORIZONTAL_RULE, Severity.INFO),
    ]


def test_hashtag_without_space_is_a_term() -> None:
    assert only_row("#hashtag").term == "#hashtag"


def test_term_not_in_sentence_is_a_warning() -> None:
    row = only_row("- heteroskedasticity | The variance is constant.")
    assert codes(row) == [C.TERM_NOT_IN_SENTENCE]
    assert row.problems[0].severity == Severity.WARNING
    assert row.include


def test_duplicate_in_file_keeps_the_one_with_a_sentence() -> None:
    result = parse("- Shed light on\n- account for\n- shed light on | It sheds light on it.\n")
    rows = {row.line: row for row in result.rows}
    assert rows[3].include and codes(rows[3]) == []
    assert not rows[1].include and codes(rows[1]) == [C.DUPLICATE_IN_FILE]
    assert rows[1].problems[0].suggestion == {"kept_line": 3}
    assert rows[1].problems[0].severity == Severity.WARNING


def test_duplicate_in_file_without_sentence_keeps_the_first() -> None:
    result = parse("- account for\n- to account for\n")
    assert [row.include for row in result.rows] == [True, False]


def test_duplicate_prefers_a_clear_line() -> None:
    result = parse("- bias = biais\n- bias\n")
    # Different normalised forms: the definition line is not a duplicate of "bias".
    assert [row.include for row in result.rows] == [False, True]
    result = parse("  - x\n- bias\n- bias\n")
    assert [row.include for row in result.rows] == [True, True, False]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("bias", ItemType.WORD),
        ("shed light on", ItemType.COLLOCATION),
        ("to account for", ItemType.COLLOCATION),
        ("take into account the fact", ItemType.PHRASE),
        ("to take into account sth", ItemType.COLLOCATION),
        ("it is worth noting that", ItemType.PHRASE),
        ("", ItemType.WORD),
    ],
)
def test_guess_item_type(term: str, expected: ItemType) -> None:
    assert guess_item_type(term) == expected


def test_spoken_formula_is_never_guessed() -> None:
    assert all(
        guess_item_type(term) != ItemType.SPOKEN_FORMULA
        for term in ("could you repeat that", "let me put it this way", "hi")
    )


# --- Header ----------------------------------------------------------------------------------

FULL_HEADER = """---
deck: Causal inference reading
domain: econometrics
source: "Angrist & Pischke, ch. 3"
context: "Reading for my report"
deadline: 2026-11-20
---
- heteroskedasticity
"""


def test_full_header() -> None:
    result = parse(FULL_HEADER)
    assert result.header == ImportHeader(
        deck="Causal inference reading",
        domain="econometrics",
        source="Angrist & Pischke, ch. 3",
        context="Reading for my report",
        deadline=date(2026, 11, 20),
    )
    assert result.problems == []
    assert result.rows[0].line == 8


def test_no_header() -> None:
    result = parse("- heteroskedasticity\n")
    assert result.header == ImportHeader()
    assert result.problems == []


def test_header_after_blank_lines_and_quoted_deadline() -> None:
    result = parse("\n\n---\ndeadline: '2026-11-20'\n---\n- x\n")
    assert result.header.deadline == date(2026, 11, 20)
    assert result.rows[0].line == 6


def test_dashes_later_in_the_file_are_not_a_header() -> None:
    result = parse("- a\n---\ndeck: x\n---\n- b\n")
    assert result.header == ImportHeader()
    assert [p.code for p in result.problems] == [C.HORIZONTAL_RULE, C.HORIZONTAL_RULE]
    assert [row.term for row in result.rows] == ["a", "deck: x", "b"]


def test_unclosed_header() -> None:
    result = parse("---\ndeck: x\n- a\n")
    assert [(p.line, p.code) for p in result.problems] == [(1, C.UNCLOSED_HEADER)]
    assert [row.line for row in result.rows] == [2, 3]


def test_invalid_yaml_still_reads_the_body() -> None:
    result = parse("---\ndeck: [unclosed\n---\n- heteroskedasticity\n")
    assert result.header == ImportHeader()
    assert [(p.line, p.code, p.severity) for p in result.problems] == [
        (1, C.INVALID_HEADER, Severity.WARNING)
    ]
    assert result.rows[0].term == "heteroskedasticity" and result.rows[0].line == 4


def test_header_that_is_not_a_mapping() -> None:
    result = parse("---\njust text\n---\n- x\n")
    assert [p.code for p in result.problems] == [C.INVALID_HEADER]


def test_header_with_python_tags_is_refused_safely() -> None:
    result = parse("---\ndeck: !!python/object/apply:os.system ['echo hi']\n---\n- x\n")
    assert [p.code for p in result.problems] == [C.INVALID_HEADER]


def test_unknown_key_and_bad_values() -> None:
    result = parse("---\ndeck: x\ncolour: blue\ndomain: [a, b]\n---\n- y\n")
    assert result.header == ImportHeader(deck="x")
    assert [(p.line, p.code, p.severity) for p in result.problems] == [
        (3, C.UNKNOWN_HEADER_KEY, Severity.WARNING),
        (4, C.INVALID_HEADER_VALUE, Severity.WARNING),
    ]


@pytest.mark.parametrize(
    "value", ["2026-13-01", "next friday", "20261120", "2026-11-20 10:00", "2026-11-20T10:00:00"]
)
def test_invalid_deadline(value: str) -> None:
    result = parse(f"---\ndeadline: {value}\n---\n- x\n")
    assert result.header.deadline is None
    assert [(p.line, p.code) for p in result.problems] == [(2, C.INVALID_DEADLINE)]


def test_past_deadline_is_kept_with_a_warning() -> None:
    result = parse("---\ndeadline: 2026-10-15\n---\n- x\n")
    assert result.header.deadline == date(2026, 10, 15)
    assert [(p.code, p.severity) for p in result.problems] == [(C.PAST_DEADLINE, Severity.WARNING)]
    assert parse("---\ndeadline: 2026-10-16\n---\n").problems == []  # today is fine


def test_empty_values_and_numbers() -> None:
    result = parse("---\ndeck:\ndomain: 2026\ndeadline:\n---\n")
    assert result.header == ImportHeader(domain="2026")
    assert result.problems == []


# --- Files -----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "\n\n  \n", "\ufeff"])
def test_empty_file(text: str) -> None:
    result = parse(text)
    assert result.rows == [] and result.problems == [] and not result.rejected


def test_header_only() -> None:
    result = parse("---\ndeck: x\n---\n")
    assert result.header.deck == "x" and result.rows == [] and result.problems == []


def test_bom_and_crlf_keep_line_numbers() -> None:
    text = "\ufeff---\r\ndeck: x\r\n---\r\n\r\n- a | A sentence with a.\r\n- b\r\n"
    result = parse(text)
    assert result.header.deck == "x"
    assert [(row.line, row.term, row.sentence) for row in result.rows] == [
        (5, "a", "A sentence with a."),
        (6, "b", None),
    ]
    assert all(not row.raw.endswith("\r") for row in result.rows)


def test_old_mac_line_endings() -> None:
    assert [row.line for row in parse("- a\r- b\r").rows] == [1, 2]


def test_typographic_characters_from_word() -> None:
    row = only_row("• x\n" if False else "- “make up one’s mind” | She made up her mind…")
    assert row.normalized_form == "make up one's mind"


def test_too_many_lines() -> None:
    result = parse("\n".join(f"- term{i}" for i in range(MAX_BODY_LINES + 1)))
    assert result.rows == [] and result.rejected
    assert [p.code for p in result.problems] == [C.TOO_LARGE]
    assert len(parse("\n".join(f"- term{i}" for i in range(MAX_BODY_LINES))).rows) == MAX_BODY_LINES


def test_too_many_bytes() -> None:
    result = parse("- " + "a" * MAX_BYTES)
    assert result.rows == [] and [p.code for p in result.problems] == [C.TOO_LARGE]


def test_decode_import_bytes() -> None:
    assert decode_import_bytes("\ufeff- café".encode()) == "- café"
    assert decode_import_bytes("- café".encode("cp1252")) is None


def test_today_must_be_a_date() -> None:
    from datetime import datetime

    with pytest.raises(TypeError):
        parse_import("- x", datetime(2026, 10, 16))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "text",
    [
        "\x00\x01\x02",
        "---\n---\n---\n",
        "|||",
        "- [",
        "1.",
        "---\n: :\n---",
        "---\n- a\n- b\n---\n",
        "\t\t- x",
        " - x",
    ],
)
def test_never_raises_on_odd_input(text: str) -> None:
    parse(text)


# --- Shared helpers --------------------------------------------------------------------------


def test_clean_term() -> None:
    assert clean_term("  **`shed light on`**  ") == "shed light on"
    assert clean_term("**") == "**"
    assert clean_term("a_b") == "a_b"


def test_check_term_for_commit() -> None:
    assert check_term("shed light on", None, 3) == []
    assert [p.code for p in check_term("bias = biais", None, 3)] == [C.LOOKS_LIKE_DEFINITION]
    assert [p.code for p in check_term("a|b", "s", None)] == [C.MULTIPLE_SEPARATORS]
    assert [p.code for p in check_term("", None, None)] == [C.EMPTY_TERM]
