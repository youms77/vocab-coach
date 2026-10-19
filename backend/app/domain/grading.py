"""Automatic grading of review answers (docs/SPEC.md module C). Pure Python, no dependency.

Typed answers (`typed_recall`, `gap_fill`) are compared with the template's `answer` and
`accepted` forms after normalisation; small typos are tolerated, but a word the user may have
confused with the term (another library term, a word of the sheet's "confusables" or "pitfalls")
is wrong, not a typo. Choice answers (recognition, listening) are right or wrong. Self-graded
types (`self_assessment`, `sentence_production`, `spoken_answer`) get no proposed rating; a typed
production is only checked for the term.

Proposed rating: exact or form -> Good (Hard when slower than twice the estimate of its duration
class, D-028); typo -> Hard; wrong or empty -> Again. Easy is never proposed (the user may pick it).
A production checked by the AI (a typed sentence, a spoken answer) is rated from its stored
correction (`production_rating`).
"""

import difflib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain import exercises as ex
from app.domain.normalize import stem_token
from app.domain.srs import Rating

# A correct answer slower than this many times the duration estimate is proposed Hard.
SLOW_FACTOR = 2.0

_APOSTROPHES = str.maketrans(dict.fromkeys("‘’‚‛′ʼ´`", "'"))
_PLACEHOLDERS = frozenset({"sb", "sth", "one's", "sb's", "someone", "something"})


class Outcome(StrEnum):
    EXACT = "exact"
    FORM = "form"  # a regular inflection of the answer (typed recall only)
    TYPO = "typo"
    WRONG = "wrong"
    EMPTY = "empty"


class GradeWarning(StrEnum):
    TERM_MISSING = "term_missing"
    # A spoken answer whose transcription lacks the term: the learner may have left it out, or the
    # recogniser may not have understood it, so no rating is proposed (speech recognition is not a
    # pronunciation judge, D-174).
    TERM_NOT_HEARD = "term_not_heard"


class ConfusionKind(StrEnum):
    LIBRARY_TERM = "library_term"  # another term of the user's library
    CONFUSABLE = "confusable"  # a "similar word not to confuse" of the sheet
    PITFALL = "pitfall"  # the wrong form of a French speaker's pitfall of the sheet


@dataclass(frozen=True)
class Confusion:
    """Why a typed answer is `wrong` rather than a typo: the word it was confused with. A
    confusion creates an error event when the review is recorded (SPEC module C)."""

    kind: ConfusionKind
    matched: str  # the word as the sheet or the library writes it
    explanation: str | None = None  # the sheet's `difference` or pitfall `explanation`


@dataclass(frozen=True)
class DiffPart:
    """One run of a character diff: `equal`, `replace`, `insert` (missing from the answer) or
    `delete` (extra in the answer)."""

    op: str
    given: str
    expected: str


@dataclass(frozen=True)
class GradeResult:
    outcome: Outcome | None  # None for self-graded types
    proposed_rating: Rating | None
    expected: str | None
    accepted: list[str] = field(default_factory=list)
    diff: list[DiffPart] | None = None
    warnings: list[str] = field(default_factory=list)
    confusion: Confusion | None = None  # set for a `wrong` caused by a confusion


# --- Normalisation and distance ------------------------------------------------------------------


def _is_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def normalize_answer(text: str) -> str:
    """NFKC, typographic apostrophes, lower case, single spaces, no punctuation at either end."""
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).casefold()
    text = " ".join(text.split())
    start, end = 0, len(text)
    while start < end and (_is_punctuation(text[start]) or text[start].isspace()):
        start += 1
    while end > start and (_is_punctuation(text[end - 1]) or text[end - 1].isspace()):
        end -= 1
    return text[start:end]


def _without_to(text: str) -> str:
    return text[3:].lstrip() if text.startswith("to ") else text


def is_to_verb(term: str) -> bool:
    return normalize_answer(term).startswith("to ")


def comparable(text: str, term: str) -> str:
    """The normalised form compared with the expected ones; "to" is optional for a to-verb."""
    normalized = normalize_answer(text)
    return _without_to(normalized) if is_to_verb(term) else normalized


