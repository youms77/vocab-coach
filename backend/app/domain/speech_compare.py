"""Word-by-word comparison of a transcription with its target sentence (module F). Pure Python.

The user repeats a target sentence; speech recognition writes down what it heard. The two word
sequences are aligned by a weighted edit distance (dynamic programming with backtracking, so the
alignment is minimal and deterministic; `difflib` is not, D-173). Target words the recogniser did
not find are flagged as *possible* intelligibility issues: speech recognition is not a
pronunciation judge, so nothing here becomes an error automatically.

Words are compared on a canonical form: the normalisation of the grading (D-102: NFKC, typographic
apostrophes, case folding, punctuation), then a few tolerances, because the recogniser writes the
same sound several ways:
- contractions: "it's" = "it is" = "it has" (= "its"), "don't" = "do not", "he'd" = "he would" or
  "he had", "John's" = "Johns" = "John is" = "John has"...;
- numbers from 0 to 100 in digits or in words ("twenty-one" = "21", "a hundred" = "100"), "1,000" =
  "1000", "%" = "percent" = "per cent";
- hyphens: "well-known" = "well known" = "wellknown".
A word that is still different may be `close` (a British / American spelling, or one slip on a long
word), which counts as recognised; anything else is `substituted`.
"""

import itertools
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from app.domain.grading import damerau_levenshtein
from app.domain.normalize import clean_typography

VERSION = "speech-compare-1"

