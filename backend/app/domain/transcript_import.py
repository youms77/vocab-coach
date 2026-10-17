"""Pasted conversation transcripts (module E, M5.a2). Pure Python: no database, no clock.

`parse_transcript` turns a pasted transcript (a ChatGPT voice session, for example) into speaker
turns and finds the user's own turns. It never raises on user input: everything odd is a
`TranscriptProblem {line, severity, code, message}` with a **stable code** (the screens turn codes
into i18n keys, like D-071).

Rules (D-133):
- `\\r\\n`, `\\r` and `\\n` end a line and a UTF-8 BOM is removed (D-071). Line numbers are 1-based.
- A timestamp at the start of a line is removed: always when it is bracketed (`[00:12]`,
  `(12:03 PM)`); otherwise when it has seconds or AM/PM (`00:12:33`, `12:03 PM`), when a label
  follows it, or when it is alone on its line (so "10:30 is fine" keeps its time). A line that was
  only a timestamp is dropped, it does not separate paragraphs.
- A line starting with `Name:` (1 to 3 words, at most 30 characters, starting with a letter, and a
  space or the end of the line after the colon, so `https://` is not a label) opens a turn; the
  next lines belong to it until the next label. Blank lines inside a turn are dropped, so a turn
  never contains an empty line and the user's turns joined by a blank line can be split again
  exactly (`user_turns_of`).
- Lines before the first label form a turn without label (`unlabelled_text`).
- Without any label, turns are the paragraphs separated by blank lines (`no_speaker_labels`).
- Known labels, compared without case: "user" labels you, user, me, moi, vous; "other" labels
  chatgpt, assistant, ai, gpt, tutor. `suggested_user_label` is the user label when exactly one
  distinct one is present.
- The user is designated by a label (`UserByLabel`) or by a mode (`UserByMode`: alternating turns,
  user first or second, or every turn). Without a designation the suggested label is used.
- Punctuation and hesitations are left as they are: the AI task ignores them.

`split_units` and `chunk_units` cut the stored user text into the units and chunks sent to the AI
(`transcript_analysis`).
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.sentences import split_sentences

MAX_PASTED_CHARS = 60_000
MAX_USER_CHARS = 6_000
MAX_LABEL_CHARS = 30
MAX_LABEL_WORDS = 3
CONTEXT_MAX_CHARS = 300  # the other speaker's turn before a user turn, sent as context only
UNIT_MAX_CHARS = 600
CHUNK_MAX_CHARS = 2_500
CHUNK_MAX_UNITS = 20
TURN_SEPARATOR = "\n\n"

KNOWN_USER_LABELS = frozenset({"you", "user", "me", "moi", "vous"})
KNOWN_OTHER_LABELS = frozenset({"chatgpt", "assistant", "ai", "gpt", "tutor"})

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_TIME = r"\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp]\.?[Mm]\.?)?"
_BRACKETED_TIME = re.compile(rf"^\s*(?:\[\s*{_TIME}\s*\]|\(\s*{_TIME}\s*\))\s*[-–—|]?\s*")
_BARE_TIME = re.compile(rf"^\s*(?P<time>{_TIME})(?=\s|$)\s*[-–—|]?\s*")
_STRONG_TIME = re.compile(r"\d{1,2}:\d{2}(?::\d{2}|\s?[AaPp]\.?[Mm]\.?)")
_LABEL = re.compile(r"^\s*(?P<label>[^\W\d_][^:\n]*?)\s*:(?=\s|$)(?P<rest>.*)$")
_LABEL_WORD = re.compile(r"^[\w.'’\-]+$")


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"  # the transcript is still usable
    ERROR = "error"  # nothing can be recorded


class ProblemCode(StrEnum):
    EMPTY_TEXT = "empty_text"
    TOO_LARGE = "too_large"
    NO_SPEAKER_LABELS = "no_speaker_labels"
    SINGLE_SPEAKER = "single_speaker"
    UNLABELLED_TEXT = "unlabelled_text"
    EMPTY_TURN = "empty_turn"
    UNKNOWN_LABEL = "unknown_label"
    NO_USER_TURNS = "no_user_turns"


class TranscriptProblem(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int | None
    severity: Severity
    code: ProblemCode
    message: str


class UserByLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=MAX_LABEL_CHARS)


UserMode = Literal["alternating_user_first", "alternating_user_second", "all_mine"]


class UserByMode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: UserMode


UserDesignation = UserByLabel | UserByMode
LabelKind = Literal["user", "other"]


class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int  # 1-based, in the order of the transcript
    speaker_label: str | None
    text: str
    line_start: int
    is_user: bool | None  # None when no designation could be applied


class LabelCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str  # the first spelling met
    turns: int
    words: int
    chars: int
    known: LabelKind | None


class TranscriptParse(BaseModel):
    model_config = ConfigDict(frozen=True)

    turns: list[Turn]
    labels: list[LabelCount]
    labelled: bool
    suggested_user_label: str | None
    designation: UserByLabel | UserByMode | None  # what was applied (None: no user turns known)
    problems: list[TranscriptProblem]

    @property
    def user_turns(self) -> list[Turn]:
        return [turn for turn in self.turns if turn.is_user]

    @property
    def user_text(self) -> str:
        """What is stored: the user's turns only, joined by a blank line."""
        return TURN_SEPARATOR.join(turn.text for turn in self.user_turns)

    @property
    def user_chars(self) -> int:
        return sum(len(turn.text) for turn in self.user_turns)

    @property
    def user_words(self) -> int:
        return sum(len(turn.text.split()) for turn in self.user_turns)

    @property
    def has_errors(self) -> bool:
        return any(problem.severity is Severity.ERROR for problem in self.problems)

    def user_contexts(self) -> list[str | None]:
        """For each user turn, the other speaker's turn just before it, cut to its last
        `CONTEXT_MAX_CHARS` characters (the question sits at the end); None when the turn before
        is the user's or there is none."""
        contexts: list[str | None] = []
        previous: Turn | None = None
        for turn in self.turns:
            if turn.is_user:
                if previous is None or previous.is_user:
                    contexts.append(None)
                else:
                    contexts.append(cut_context(previous.text))
            previous = turn
        return contexts


