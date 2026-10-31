"""Markdown list import (docs/SPEC.md module A). Pure Python: no database, no clock.

One line = one term, optionally followed by `|` and the sentence it came from; an optional YAML
header (between `---` lines) describes the deck. The parser never raises on user input: anything
odd becomes a problem with a stable `code` (the interface turns codes into i18n keys). Ambiguous
lines are returned but not included: the user corrects or confirms them in the preview.

Line numbers are those of the original file, 1-based, header included.
"""

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.domain.enums import ItemType
from app.domain.normalize import normalize_term, term_in_sentence

MAX_BYTES = 256 * 1024
MAX_BODY_LINES = 1000
MAX_TERM_CHARS = 300  # lexical_item.term column
SENTENCE_MAX_WORDS = 8
SENTENCE_MAX_CHARS = 80
HEADER_KEYS = ("deck", "domain", "source", "context", "deadline")


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"  # imported anyway
    AMBIGUOUS = "ambiguous"  # not imported unless corrected or confirmed
    ERROR = "error"  # nothing imported


class ProblemCode(StrEnum):
    TOO_LARGE = "too_large"
    NOT_UTF8 = "not_utf8"
    INVALID_HEADER = "invalid_header"
    INVALID_HEADER_VALUE = "invalid_header_value"
    UNCLOSED_HEADER = "unclosed_header"
    UNKNOWN_HEADER_KEY = "unknown_header_key"
    INVALID_DEADLINE = "invalid_deadline"
    PAST_DEADLINE = "past_deadline"
    HEADING_IGNORED = "heading_ignored"
    HORIZONTAL_RULE = "horizontal_rule"
    MULTIPLE_SEPARATORS = "multiple_separators"
    LOOKS_LIKE_DEFINITION = "looks_like_definition"
    LOOKS_LIKE_SENTENCE = "looks_like_sentence"
    NESTED_ITEM = "nested_item"
    EMPTY_TERM = "empty_term"
    TERM_TOO_LONG = "term_too_long"
    TERM_NOT_IN_SENTENCE = "term_not_in_sentence"
    HEADER_ROW_SKIPPED = "header_row_skipped"  # CSV / TSV only (app/domain/tabular_import.py)
    INVALID_TABLE = "invalid_table"  # CSV / TSV only
    DUPLICATE_IN_FILE = "duplicate_in_file"
    # Added by the preview, which looks at the library (app/services/importing.py).
    DUPLICATE_EXACT = "duplicate_exact"
    DUPLICATE_POSSIBLE = "duplicate_possible"
    ALREADY_IN_DECK = "already_in_deck"
    EXISTING_STATUS_KEPT = "existing_status_kept"


