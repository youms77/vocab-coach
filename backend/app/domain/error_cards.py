"""Cards made from errors, and suggestions for recurring errors (module E, M5.a3). Pure Python.

An error such as "in campus" -> "on campus" can become a term of the library ("on campus"), reviewed
like any other: the term is the corrected fragment, the exercise is a gap-fill of the sentence the
error came from with the changed words blanked, and the usage sheet is built from the error itself
(its explanation, the wrong form as a French speaker's pitfall), so no AI is needed (D-163).

The wrong form is declared as a pitfall on purpose: a typed answer is graded with a tolerance for
typos from four characters on ("in campus" is one edit away from "on campus"), and the sheet's
pitfalls are what makes the wrong form a `wrong` answer instead of a typo (`domain/grading.py`).

Recurring errors are the same (wrong form, correction) pair seen at least twice. The grouping key is
plain text, so a dismissal can be stored in the event log and recognised later.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.exercises import GAP, GapFillContent
from app.domain.sentences import find_fragment
from app.domain.usage_sheet import ExampleKind, UsageSheet

MAX_TERM_WORDS = 6
MAX_TERM_CHARS = 60
MIN_RECURRENCE = 2
MAX_SAMPLE_ERRORS = 5
# A gap-fill sentence is at most this long (`GapFillContent`).
MAX_SENTENCE_CHARS = 400

_WORD = re.compile(r"[\w'’-]+")
_APOSTROPHES = str.maketrans("’‘`´", "''''")


class NotCardable(ValueError):
    """The error cannot become a card; `reason` is a stable code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CardPlan:
    """Everything the service needs to create the term, its sheet and its exercise."""

    term: str
    wrong: str  # the wrong fragment the term replaces
    sentence: str | None  # the corrected sentence the error came from, if known
    gap_fill: dict[str, Any] | None  # `gap_fill` template content, if a sentence is known
    sheet: dict[str, Any]  # `UsageSheet` content


# --- Words and fragments -------------------------------------------------------------------------


def _key(text: str) -> str:
    """A comparable spelling: NFKC, one apostrophe, lower case, words only."""
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).casefold()
    return " ".join(_WORD.findall(text))


def _trim(fragment: str) -> str:
    return fragment.strip().strip(' .,;:!?"“”').strip()


def pair_key(wrong: str, correction: str) -> str:
    """The identity of a recurring error: the same wrong form corrected the same way."""
    return f"{_key(wrong)} => {_key(correction)}"


@dataclass(frozen=True)
class _Diff:
    """The words of `correction` that differ from `wrong`, as word indexes of `correction`."""

    first: int
    last: int  # inclusive; first > last when the correction only deletes words
    right_words: list[re.Match[str]]
    wrong_core: str


def _diff(wrong: str, correction: str) -> _Diff:
    """Strip the words that both forms share at the start and at the end."""
    right_words = list(_WORD.finditer(correction))
    right = [_key(m.group()) for m in right_words]
    left_words = list(_WORD.finditer(wrong))
    left = [_key(m.group()) for m in left_words]
    start = 0
    while start < min(len(left), len(right)) and left[start] == right[start]:
        start += 1
    end = 0
    while (
        end < min(len(left), len(right)) - start
        and left[len(left) - 1 - end] == right[len(right) - 1 - end]
    ):
        end += 1
    last = len(right) - 1 - end
    left_core = left_words[start : len(left_words) - end]
    wrong_core = wrong[left_core[0].start() : left_core[-1].end()] if left_core else ""
    return _Diff(first=start, last=last, right_words=right_words, wrong_core=wrong_core)


def _within_limits(fragment: str) -> bool:
    return 0 < len(fragment) <= MAX_TERM_CHARS and len(_WORD.findall(fragment)) <= MAX_TERM_WORDS


def _focused_term(correction: str, diff: _Diff) -> str:
    """For a long correction (a whole sentence from a drill): the changed words with one word of
    context on each side."""
    words = diff.right_words
    first = max(diff.first - 1, 0)
    last = min(max(diff.last, diff.first) + 1, len(words) - 1)
    return _trim(correction[words[first].start() : words[last].end()])


# --- The plan ------------------------------------------------------------------------------------


def _corrected_sentence(original: str, wrong: str, correction: str) -> str | None:
    """The sentence the error came from, with the wrong form replaced by its correction. A
    correction that is itself a sentence (a drill error) is the sentence."""
    original = original.strip()
    if original:
        found = find_fragment(original, wrong)
        if found is not None:
            return original[: found[0]] + correction.strip() + original[found[1] :]
    if len(_WORD.findall(correction)) > MAX_TERM_WORDS:
        return correction.strip()
    return None