def cut_context(text: str, limit: int = CONTEXT_MAX_CHARS) -> str:
    """The end of `text`, at most `limit` characters, "…" first when it was cut."""
    text = " ".join(text.split())
    return text if len(text) <= limit else "…" + text[-(limit - 1) :].lstrip()


def label_kind(label: str) -> LabelKind | None:
    key = label.casefold()
    if key in KNOWN_USER_LABELS:
        return "user"
    if key in KNOWN_OTHER_LABELS:
        return "other"
    return None


# --- Lines ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    label: str | None  # set when the line opens a turn
    dropped: bool = False  # only a timestamp


def _match_label(text: str) -> tuple[str, str] | None:
    match = _LABEL.match(text)
    if match is None:
        return None
    label = " ".join(match.group("label").split())
    words = label.split(" ")
    if len(label) > MAX_LABEL_CHARS or len(words) > MAX_LABEL_WORDS:
        return None
    if not all(_LABEL_WORD.match(word) for word in words):
        return None
    return label, match.group("rest")


def _strip_timestamp(text: str) -> tuple[str, bool]:
    """The line without its leading timestamp, and whether one was removed."""
    match = _BRACKETED_TIME.match(text)
    if match is not None:
        return text[match.end() :], True
    match = _BARE_TIME.match(text)
    if match is None:
        return text, False
    rest = text[match.end() :]
    if not rest.strip() or _STRONG_TIME.fullmatch(match.group("time")) or _match_label(rest):
        return rest, True
    return text, False


def _read_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(_LINE_BREAK.split(text), start=1):
        stripped, had_time = _strip_timestamp(raw)
        if had_time and not stripped.strip():
            lines.append(_Line(number, "", None, dropped=True))
            continue
        found = _match_label(stripped)
        if found is not None:
            lines.append(_Line(number, found[1].strip(), found[0]))
        else:
            lines.append(_Line(number, stripped.strip(), None))
    return lines


# --- Turns ---------------------------------------------------------------------------------------


@dataclass
class _Draft:
    label: str | None
    line_start: int
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _labelled_turns(lines: list[_Line], problems: list[TranscriptProblem]) -> list[_Draft]:
    drafts: list[_Draft] = []
    current: _Draft | None = None
    for line in lines:
        if line.dropped:
            continue
        if line.label is not None:
            current = _Draft(line.label, line.number, [line.text] if line.text else [])
            drafts.append(current)
            continue
        if not line.text:
            continue  # a blank line inside a turn
        if current is None:
            current = _Draft(None, line.number, [])
            drafts.append(current)
            problems.append(
                TranscriptProblem(
                    line=line.number,
                    severity=Severity.WARNING,
                    code=ProblemCode.UNLABELLED_TEXT,
                    message="Text before the first speaker label: it is a turn without a label.",
                )
            )
        current.lines.append(line.text)
    return drafts


