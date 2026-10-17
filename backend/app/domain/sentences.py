"""Sentence splitting and fragment search (module E). Pure Python, no dependency.

SPEC module E asks for a "line-by-line" correction of free writing; it is a sentence-by-sentence
correction. Numbered sentences give the AI stable indices that its output can be checked against
(`app/ai/schemas/production_correction.py`), and the offsets of each sentence in the original text
place the highlighted errors (`spans`).

Rules:
- a line break always ends a sentence (a textarea is not hard-wrapped);
- `!`, `?` and their runs (`?!`) end a sentence when followed by a space or the end of the line;
- `.` ends a sentence unless it closes a known abbreviation ("e.g.", "Dr.", "p. 12", "et al.") or
  sits inside a number ("3.5": no space follows); "etc." and dotted acronyms ("U.S.", "p.m.") end a
  sentence only when the next word starts with a capital letter or a digit;
- an ellipsis ("..." or "…") ends a sentence only before a capital letter or a digit
  ("I was... tired" is one sentence);
- closing quotes and brackets right after the punctuation belong to the sentence, which goes on
  when a lowercase word follows them ("Really?" she said.);
- a text without final punctuation is still a sentence.
"""

import unicodedata
from dataclasses import dataclass

MAX_SENTENCES = 40

_TERMINATORS = frozenset(".!?…")
_CLOSERS = frozenset("\"'”’»)]")
_OPENERS = frozenset("\"'“‘«([")
_APOSTROPHES = frozenset("‘’‚‛′ʼ´`")

# A period after these never ends a sentence ("Dr. Smith", "e.g. this", "p. 12", "vs. that").
_HARD_ABBREVIATIONS = frozenset(
    {"e.g", "i.e", "dr", "mr", "mrs", "ms", "prof", "vs", "cf", "p", "pp", "fig", "approx", "eq"}
)
# A period after these ends a sentence only before a capital letter or a digit.
_SOFT_ABBREVIATIONS = frozenset({"etc"})


class TextTooLong(ValueError):
    """More than MAX_SENTENCES sentences."""


@dataclass(frozen=True)
class Sentence:
    index: int  # 1-based, as sent to the AI
    text: str
    start: int  # offsets in the original text (Python indices: Unicode code points)
    end: int


def _word_before(line: str, position: int) -> tuple[str, str]:
    """The token that ends right before `position` (letters, digits and inner dots), lowercased,
    and the token before it ("et" for "et al.")."""
    start = position
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "."):
        start -= 1
    word = line[start:position]
    rest = line[:start].rstrip()
    previous_start = len(rest)
    while previous_start > 0 and rest[previous_start - 1].isalpha():
        previous_start -= 1
    return word, rest[previous_start:].casefold()


def _next_visible(line: str, position: int) -> str | None:
    """The first character after spaces and opening quotes or brackets, None at the line end."""
    while position < len(line) and (line[position].isspace() or line[position] in _OPENERS):
        position += 1
    return line[position] if position < len(line) else None


def _starts_sentence(char: str | None) -> bool:
    return char is None or char.isupper() or char.isdigit()


def _is_boundary(
    line: str, position: int, run: str, following: str | None, *, quoted: bool
) -> bool:
    """Does the punctuation `run` found at `position` end a sentence? `quoted`: a closing quote
    or bracket follows it ("Really?" she said: the sentence goes on)."""
    if following is None:
        return True
    if quoted and following.islower():
        return False
    if "!" in run or "?" in run:
        return True
    if "…" in run or len(run) > 1:  # an ellipsis
        return _starts_sentence(following)
    word, previous = _word_before(line, position)
    lowered = word.casefold()
    if lowered in _HARD_ABBREVIATIONS or (lowered == "al" and previous == "et"):
        return False
    if len(word) == 1 and word.isupper():  # an initial: "J. Smith"
        return False
    if lowered in _SOFT_ABBREVIATIONS or "." in word:  # "etc.", "U.S.", "p.m."
        return _starts_sentence(following)
    return True


def _split_line(line: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence of one line, before trimming."""
    bounds: list[tuple[int, int]] = []
    start = i = 0
    while i < len(line):
        if line[i] not in _TERMINATORS:
            i += 1
            continue
        j = i
        while j < len(line) and line[j] in _TERMINATORS:
            j += 1
        k = j
        while k < len(line) and line[k] in _CLOSERS:
            k += 1
        if k < len(line) and not line[k].isspace():  # "3.5", "e.g.,", "U.S.-based"
            i = j
            continue
        if _is_boundary(line, i, line[i:j], _next_visible(line, k), quoted=k > j):
            bounds.append((start, k))
            start = k
        i = k
    bounds.append((start, len(line)))
    return bounds


def split_sentences(text: str, *, max_sentences: int | None = MAX_SENTENCES) -> list[Sentence]:
    """Split `text` into numbered sentences (see the module docstring). Raises TextTooLong when
    there are more than `max_sentences` (None: no limit, used to cut a long transcript turn)."""
    sentences: list[Sentence] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        for start, end in _split_line(line):
            piece = line[start:end]
            stripped = piece.strip()
            if stripped:
                lead = len(piece) - len(piece.lstrip())
                first = offset + start + lead
                sentences.append(
                    Sentence(len(sentences) + 1, stripped, first, first + len(stripped))
                )
        offset += len(line)
    if max_sentences is not None and len(sentences) > max_sentences:
        raise TextTooLong(
            f"The text has {len(sentences)} sentences; at most {max_sentences} are corrected at "
            "once."
        )
    return sentences


# --- Fragment search -----------------------------------------------------------------------------


def _comparable(text: str, *, fold: bool) -> tuple[str, list[int]]:
    """`text` with runs of spaces collapsed, typographic apostrophes straightened and characters
    decomposed (NFD, so "é" and "e" + combining accent match), and for each character of the
    result the index of the original character it comes from."""
    chars: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            if chars and chars[-1] == " ":
                continue
            pieces = " "
        elif char in _APOSTROPHES:
            pieces = "'"
        else:
            pieces = unicodedata.normalize("NFD", char)
            if fold:
                pieces = pieces.casefold()
        for piece in pieces:
            chars.append(piece)
            origin.append(index)
    return "".join(chars), origin


def find_fragment(sentence: str, fragment: str) -> tuple[int, int] | None:
    """(start, end) of `fragment` in `sentence`, ignoring differences of spaces, apostrophes and
    Unicode composition (and of case, when the exact case is not found); None if absent."""
    for fold in (False, True):
        haystack, origin = _comparable(sentence, fold=fold)
        needle, _ = _comparable(fragment.strip(), fold=fold)
        if not needle:
            return None
        found = haystack.find(needle)
        if found >= 0:
            return origin[found], origin[found + len(needle) - 1] + 1
    return None