def damerau_levenshtein(a: str, b: str) -> int:
    """Edit distance counting insertions, deletions, substitutions and transpositions of two
    adjacent characters (the "optimal string alignment" variant: no substring is edited twice)."""
    if a == b:
        return 0
    rows = len(a) + 1
    cols = len(b) + 1
    d = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        d[i][0] = i
    for j in range(cols):
        d[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def typo_tolerance(expected_length: int) -> int:
    """Edits allowed for a typo: none up to 3 characters, 1 up to 8, then 2."""
    if expected_length <= 3:
        return 0
    if expected_length <= 8:
        return 1
    return 2


def char_diff(given: str, expected: str) -> list[DiffPart]:
    matcher = difflib.SequenceMatcher(None, given, expected, autojunk=False)
    return [
        DiffPart(op, given[i1:i2], expected[j1:j2]) for op, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w']+", text) if w not in _PLACEHOLDERS]


def _inflected(word: str, form: str) -> bool:
    """`form` is `word` itself or a longer regular inflection of it (same stem). A shorter form
    is a truncation, not an inflection: the stemmer gives "rul" for both "rule" and "rul"."""
    return form == word or (len(form) > len(word) and stem_token(form) == stem_token(word))


def is_regular_form(expected: str, given: str) -> bool:
    """Same words up to regular inflections ("accounted for" for "account for").

    Stricter than `exercises.is_form_of`, which also accepts any word with the same first letter
    (for irregular forms such as drew/draw) and would grade "cat" as a form of "confounder".
    Irregular forms are accepted when the template lists them (`accepted`).
    """
    a, b = _words(expected), _words(given)
    return bool(a) and len(a) == len(b) and all(_inflected(x, y) for x, y in zip(a, b, strict=True))


# --- Grading -------------------------------------------------------------------------------------


def propose_rating(
    outcome: Outcome, response_time_ms: int | None, estimate_seconds: float
) -> Rating:
    if outcome in (Outcome.EXACT, Outcome.FORM):
        slow = (
            response_time_ms is not None
            and response_time_ms > SLOW_FACTOR * estimate_seconds * 1000
        )
        return Rating.HARD if slow else Rating.GOOD
    if outcome == Outcome.TYPO:
        return Rating.HARD
    return Rating.AGAIN


def grade_typed(
    *,
    exercise_type: str,
    term: str,
    answer: str,
    accepted: Sequence[str],
    given: str | None,
    confusions: Mapping[str, Confusion] | None = None,
    response_time_ms: int | None = None,
    estimate_seconds: float,
) -> GradeResult:
    """Grade a typed answer. `confusions` maps the words the user may have confused with the
    term, already normalised with `comparable`, to what they are; a match is `wrong` and the
    result says which confusion it was."""
    confusions = confusions or {}
    forms: list[str] = []
    for form in (answer, *accepted):
        key = comparable(form, term)
        if key and key not in forms:
            forms.append(key)
    guess = comparable(given or "", term)

    diff: list[DiffPart] | None = None
    confusion: Confusion | None = None
    if not guess:
        outcome = Outcome.EMPTY
    elif guess in forms:
        outcome = Outcome.EXACT
    elif guess in confusions:
        outcome = Outcome.WRONG
        confusion = confusions[guess]
    elif exercise_type == ex.TYPED_RECALL and any(is_regular_form(f, guess) for f in forms):
        outcome = Outcome.FORM
    elif not forms:
        outcome = Outcome.WRONG
    else:
        nearest = min(forms, key=lambda f: (damerau_levenshtein(guess, f), forms.index(f)))
        if damerau_levenshtein(guess, nearest) <= typo_tolerance(len(nearest)):
            outcome = Outcome.TYPO
            diff = char_diff(guess, nearest)
        else:
            outcome = Outcome.WRONG
    return GradeResult(
        outcome=outcome,
        proposed_rating=propose_rating(outcome, response_time_ms, estimate_seconds),
        expected=answer,
        accepted=list(accepted),
        diff=diff,
        confusion=confusion,
    )


def grade_choice(
    *,
    options: Sequence[str],
    correct_index: int,
    chosen_index: int | None,
    response_time_ms: int | None = None,
    estimate_seconds: float,
) -> GradeResult:
    """A multiple-choice answer: right or wrong (no choice at all is `empty`)."""
    if chosen_index is None:
        outcome = Outcome.EMPTY
    else:
        outcome = Outcome.EXACT if chosen_index == correct_index else Outcome.WRONG
    return GradeResult(
        outcome=outcome,
        proposed_rating=propose_rating(outcome, response_time_ms, estimate_seconds),
        expected=options[correct_index],
    )


def check_production(term: str, text: str | None, forms: Sequence[str] = ()) -> GradeResult:
    """A typed production is self-graded; it only warns when the term is missing."""
    warnings = []
    if text and text.strip() and not ex.contains_term(term, text, forms):
        warnings.append(GradeWarning.TERM_MISSING.value)
    return GradeResult(outcome=None, proposed_rating=None, expected=None, warnings=warnings)


WRITTEN_FEEDBACK = "correction-1"  # a typed production (`app/services/corrections.py`)
SPOKEN_FEEDBACK = "speaking-1"  # a transcribed spoken production (`app/services/speaking.py`)


def _target_check(
    feedback: Mapping[str, Any] | None, lexical_item_id: int
) -> dict[str, Any] | None:
    if not feedback or feedback.get("format") not in (WRITTEN_FEEDBACK, SPOKEN_FEEDBACK):
        return None
    return next(
        (t for t in feedback.get("targets") or [] if t.get("lexical_item_id") == lexical_item_id),
        None,
    )


def production_rating(feedback: Mapping[str, Any] | None, lexical_item_id: int) -> Rating | None:
    """The rating proposed for a production checked by the AI, from its stored feedback (D-128):
    Good when the term was used correctly and no error concerns it, Again when it is misused or
    has an error. A term absent from a written sentence (`correction-1`) is Again; absent from a
    transcription (`speaking-1`) it gives no rating, since the recogniser may have missed it
    (`production_warnings`). None when the check is missing or unusable (the review is then
    self-graded). Easy and Hard are never proposed."""
    check = _target_check(feedback, lexical_item_id)
    if feedback is None or check is None:
        return None
    if not check.get("used"):
        return Rating.AGAIN if feedback.get("format") == WRITTEN_FEEDBACK else None
    errors = (feedback.get("output") or {}).get("errors") or []
    if any(error.get("target_ref") == check.get("ref") for error in errors):
        return Rating.AGAIN
    if check.get("used_correctly") is None:
        return None
    return Rating.GOOD if check["used_correctly"] else Rating.AGAIN


def production_warnings(feedback: Mapping[str, Any] | None, lexical_item_id: int) -> list[str]:
    """`term_not_heard` when a transcription checked by the AI (`speaking-1`) lacks the term."""
    check = _target_check(feedback, lexical_item_id)
    if feedback is None or check is None or feedback.get("format") != SPOKEN_FEEDBACK:
        return []
    return [] if check.get("used") else [GradeWarning.TERM_NOT_HEARD.value]