def _gap_fill(sentence: str, wrong: str, correction: str) -> dict[str, Any] | None:
    """The corrected sentence with the changed words blanked: "I live ___ campus." The whole
    corrected fragment is blanked when the correction only removes words."""
    if len(sentence) > MAX_SENTENCE_CHARS:
        return None
    found = find_fragment(sentence, correction)
    if found is None:
        return None
    fragment = sentence[found[0] : found[1]]
    diff = _diff(wrong, fragment)
    if diff.last < diff.first:
        start, end = 0, len(fragment)
    else:
        start = diff.right_words[diff.first].start()
        end = diff.right_words[diff.last].end()
    answer = fragment[start:end].strip()
    if not answer:
        return None
    gapped = sentence[: found[0]] + fragment[:start] + GAP + fragment[end:] + sentence[found[1] :]
    content = GapFillContent(sentence=gapped, answer=answer, accepted=[])
    return content.model_dump(mode="json")


def _sheet(
    term: str, wrong: str, wrong_core: str, sentence: str | None, explanation: str
) -> dict[str, Any]:
    """A small hand-made sheet: the rule as the definition, the wrong forms as pitfalls."""
    rule = explanation.strip() or f'Say "{term}", not "{wrong}".'
    pitfalls = [{"wrong": wrong, "right": term, "explanation": rule}]
    core = wrong_core.strip()
    if core and _key(core) != _key(wrong):
        pitfalls.append({"wrong": core, "right": term, "explanation": rule})
    examples = [{"sentence": sentence, "kind": ExampleKind.GENERAL}] if sentence else []
    sheet = UsageSheet.model_validate(
        {
            "definition_simple": rule[:1200],
            "examples": examples,
            "french_speaker_pitfalls": pitfalls,
        }
    )
    return sheet.model_dump(mode="json")


def plan_card(
    *,
    erroneous_text: str,
    correction: str,
    original_text: str = "",
    explanation: str = "",
    term: str | None = None,
) -> CardPlan:
    """Plan the card of an error. `term` replaces the proposed term (a shorter or a better one).
    Raises NotCardable (`no_correction`, `too_long`, `invalid_term`)."""
    wrong, right = _trim(erroneous_text), _trim(correction)
    if not wrong or not right or _key(wrong) == _key(right):
        raise NotCardable("no_correction", "This error has no different correction to learn.")
    diff = _diff(erroneous_text, correction)
    if term is not None:
        chosen = _trim(term)
        if not _within_limits(chosen):
            raise NotCardable(
                "invalid_term",
                f"A term has at most {MAX_TERM_WORDS} words and {MAX_TERM_CHARS} characters.",
            )
    elif _within_limits(right):
        chosen = right
    else:
        chosen = _focused_term(correction, diff)
        if not _within_limits(chosen):
            raise NotCardable(
                "too_long", "The correction is too long to become a card: give a shorter term."
            )
    sentence = _corrected_sentence(original_text, erroneous_text, correction)
    gap = _gap_fill(sentence, erroneous_text, correction) if sentence else None
    return CardPlan(
        term=chosen,
        wrong=wrong,
        sentence=sentence,
        gap_fill=gap,
        sheet=_sheet(chosen, wrong, diff.wrong_core, sentence, explanation),
    )


# --- Recurring errors ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorRow:
    """What the grouping needs from an error event."""

    error_id: int
    erroneous_text: str
    correction: str
    category_code: str
    occurred_at: datetime


@dataclass(frozen=True)
class Suggestion:
    key: str
    erroneous_text: str  # as written in the latest occurrence
    correction: str
    category_code: str  # the most frequent one in the group
    count: int
    first_at: datetime
    last_at: datetime
    error_ids: tuple[int, ...]  # the latest occurrences, newest first
    latest_error_id: int


def group_recurring(rows: Iterable[ErrorRow], min_count: int = MIN_RECURRENCE) -> list[Suggestion]:
    """Groups of at least `min_count` identical (wrong form, correction) pairs, the most frequent
    first, then the most recent, then by key (a total order, so the result is deterministic)."""
    groups: dict[str, list[ErrorRow]] = {}
    for row in rows:
        key = pair_key(row.erroneous_text, row.correction)
        if _key(row.erroneous_text) and _key(row.correction):
            groups.setdefault(key, []).append(row)
    found = []
    for key, members in groups.items():
        if len(members) < min_count:
            continue
        newest_first = sorted(members, key=lambda r: (r.occurred_at, r.error_id), reverse=True)
        categories = Counter(r.category_code for r in newest_first)
        top = max(categories.values())
        category = next(r.category_code for r in newest_first if categories[r.category_code] == top)
        latest = newest_first[0]
        found.append(
            Suggestion(
                key=key,
                erroneous_text=latest.erroneous_text,
                correction=latest.correction,
                category_code=category,
                count=len(members),
                first_at=newest_first[-1].occurred_at,
                last_at=latest.occurred_at,
                error_ids=tuple(r.error_id for r in newest_first[:MAX_SAMPLE_ERRORS]),
                latest_error_id=latest.error_id,
            )
        )
    found.sort(key=lambda s: (-s.count, -s.last_at.timestamp(), s.key))
    return found


def without_keys(suggestions: Sequence[Suggestion], keys: Iterable[str]) -> list[Suggestion]:
    """The suggestions whose key is not in `keys` (dismissed or already carded)."""
    hidden = set(keys)
    return [s for s in suggestions if s.key not in hidden]