def _paragraph_turns(lines: list[_Line]) -> list[_Draft]:
    drafts: list[_Draft] = []
    current: _Draft | None = None
    for line in lines:
        if line.dropped:
            continue
        if not line.text:
            current = None
            continue
        if current is None:
            current = _Draft(None, line.number, [])
            drafts.append(current)
        current.lines.append(line.text)
    return drafts


def _user_flags(
    drafts: list[_Draft],
    designation: UserDesignation | None,
    problems: list[TranscriptProblem],
) -> list[bool] | None:
    if designation is None:
        return None
    if isinstance(designation, UserByLabel):
        key = designation.label.strip().casefold()
        flags = [d.label is not None and d.label.casefold() == key for d in drafts]
        if not any(flags):
            problems.append(
                TranscriptProblem(
                    line=None,
                    severity=Severity.ERROR,
                    code=ProblemCode.UNKNOWN_LABEL,
                    message="The speaker label you chose is not in the transcript.",
                )
            )
        return flags
    if designation.mode == "all_mine":
        return [True] * len(drafts)
    first = 0 if designation.mode == "alternating_user_first" else 1
    return [i % 2 == first for i in range(len(drafts))]


def _label_counts(drafts: list[_Draft]) -> list[LabelCount]:
    order: list[str] = []
    spelling: dict[str, str] = {}
    turns: dict[str, int] = {}
    words: dict[str, int] = {}
    chars: dict[str, int] = {}
    for draft in drafts:
        if draft.label is None:
            continue
        key = draft.label.casefold()
        if key not in spelling:
            order.append(key)
            spelling[key] = draft.label
        turns[key] = turns.get(key, 0) + 1
        words[key] = words.get(key, 0) + len(draft.text.split())
        chars[key] = chars.get(key, 0) + len(draft.text)
    return [
        LabelCount(
            label=spelling[key],
            turns=turns[key],
            words=words[key],
            chars=chars[key],
            known=label_kind(key),
        )
        for key in order
    ]


def _problem(
    code: ProblemCode, severity: Severity, message: str, line: int | None = None
) -> TranscriptProblem:
    return TranscriptProblem(line=line, severity=severity, code=code, message=message)


def parse_transcript(text: str, user: UserDesignation | None = None) -> TranscriptParse:
    """See the module docstring. Never raises on user input."""
    text = text.removeprefix("﻿")
    problems: list[TranscriptProblem] = []
    if len(text) > MAX_PASTED_CHARS:
        problems.append(
            _problem(
                ProblemCode.TOO_LARGE,
                Severity.ERROR,
                f"The text has {len(text)} characters; at most {MAX_PASTED_CHARS} are accepted.",
            )
        )
        return TranscriptParse(
            turns=[],
            labels=[],
            labelled=False,
            suggested_user_label=None,
            designation=None,
            problems=problems,
        )
    lines = _read_lines(text)
    labelled = any(line.label is not None for line in lines)
    if labelled:
        all_drafts = _labelled_turns(lines, problems)
    else:
        all_drafts = _paragraph_turns(lines)
        if all_drafts:
            problems.append(
                _problem(
                    ProblemCode.NO_SPEAKER_LABELS,
                    Severity.WARNING,
                    "No speaker labels: each paragraph is a turn. Say which turns are yours.",
                )
            )
    drafts: list[_Draft] = []
    for draft in all_drafts:
        if draft.text:
            drafts.append(draft)
        else:
            problems.append(
                _problem(
                    ProblemCode.EMPTY_TURN,
                    Severity.WARNING,
                    "This turn is empty; it is ignored.",
                    draft.line_start,
                )
            )
    labels = _label_counts(drafts)
    if not drafts:
        problems.append(
            _problem(ProblemCode.EMPTY_TEXT, Severity.ERROR, "There is no text to analyse.")
        )
    elif (labelled and len(labels) == 1) or (not labelled and len(drafts) == 1):
        problems.append(
            _problem(
                ProblemCode.SINGLE_SPEAKER,
                Severity.WARNING,
                "Only one speaker was found.",
            )
        )
    user_labels = [label.label for label in labels if label.known == "user"]
    suggested = user_labels[0] if len(user_labels) == 1 else None
    designation: UserDesignation | None = user
    if designation is None and suggested is not None:
        designation = UserByLabel(label=suggested)
    flags = _user_flags(drafts, designation, problems) if drafts else None
    turns = [
        Turn(
            index=i + 1,
            speaker_label=draft.label,
            text=draft.text,
            line_start=draft.line_start,
            is_user=flags[i] if flags is not None else None,
        )
        for i, draft in enumerate(drafts)
    ]
    parsed = TranscriptParse(
        turns=turns,
        labels=labels,
        labelled=labelled,
        suggested_user_label=suggested,
        designation=designation if flags is not None else None,
        problems=problems,
    )
    if flags is not None and drafts:
        if not any(flags):
            problems.append(
                _problem(
                    ProblemCode.NO_USER_TURNS,
                    Severity.ERROR,
                    "None of the turns is yours with this choice.",
                )
            )
        elif parsed.user_chars > MAX_USER_CHARS:
            problems.append(
                _problem(
                    ProblemCode.TOO_LARGE,
                    Severity.ERROR,
                    f"Your turns have {parsed.user_chars} characters; at most {MAX_USER_CHARS} "
                    "are analysed at once.",
                )
            )
    return parsed.model_copy(update={"problems": list(problems)})