class ImportProblem(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int | None
    severity: Severity
    code: ProblemCode
    message: str
    suggestion: dict[str, Any] | None = None


class ImportHeader(BaseModel):
    model_config = ConfigDict(frozen=True)

    deck: str | None = None
    domain: str | None = None
    source: str | None = None
    context: str | None = None
    deadline: date | None = None


class ParsedRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int
    raw: str
    term: str
    sentence: str | None
    item_type: ItemType
    normalized_form: str
    include: bool
    ambiguous: bool
    problems: list[ImportProblem]


class ParsedImport(BaseModel):
    model_config = ConfigDict(frozen=True)

    header: ImportHeader
    rows: list[ParsedRow]
    # File-level and header problems; row problems live on their row.
    problems: list[ImportProblem]

    @property
    def rejected(self) -> bool:
        return any(problem.severity == Severity.ERROR for problem in self.problems)

    def all_problems(self) -> list[ImportProblem]:
        found = [*self.problems, *(problem for row in self.rows for problem in row.problems)]
        return sorted(found, key=lambda problem: problem.line or 0)


def _problem(
    line: int | None,
    severity: Severity,
    code: ProblemCode,
    message: str,
    suggestion: dict[str, Any] | None = None,
) -> ImportProblem:
    return ImportProblem(
        line=line, severity=severity, code=code, message=message, suggestion=suggestion
    )


def too_large_problem() -> ImportProblem:
    return _problem(
        None,
        Severity.ERROR,
        ProblemCode.TOO_LARGE,
        f"The file is too large (limit: {MAX_BYTES // 1024} KB and {MAX_BODY_LINES} lines).",
    )


def not_utf8_problem() -> ImportProblem:
    return _problem(
        None, Severity.ERROR, ProblemCode.NOT_UTF8, "The file is not UTF-8 text. Save it as UTF-8."
    )


def decode_import_bytes(data: bytes) -> str | None:
    """UTF-8 (with or without BOM) text, or None when the bytes are not UTF-8."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


# --- Term checks (shared by the parser and the commit's re-validation) ------------------------

_WRAPPERS = ("**", "__", "`", "*", "_")
# A translation or definition: "term = traduction", "term : def", "term -> x", "term - x".
_DEFINITION = re.compile(r"\s(?:=|:|->|→|=>|[-–—])\s|(?<=\w):\s+(?=\S)")


def clean_term(text: str) -> str:
    """Strip spaces and the Markdown emphasis or code marks around a term."""
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for mark in _WRAPPERS:
            if len(text) > 2 * len(mark) and text.startswith(mark) and text.endswith(mark):
                text = text[len(mark) : -len(mark)].strip()
                changed = True
    return text


def guess_item_type(term: str) -> ItemType:
    """1 word -> word; 2-4 words or "to + verb" -> collocation; longer -> phrase.

    `spoken_formula` is never guessed: the user (or the AI, M3.b) chooses it.
    """
    words = term.split()
    if len(words) <= 1:
        return ItemType.WORD
    if len(words) <= 4 or (len(words) == 5 and words[0].casefold() == "to"):
        return ItemType.COLLOCATION
    return ItemType.PHRASE


def check_term(term: str, sentence: str | None, line: int | None) -> list[ImportProblem]:
    """Problems of one (already cleaned) term and its sentence, as the user would import it."""
    if not term:
        return [_problem(line, Severity.AMBIGUOUS, ProblemCode.EMPTY_TERM, "The term is empty.")]
    if "|" in term:
        return [
            _problem(
                line,
                Severity.AMBIGUOUS,
                ProblemCode.MULTIPLE_SEPARATORS,
                "More than one '|': only the first one separates the term from its sentence.",
            )
        ]
    if len(term) > MAX_TERM_CHARS:
        return [
            _problem(
                line,
                Severity.AMBIGUOUS,
                ProblemCode.TERM_TOO_LONG,
                f"The term is longer than {MAX_TERM_CHARS} characters.",
            )
        ]
    problems: list[ImportProblem] = []
    if sentence is None:
        match = _DEFINITION.search(term)
        if match is not None and term[: match.start()].strip() and term[match.end() :].strip():
            left = clean_term(term[: match.start()])
            right = term[match.end() :].strip()
            problems.append(
                _problem(
                    line,
                    Severity.AMBIGUOUS,
                    ProblemCode.LOOKS_LIKE_DEFINITION,
                    "This line looks like a term followed by a translation or a definition.",
                    {"term": left, "note": right},
                )
            )
        elif len(term.split()) > SENTENCE_MAX_WORDS or len(term) > SENTENCE_MAX_CHARS:
            problems.append(
                _problem(
                    line,
                    Severity.AMBIGUOUS,
                    ProblemCode.LOOKS_LIKE_SENTENCE,
                    "This line looks like a sentence, not a term. Use 'term | sentence'.",
                )
            )
    elif not term_in_sentence(term, sentence):
        problems.append(
            _problem(
                line,
                Severity.WARNING,
                ProblemCode.TERM_NOT_IN_SENTENCE,
                "The term was not found in its sentence.",
            )
        )
    return problems


def is_ambiguous(problems: list[ImportProblem]) -> bool:
    return any(problem.severity == Severity.AMBIGUOUS for problem in problems)


# --- Header ------------------------------------------------------------------------------------


class _HeaderLoader(yaml.SafeLoader):
    """`yaml.SafeLoader` that keeps dates as text: PyYAML raises ValueError on "2026-13-01",
    and the deadline gets its own check and problem code below."""


_HeaderLoader.add_constructor(
    "tag:yaml.org,2002:timestamp", lambda loader, node: loader.construct_scalar(node)
)

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _header_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str | int | float | date):
        text = str(value).strip()
        return text or None
    raise TypeError


def _key_line(lines: list[str], first: int, key: str) -> int:
    pattern = re.compile(rf"^\s*['\"]?{re.escape(key)}['\"]?\s*:")
    for index in range(first, len(lines)):
        if pattern.match(lines[index]):
            return index + 1
    return first + 1


def _parse_deadline(value: Any) -> date | None:
    if isinstance(value, str) and _ISO_DATE.fullmatch(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _parse_header(
    lines: list[str], start: int, end: int, today: date
) -> tuple[ImportHeader, list[ImportProblem]]:
    """`lines[start:end]` is the YAML between the two `---` lines (0-based indexes)."""
    problems: list[ImportProblem] = []
    try:
        data: Any = yaml.load("\n".join(lines[start:end]), Loader=_HeaderLoader)  # noqa: S506
        valid = data is None or isinstance(data, dict)
    except yaml.YAMLError:
        data, valid = None, False
    if not valid:
        problems.append(
            _problem(
                start,  # 1-based line of the opening `---`
                Severity.WARNING,
                ProblemCode.INVALID_HEADER,
                "The header is not valid YAML; it was ignored and the list was read anyway.",
            )
        )
        return ImportHeader(), problems
    if data is None:
        return ImportHeader(), problems

    values: dict[str, Any] = {}
    for raw_key, value in data.items():
        key = str(raw_key)
        line = _key_line(lines, start, key)
        if key not in HEADER_KEYS:
            problems.append(
                _problem(
                    line,
                    Severity.WARNING,
                    ProblemCode.UNKNOWN_HEADER_KEY,
                    f"Unknown header key '{key}' (known: {', '.join(HEADER_KEYS)}); ignored.",
                    {"key": key},
                )
            )
            continue
        if key == "deadline":
            if value is None:
                continue
            deadline = _parse_deadline(value)
            if deadline is None:
                problems.append(
                    _problem(
                        line,
                        Severity.WARNING,
                        ProblemCode.INVALID_DEADLINE,
                        "The deadline must be a date written YYYY-MM-DD; it was ignored.",
                    )
                )
                continue
            if deadline < today:
                problems.append(
                    _problem(
                        line,
                        Severity.WARNING,
                        ProblemCode.PAST_DEADLINE,
                        "The deadline is in the past.",
                    )
                )
            values[key] = deadline
            continue
        try:
            values[key] = _header_text(value)
        except TypeError:
            problems.append(
                _problem(
                    line,
                    Severity.WARNING,
                    ProblemCode.INVALID_HEADER_VALUE,
                    f"The header value of '{key}' must be plain text; it was ignored.",
                    {"key": key},
                )
            )
    return ImportHeader(**values), problems


# --- Body --------------------------------------------------------------------------------------

_HEADING = re.compile(r"#{1,6}(?:\s|$)")
_RULE = re.compile(r"(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,}")
_BULLET = re.compile(r"(?:[-*+]|\d{1,4}[.)])(?:\s+|$)")
_CHECKBOX = re.compile(r"\[[ xX]\](?:\s+|$)")


def _indent(raw: str) -> int:
    width = 0
    for char in raw:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            break
    return width


def _parse_line(line: int, raw: str, base_indent: int | None) -> ParsedRow | ImportProblem:
    stripped = raw.strip()
    if _HEADING.match(stripped):
        return _problem(line, Severity.INFO, ProblemCode.HEADING_IGNORED, "Heading ignored.")
    if _RULE.fullmatch(stripped):
        return _problem(
            line, Severity.INFO, ProblemCode.HORIZONTAL_RULE, "Horizontal rule ignored."
        )

    problems: list[ImportProblem] = []
    bullet = _BULLET.match(stripped)
    content = stripped[bullet.end() :] if bullet else stripped
    checkbox = _CHECKBOX.match(content)
    if checkbox:
        content = content[checkbox.end() :]
    if bullet and base_indent is not None and _indent(raw) >= base_indent + 2:
        problems.append(
            _problem(
                line,
                Severity.AMBIGUOUS,
                ProblemCode.NESTED_ITEM,
                "Indented sub-item: is it a separate term or a note on the term above?",
            )
        )

    term_part, separator, sentence_part = content.partition("|")
    term = clean_term(term_part)
    sentence = (sentence_part.strip() or None) if separator else None
    if separator and "|" in sentence_part:
        problems.append(
            _problem(
                line,
                Severity.AMBIGUOUS,
                ProblemCode.MULTIPLE_SEPARATORS,
                "More than one '|': only the first one separates the term from its sentence.",
            )
        )
    else:
        problems.extend(check_term(term, sentence, line))

    return make_row(line, raw, term, sentence, problems)


def make_row(
    line: int, raw: str, term: str, sentence: str | None, problems: list[ImportProblem]
) -> ParsedRow:
    """The row of a cleaned term; ambiguous rows are returned but not included."""
    ambiguous = is_ambiguous(problems)
    return ParsedRow(
        line=line,
        raw=raw.rstrip(),
        term=term,
        sentence=sentence,
        item_type=guess_item_type(term),
        normalized_form=normalize_term(term),
        include=not ambiguous,
        ambiguous=ambiguous,
        problems=problems,
    )


def mark_duplicates(rows: list[ParsedRow]) -> list[ParsedRow]:
    """Keep one row per normalised form: a clear one with a sentence, else the first clear one."""
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if row.normalized_form:
            groups.setdefault(row.normalized_form, []).append(index)
    result = list(rows)
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        kept = min(
            indexes,
            key=lambda i: (rows[i].ambiguous, rows[i].sentence is None, rows[i].line),
        )
        for index in indexes:
            if index == kept:
                continue
            row = rows[index]
            problem = _problem(
                row.line,
                Severity.WARNING,
                ProblemCode.DUPLICATE_IN_FILE,
                f"Same term as line {rows[kept].line}; only that line is imported.",
                {"kept_line": rows[kept].line},
            )
            result[index] = row.model_copy(
                update={"include": False, "problems": [*row.problems, problem]}
            )
    return result


def parse_import(text: str, today: date) -> ParsedImport:
    """Parse a Markdown list. Never raises on user input. `today` is the user's study day."""
    if isinstance(today, datetime):
        raise TypeError("`today` must be a date, not a datetime")
    if len(text.encode("utf-8", errors="replace")) > MAX_BYTES:
        return ParsedImport(header=ImportHeader(), rows=[], problems=[too_large_problem()])
    text = text.removeprefix("\ufeff")
    lines = _LINE_BREAK.split(text)

    header = ImportHeader()
    problems: list[ImportProblem] = []
    body_start = 0
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None and lines[first].strip() == "---":
        closing = next((i for i in range(first + 1, len(lines)) if lines[i].strip() == "---"), None)
        if closing is None:
            problems.append(
                _problem(
                    first + 1,
                    Severity.WARNING,
                    ProblemCode.UNCLOSED_HEADER,
                    "The header has no closing '---'; the file was read as a plain list.",
                )
            )
            body_start = first + 1
        else:
            header, header_problems = _parse_header(lines, first + 1, closing, today)
            problems.extend(header_problems)
            body_start = closing + 1

    body = [(index + 1, lines[index]) for index in range(body_start, len(lines))]
    if sum(1 for _, raw in body if raw.strip()) > MAX_BODY_LINES:
        return ParsedImport(header=ImportHeader(), rows=[], problems=[too_large_problem()])

    rows: list[ParsedRow] = []
    base_indent: int | None = None
    for line, raw in body:
        if not raw.strip():
            continue
        parsed = _parse_line(line, raw, base_indent)
        if isinstance(parsed, ImportProblem):
            problems.append(parsed)
        else:
            if base_indent is None:
                base_indent = _indent(raw)
            rows.append(parsed)
    return ParsedImport(header=header, rows=mark_duplicates(rows), problems=problems)
