"""CSV / TSV word-list import (docs/SPEC.md module A). Pure Python: no database, no clock.

Column 1 is the term, optional column 2 the original English sentence; other columns are ignored.
The delimiter (comma, semicolon, tab) is detected, an optional header row is skipped, and the rows
come out as the same `ParsedRow` objects as the Markdown parser, so the preview and the commit are
shared. There is no YAML header: the deck is chosen in the import page. The parser never raises on
user input. Line numbers are physical lines of the file (a quoted field may span several), 1-based.
"""

import csv
import io
from collections import Counter
from typing import Literal

from app.domain.markdown_import import (
    MAX_BODY_LINES,
    MAX_BYTES,
    ImportHeader,
    ImportProblem,
    ParsedImport,
    ParsedRow,
    ProblemCode,
    Severity,
    check_term,
    make_row,
    mark_duplicates,
    too_large_problem,
)

ImportFormat = Literal["markdown", "csv", "tsv"]
TableFormat = Literal["csv", "tsv"]

_CANDIDATES = (",", ";", "\t")  # in order of preference when two fit equally well
_SAMPLE_RECORDS = 10
_TERM_HEADERS = frozenset({"term", "terme", "word", "mot", "vocabulary", "vocabulaire"})
_SENTENCE_HEADERS = frozenset(
    {"sentence", "phrase", "example", "exemple", "context", "contexte", "original sentence"}
)


def _problem(
    line: int | None, severity: Severity, code: ProblemCode, message: str
) -> ImportProblem:
    return ImportProblem(line=line, severity=severity, code=code, message=message)


def _records(text: str, delimiter: str, limit: int | None = None) -> list[tuple[int, list[str]]]:
    """(first physical line, fields) of each non-blank record. May raise `csv.Error`."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    records: list[tuple[int, list[str]]] = []
    previous_end = 0
    for fields in reader:
        start = previous_end + 1
        previous_end = reader.line_num
        if not fields or all(not field.strip() for field in fields):
            continue
        records.append((start, fields))
        if limit is not None and len(records) >= limit:
            break
    return records


def detect_delimiter(text: str) -> str:
    """The candidate giving the most first records that split into the same number (>= 2) of
    columns; on a tie the fewer columns, since a stray delimiter in a sentence only adds some."""
    best, best_score = ",", (0, 0)
    for delimiter in _CANDIDATES:
        try:
            sample = _records(text, delimiter, _SAMPLE_RECORDS)
        except csv.Error:
            continue
        widths = Counter(len(fields) for _, fields in sample if len(fields) >= 2)
        score = max(((count, -width) for width, count in widths.items()), default=(0, 0))
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _is_header_row(fields: list[str]) -> bool:
    if fields[0].strip().casefold() not in _TERM_HEADERS:
        return False
    return len(fields) == 1 or fields[1].strip().casefold() in _SENTENCE_HEADERS | {""}


def parse_table(text: str, fmt: TableFormat = "csv") -> ParsedImport:
    """Parse a CSV or TSV word list. Never raises on user input."""
    if len(text.encode("utf-8", errors="replace")) > MAX_BYTES:
        return _rejected(too_large_problem())
    text = text.removeprefix("﻿")
    if sum(1 for line in text.splitlines() if line.strip()) > MAX_BODY_LINES + 1:
        return _rejected(too_large_problem())  # +1: room for a header row

    delimiter = "\t" if fmt == "tsv" else detect_delimiter(text)
    try:
        records = _records(text, delimiter)
    except csv.Error as exc:
        return _rejected(
            _problem(
                None, Severity.ERROR, ProblemCode.INVALID_TABLE, f"The table cannot be read: {exc}."
            )
        )

    problems: list[ImportProblem] = []
    if records and _is_header_row(records[0][1]):
        line, _ = records.pop(0)
        problems.append(
            _problem(line, Severity.INFO, ProblemCode.HEADER_ROW_SKIPPED, "Header row skipped.")
        )
    if len(records) > MAX_BODY_LINES:
        return _rejected(too_large_problem())

    rows: list[ParsedRow] = []
    for line, fields in records:
        term = fields[0].strip()
        sentence = (fields[1].strip() or None) if len(fields) > 1 else None
        rows.append(
            make_row(line, delimiter.join(fields), term, sentence, check_term(term, sentence, line))
        )
    return ParsedImport(header=ImportHeader(), rows=mark_duplicates(rows), problems=problems)


def _rejected(problem: ImportProblem) -> ParsedImport:
    return ParsedImport(header=ImportHeader(), rows=[], problems=[problem])