def user_turns_of(stored_text: str) -> list[str]:
    """The user's turns of a stored transcript (the inverse of `TranscriptParse.user_text`)."""
    return stored_text.split(TURN_SEPARATOR) if stored_text else []


# --- Units and chunks sent to the AI -------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    index: int  # 1-based over the whole transcript, as sent to the AI
    turn: int  # 0-based position among the user's turns
    text: str
    start: int  # offsets in the stored text (Unicode code points)
    end: int
    opens_turn: bool


def _pieces(text: str, limit: int) -> list[tuple[int, int]]:
    """(start, end) pieces of `text`, each at most `limit` characters: whole sentences grouped
    while they fit, a longer sentence cut on spaces, a longer word cut where it must be."""
    if len(text) <= limit:
        return [(0, len(text))]
    bounds: list[tuple[int, int]] = []
    for sentence in split_sentences(text, max_sentences=None):
        if sentence.end - sentence.start > limit:
            bounds.extend(_word_pieces(text, sentence.start, sentence.end, limit))
        else:
            bounds.append((sentence.start, sentence.end))
    grouped: list[tuple[int, int]] = []
    for start, end in bounds:
        if grouped and end - grouped[-1][0] <= limit:
            grouped[-1] = (grouped[-1][0], end)
        else:
            grouped.append((start, end))
    return grouped


def _word_pieces(text: str, start: int, end: int, limit: int) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    for match in re.finditer(r"\S+", text[start:end]):
        w_start, w_end = start + match.start(), start + match.end()
        while w_end - w_start > limit:  # a "word" longer than a unit
            pieces.append((w_start, w_start + limit))
            w_start += limit
        if pieces and w_end - pieces[-1][0] <= limit:
            pieces[-1] = (pieces[-1][0], w_end)
        else:
            pieces.append((w_start, w_end))
    return pieces


def split_units(stored_text: str, limit: int = UNIT_MAX_CHARS) -> list[Unit]:
    """Each user turn is a unit; a turn longer than `limit` is cut (`_pieces`)."""
    units: list[Unit] = []
    offset = 0
    for turn_index, turn in enumerate(user_turns_of(stored_text)):
        for n, (start, end) in enumerate(_pieces(turn, limit)):
            units.append(
                Unit(
                    index=len(units) + 1,
                    turn=turn_index,
                    text=turn[start:end],
                    start=offset + start,
                    end=offset + end,
                    opens_turn=n == 0,
                )
            )
        offset += len(turn) + len(TURN_SEPARATOR)
    return units


def chunk_units(
    units: list[Unit], max_chars: int = CHUNK_MAX_CHARS, max_units: int = CHUNK_MAX_UNITS
) -> list[list[Unit]]:
    """Consecutive units in chunks of at most `max_chars` characters of unit text and
    `max_units` units (a unit is never cut: one unit is at most `UNIT_MAX_CHARS`)."""
    chunks: list[list[Unit]] = []
    size = 0
    for unit in units:
        if chunks and size + len(unit.text) <= max_chars and len(chunks[-1]) < max_units:
            chunks[-1].append(unit)
            size += len(unit.text)
        else:
            chunks.append([unit])
            size = len(unit.text)
    return chunks
