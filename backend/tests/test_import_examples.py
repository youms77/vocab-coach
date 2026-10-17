"""The example files in content/examples/ give exactly the expected problems, at the right lines."""

from datetime import date
from pathlib import Path

import pytest

from app.domain.markdown_import import ImportHeader, ParsedImport, ProblemCode, parse_import

EXAMPLES = Path(__file__).resolve().parents[2] / "content" / "examples"
TODAY = date(2026, 10, 16)
C = ProblemCode


def parse(name: str, *, crlf: bool = False, bom: bool = False) -> ParsedImport:
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n")
    if crlf:
        text = text.replace("\n", "\r\n")
    if bom:
        text = "﻿" + text
    return parse_import(text, TODAY)


def problems(result: ParsedImport) -> list[tuple[int | None, ProblemCode]]:
    return [(problem.line, problem.code) for problem in result.all_problems()]


@pytest.mark.parametrize(("crlf", "bom"), [(False, False), (True, True)])
def test_example_with_header(crlf: bool, bom: bool) -> None:
    result = parse("import-with-header.md", crlf=crlf, bom=bom)
    assert result.header == ImportHeader(
        deck="Presenting survey results",
        domain="statistics",
        source="Lecture notes, Survey Methods, week 4",
        context="Preparing a short talk on a fictional student survey",
        deadline=date(2099, 6, 30),
    )
    assert problems(result) == [
        (8, C.HEADING_IGNORED),
        (16, C.LOOKS_LIKE_DEFINITION),
        (17, C.DUPLICATE_IN_FILE),
        (18, C.LOOKS_LIKE_SENTENCE),
        (19, C.TERM_NOT_IN_SENTENCE),
        (21, C.HEADING_IGNORED),
    ]
    included = [(row.line, row.term) for row in result.rows if row.include]
    assert included == [
        (10, "sampling frame"),
        (11, "response rate"),
        (12, "to account for"),
        (13, "margin of error"),
        (14, "weighting"),
        (15, "shed light on"),
        (19, "outlier"),
        (22, "as you can see on this slide"),
        (23, "it is worth noting that"),
    ]


@pytest.mark.parametrize(("crlf", "bom"), [(False, False), (True, True)])
def test_example_without_header(crlf: bool, bom: bool) -> None:
    result = parse("import-without-header.md", crlf=crlf, bom=bom)
    assert result.header == ImportHeader()
    assert problems(result) == [
        (1, C.HEADING_IGNORED),
        (4, C.DUPLICATE_IN_FILE),
        (9, C.LOOKS_LIKE_DEFINITION),
        (11, C.NESTED_ITEM),
        (12, C.LOOKS_LIKE_SENTENCE),
        (13, C.MULTIPLE_SEPARATORS),
    ]
    included = [row.line for row in result.rows if row.include]
    assert included == [3, 5, 6, 7, 8, 10]