# Dashes that separate words ("this — fixed"), unlike a hyphen inside one ("well-known").
_SEPARATING_DASHES = str.maketrans(dict.fromkeys("–—―", " "))
# A decimal or grouped number ("1,000", "3.5%"), a word (letters or digits, with inner apostrophes
# or hyphens, a final apostrophe as in "students'", an optional "%"), or a lone "%".
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+%?|[^\W_]+(?:['\-][^\W_]+)*'?%?|%")
_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")

_UNIT_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen"
)
_TEN_WORDS = "twenty thirty forty fifty sixty seventy eighty ninety"
_UNITS = {word: value for value, word in enumerate(_UNIT_WORDS.split())}
_TENS = {word: 10 * (index + 2) for index, word in enumerate(_TEN_WORDS.split())}

_NOT = {
    "cannot": ("can", "not"),
    "can't": ("can", "not"),
    "won't": ("will", "not"),
    "shan't": ("shall", "not"),
}
_SUFFIXES = (("'re", "are"), ("'m", "am"), ("'ve", "have"), ("'ll", "will"))
# Before these words "'s" is "is" or "has", never a possessive.
_S_IS_HAS_WORDS = "he she it that this there here what who where when why how"
_S_IS_HAS = frozenset(_S_IS_HAS_WORDS.split())

# Merges tried after the one-to-one match, in this order (target words, heard words): "it's" for
# "it is" is (1, 2). Three words on each side are enough for every tolerance above.
_MERGES = ((1, 2), (2, 1), (1, 3), (3, 1), (2, 2), (2, 3), (3, 2), (3, 3))

COST_MATCH = 0
COST_CLOSE = 1
COST_SUBSTITUTED = 2
COST_MISSING = 2
COST_EXTRA = 2

# British / American spellings two edits apart: "catalogue" / "catalog", "programme" / "program".
_SPELLING = re.compile(r"(ogue|mme)(s?)$")
_GREY = re.compile(r"^grey(s?)$")
CLOSE_MIN_LENGTH = 5


class Op(StrEnum):
    MATCH = "match"
    CLOSE = "close"  # a near spelling, counted as recognised
    SUBSTITUTED = "substituted"
    MISSING = "missing"  # a target word not heard
    EXTRA = "extra"  # a heard word that is not in the target


@dataclass(frozen=True)
class Step:
    """One operation. Words `[target_start, target_end)` of the target were heard as words
    `[heard_start, heard_end)`; an empty range is None in `target` / `heard`."""

    op: Op
    target_start: int
    target_end: int
    heard_start: int
    heard_end: int
    target: str | None
    heard: str | None


@dataclass(frozen=True)
class Unrecognized:
    """A target word the recogniser did not find: substituted (`heard` = what it wrote instead)
    or missing (`heard` = None). `position` is the word's index in the target."""

    position: int
    word: str
    heard: str | None


@dataclass(frozen=True)
class Comparison:
    steps: tuple[Step, ...]
    unrecognized: tuple[Unrecognized, ...]
    target_word_count: int
    heard_word_count: int
    recognized_count: int  # target words of `match` and `close` steps
    word_accuracy: float  # recognized / target words (0.0 for an empty target)
    version: str = VERSION


# --- Words ------------------------------------------------------------------------------------


def words(text: str) -> list[str]:
    """The words of a text as written (typography cleaned, punctuation dropped)."""
    return _TOKEN.findall(clean_typography(text.translate(_SEPARATING_DASHES)))


def _key(word: str) -> str:
    key = word.casefold()
    return key[:-1] if key.endswith("'") else key  # "students'" = "students"


@lru_cache(maxsize=4096)
def _token_variants(key: str) -> tuple[tuple[str, ...], ...]:
    """The ways one word may be written as canonical words (the word itself first)."""
    found: list[tuple[str, ...]] = [(key,)]
    if key == "%":
        found.append(("percent",))
    elif key.endswith("%"):
        found += [variant + ("percent",) for variant in _token_variants(key[:-1])]
    if _THOUSANDS.fullmatch(key):
        found.append((key.replace(",", ""),))
    if key in _NOT:
        found.append(_NOT[key])
    elif key.endswith("n't") and len(key) > 3:
        found.append((key[:-3], "not"))
    for suffix, word in _SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            found.append((key[: -len(suffix)], word))
    if key.endswith("'d") and len(key) > 2:
        found += [(key[:-2], "would"), (key[:-2], "had")]
    if key == "let's":
        found.append(("let", "us"))
    elif key.endswith("'s") and len(key) > 2:
        stem = key[:-2]
        found += [(stem, "is"), (stem, "has")]
        if stem == "it":
            found.append(("its",))
        elif stem not in _S_IS_HAS:
            found.append((stem + "s",))  # "John's" sounds like "Johns"
    if "-" in key:
        parts = tuple(key.split("-"))
        found += [parts, ("".join(parts),)]
    return tuple(dict.fromkeys(found))


def _normalize_sequence(sequence: tuple[str, ...]) -> tuple[str, ...]:
    """Number words to digits (0 to 100) and "per cent" to "percent"."""
    out: list[str] = []
    i = 0
    while i < len(sequence):
        word = sequence[i]
        following = sequence[i + 1] if i + 1 < len(sequence) else None
        if word == "per" and following == "cent":
            out.append("percent")
            i += 2
        elif word in ("a", "one") and following == "hundred":
            out.append("100")
            i += 2
        elif word == "hundred":
            out.append("100")
            i += 1
        elif word in _TENS:
            unit = _UNITS.get(following or "")
            if unit is not None and 1 <= unit <= 9:
                out.append(str(_TENS[word] + unit))
                i += 2
            else:
                out.append(str(_TENS[word]))
                i += 1
        elif word in _UNITS:
            out.append(str(_UNITS[word]))
            i += 1
        else:
            out.append(word)
            i += 1
    return tuple(out)


@lru_cache(maxsize=16384)
def _variants(keys: tuple[str, ...]) -> frozenset[tuple[str, ...]]:
    """Every canonical form of a run of at most three words."""
    combos = itertools.product(*(_token_variants(key) for key in keys))
    return frozenset(
        _normalize_sequence(tuple(word for part in combo for word in part)) for combo in combos
    )


def equivalent(target: Sequence[str], heard: Sequence[str]) -> bool:
    """Whether two runs of words (comparison keys) may be the same speech."""
    return not _variants(tuple(target)).isdisjoint(_variants(tuple(heard)))


def _spelling_key(word: str) -> str:
    word = _SPELLING.sub(lambda m: ("og" if m[1] == "ogue" else "m") + m[2], word)
    return _GREY.sub(r"gray\1", word)


def is_close(target: str, heard: str) -> bool:
    """A near spelling counted as recognised: a British / American variant ("colour" / "color",
    "catalogue" / "catalog", "grey" / "gray"), or one edit (Damerau, D-102) on a target word of
    five letters or more, except on the first letter or for a final -s or -d added or removed
    ("effects" / "effect" is a real difference). Arguments are comparison keys."""
    if target == heard or not (target.isalpha() and heard.isalpha()):
        return False
    if _spelling_key(target) == _spelling_key(heard):
        return True
    if len(target) < CLOSE_MIN_LENGTH or target[0] != heard[0]:
        return False
    for ending in ("s", "d"):
        if target == heard + ending or heard == target + ending:
            return False
    return damerau_levenshtein(target, heard) == 1


# --- Alignment --------------------------------------------------------------------------------


def _options(
    target: Sequence[str], heard: Sequence[str], i: int, j: int
) -> Iterator[tuple[Op, int, int, int]]:
    """The operations that can end the alignment of `target[:i]` with `heard[:j]`, as (op, target
    words, heard words, cost), in the tie-breaking order. The filling and the backtracking both
    use it, so they cannot disagree."""
    same = i > 0 and j > 0 and equivalent(target[i - 1 : i], heard[j - 1 : j])
    if same:
        yield Op.MATCH, 1, 1, COST_MATCH
    for k, length in _MERGES:
        if k <= i and length <= j and equivalent(target[i - k : i], heard[j - length : j]):
            yield Op.MATCH, k, length, COST_MATCH
    if i > 0 and j > 0 and not same:
        if is_close(target[i - 1], heard[j - 1]):
            yield Op.CLOSE, 1, 1, COST_CLOSE
        yield Op.SUBSTITUTED, 1, 1, COST_SUBSTITUTED
    if i > 0:
        yield Op.MISSING, 1, 0, COST_MISSING
    if j > 0:
        yield Op.EXTRA, 0, 1, COST_EXTRA


def _align(target: Sequence[str], heard: Sequence[str]) -> list[tuple[Op, int, int, int, int]]:
    n, m = len(target), len(heard)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            cost[i][j] = min(
                cost[i - k][j - length] + step
                for _, k, length, step in _options(target, heard, i, j)
            )
    steps: list[tuple[Op, int, int, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        for op, k, length, step in _options(target, heard, i, j):
            if cost[i - k][j - length] + step == cost[i][j]:
                steps.append((op, i - k, i, j - length, j))
                i, j = i - k, j - length
                break
    steps.reverse()
    return steps


def compare(target_text: str, heard_text: str) -> Comparison:
    """Align what was heard with the target sentence."""
    target_words = words(target_text)
    heard_words = words(heard_text)
    target_keys = [_key(word) for word in target_words]
    heard_keys = [_key(word) for word in heard_words]

    def text(found: list[str], start: int, end: int) -> str | None:
        return " ".join(found[start:end]) if end > start else None

    steps = tuple(
        Step(
            op=op,
            target_start=ts,
            target_end=te,
            heard_start=hs,
            heard_end=he,
            target=text(target_words, ts, te),
            heard=text(heard_words, hs, he),
        )
        for op, ts, te, hs, he in _align(target_keys, heard_keys)
    )
    unrecognized = tuple(
        Unrecognized(position=step.target_start, word=step.target or "", heard=step.heard)
        for step in steps
        if step.op in (Op.SUBSTITUTED, Op.MISSING)
    )
    recognized = sum(
        step.target_end - step.target_start for step in steps if step.op in (Op.MATCH, Op.CLOSE)
    )
    total = len(target_words)
    return Comparison(
        steps=steps,
        unrecognized=unrecognized,
        target_word_count=total,
        heard_word_count=len(heard_words),
        recognized_count=recognized,
        word_accuracy=recognized / total if total else 0.0,
    )
