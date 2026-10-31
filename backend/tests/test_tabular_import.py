"""CSV / TSV import parser (app/domain/tabular_import.py): table-driven, pure."""

import pytest

from app.domain.markdown_import import (
    MAX_BODY_LINES,
    MAX_BYTES,
    ParsedImport,
    ProblemCode,
    Severity,
)
from app.domain.tabular_import import detect_delimiter, parse_table

C = ProblemCode


def terms(result: ParsedImport) -> list[tuple[str, str | None]]:
    return [(row.term, row.sentence) for row in result.rows]


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_each_delimiter_is_detected(delimiter: str) -> None:
    text = f"margin of error{delimiter}The margin of error is 3%.\nbias{delimiter}A bias.\n"
    assert detect_delimiter(text) == delimiter
    assert terms(parse_table(text)) == [
        ("margin of error", "The margin of error is 3%."),
        ("bias", "A bias."),
    ]


def test_commas_in_sentences_do_not_beat_the_semicolon() -> None:
    text = "bias;It is, as a rule, small.\nvariance;Large, then small, then large.\n"
    assert terms(parse_table(text)) == [
        ("bias", "It is, as a rule, small."),
        ("variance", "Large, then small, then large."),
    ]


def test_single_column_file_is_a_list_of_terms() -> None:
    result = parse_table("bias\nvariance\n")
    assert terms(result) == [("bias", None), ("variance", None)]


def test_quoted_fields_keep_their_delimiters_and_line_breaks() -> None:
    text = 'bias,"It is small, really."\n"odds ratio","two\nlines"\nnext,sentence\n'
    result = parse_table(text)
    assert terms(result) == [
        ("bias", "It is small, really."),
        ("odds ratio", "two\nlines"),
        ("next", "sentence"),
    ]
    assert [row.line for row in result.rows] == [1, 2, 4]


def test_bom_and_windows_line_breaks() -> None:
    result = parse_table("﻿bias;A bias.\r\nvariance;A variance.\r\n")
    assert terms(result) == [("bias", "A bias."), ("variance", "A variance.")]


@pytest.mark.parametrize("header", ["term,sentence", "Terme;Phrase", "WORD,Example", "term"])
def test_header_row_is_skipped(header: str) -> None:
    result = parse_table(f"{header}\nbias,A bias.\n" if "," in header else f"{header}\nbias\n")
    assert [row.term for row in result.rows] == ["bias"]
    assert result.rows[0].line == 2
    assert [(p.code, p.severity, p.line) for p in result.problems] == [
        (C.HEADER_ROW_SKIPPED, Severity.INFO, 1)
    ]


def test_a_term_that_looks_like_a_header_word_is_kept_when_column_two_is_a_sentence() -> None:
    result = parse_table("term,The term is defined here.\n")
    assert terms(result) == [("term", "The term is defined here.")]


def test_blank_rows_and_extra_columns() -> None:
    result = parse_table("\nbias;A bias.;noun;B2\n;;\n   \nvariance\n")
    assert terms(result) == [("bias", "A bias."), ("variance", None)]
    assert [row.line for row in result.rows] == [2, 5]


def test_empty_term_is_ambiguous() -> None:
    result = parse_table("bias;A bias.\n;A sentence without a term.\n")
    row = result.rows[1]
    assert row.ambiguous and not row.include
    assert [p.code for p in row.problems] == [C.EMPTY_TERM]
    assert row.line == 2


def test_term_not_in_sentence_is_a_warning() -> None:
    row = parse_table("bias;Nothing to see.\n").rows[0]
    assert row.include and not row.ambiguous
    assert [(p.code, p.severity) for p in row.problems] == [
        (C.TERM_NOT_IN_SENTENCE, Severity.WARNING)
    ]


def test_long_term_without_sentence_looks_like_a_sentence() -> None:
    row = parse_table("this is a very long line that is clearly a whole sentence of text\n").rows[0]
    assert row.ambiguous
    assert [p.code for p in row.problems] == [C.LOOKS_LIKE_SENTENCE]


def test_duplicates_in_file_keep_one_row() -> None:
    result = parse_table("bias\nBias;A bias.\n")
    assert [row.include for row in result.rows] == [False, True]
    assert result.rows[0].problems[-1].code == C.DUPLICATE_IN_FILE


def test_tsv_is_split_on_tabs_only() -> None:
    result = parse_table("bias\tIt is small, really; truly.\n", "tsv")
    assert terms(result) == [("bias", "It is small, really; truly.")]


def test_too_many_lines_is_rejected() -> None:
    text = "\n".join(f"word{i}" for i in range(MAX_BODY_LINES + 2))
    result = parse_table(text)
    assert result.rejected and result.rows == []
    assert result.problems[0].code == C.TOO_LARGE


def test_exactly_the_limit_plus_a_header_is_accepted() -> None:
    text = "term\n" + "\n".join(f"word{i}" for i in range(MAX_BODY_LINES))
    assert len(parse_table(text).rows) == MAX_BODY_LINES


def test_too_large_file_is_rejected() -> None:
    result = parse_table("a;" + "x" * MAX_BYTES)
    assert result.rejected
    assert result.problems[0].code == C.TOO_LARGE


def test_field_over_the_csv_limit_is_reported_not_raised() -> None:
    result = parse_table('a,"' + "x" * 200_000 + '"\n')
    assert result.rejected or result.rows  # never raises
    if result.rejected:
        assert result.problems[0].code in {C.INVALID_TABLE, C.TOO_LARGE}


@pytest.mark.parametrize("text", ["", "\n\n", "﻿"])
def test_empty_input_gives_no_rows(text: str) -> None:
    result = parse_table(text)
    assert result.rows == [] and not result.rejected
