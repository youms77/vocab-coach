"""What a review step shows before the attempt, and what it reveals after (docs/SPEC.md module C).

Pure Python. Active recall (SPEC section 3, principle 2) is enforced here: `build_prompt` never
returns the answer, the accepted forms, the example answer, the meaning of a choice exercise or the
index of its right option. The solution comes from `build_solution`, which the API only calls
after an attempt (grading) or on an explicit reveal (self-graded types).

Exception: `listening_comprehension` sends the sentence, because speech synthesis runs in the
browser; the interface hides it until the answer.

Choice options are shuffled with a generator seeded by a string (the card id and its `reps`), so
the step and the grading of the same attempt see the same order without storing it.
"""

import random
import re
from typing import Any

from app.domain import exercises as ex
from app.domain.enums import CardDirection
from app.domain.normalize import normalize_term, stem_token
from app.domain.usage_sheet import UsageSheet

# Keys that may only appear in a solution, never in a step (checked by a test of every step).
SOLUTION_KEYS = frozenset(
    {
        "answer",
        "accepted",
        "example_answer",
        "correct_index",
        "meaning",
        "meaning_fr",
        "distractors",
        "solution",
    }
)

_PLACEHOLDERS = frozenset({"sb", "sth", "one's", "sb's"})
_TOKEN = re.compile(r"[\w']+")


def option_seed(card_id: int, reps: int) -> str:
    return f"card:{card_id}:reps:{reps}"


def shuffled_options(content: dict[str, Any], seed: str) -> tuple[list[str], int]:
    """(options, index of the right one): the meaning and its three distractors, shuffled."""
    options = [content["meaning"], *content["distractors"]]
    order = list(range(len(options)))
    random.Random(seed).shuffle(order)  # noqa: S311 (presentation order, not security)
    return [options[i] for i in order], order.index(0)


def gapped(sentence: str, term: str) -> str | None:
    """`sentence` with the term (regular inflections tolerated) replaced by `___`, or None."""
    words = [w for w in normalize_term(term).split() if w not in _PLACEHOLDERS]
    if not words:
        return None
    tokens = list(_TOKEN.finditer(sentence))

    def same(token: str, word: str) -> bool:
        token = token.casefold()
        return token == word or stem_token(token) == stem_token(word)

    for first in range(len(tokens)):
        if not same(tokens[first].group(), words[0]):
            continue
        position, last = first, first
        for word in words[1:]:
            # The object of "rule sth out" may sit between the words: up to two tokens.
            following = range(position + 1, min(position + 4, len(tokens)))
            found = next((k for k in following if same(tokens[k].group(), word)), None)
            if found is None:
                break
            position = last = found
        else:
            start, end = tokens[first].start(), tokens[last].end()
            return sentence[:start] + ex.GAP + sentence[end:]
    return None


def context_sentence(origin_sentence: str | None, sheet: UsageSheet | None) -> str | None:
    """The original sentence if there is one, otherwise the sheet's first example."""
    if origin_sentence and origin_sentence.strip():
        return origin_sentence
    if sheet is not None and sheet.examples:
        return sheet.examples[0].sentence
    return None


def _first_translation(sheet: UsageSheet | None) -> str | None:
    if sheet is None:
        return None
    return next((t for t in sheet.translation_fr if t.strip()), None)


def _definition(sheet: UsageSheet | None) -> str | None:
    if sheet is None or not sheet.definition_simple or not sheet.definition_simple.strip():
        return None
    return sheet.definition_simple


def build_prompt(
    exercise_type: str,
    direction: CardDirection,
    content: dict[str, Any] | None,
    *,
    term: str,
    origin_sentence: str | None,
    sheet: UsageSheet | None,
    seed: str,
) -> dict[str, Any]:
    """What the user sees before answering. `content` is the template's (None for
    `self_assessment`)."""
    if exercise_type in ex.CHOICE_TYPES:
        assert content is not None  # noqa: S101 (choice types always have a template)
        options, _ = shuffled_options(content, seed)
        return {"sentence": content["sentence"], "options": options}
    if exercise_type == ex.GAP_FILL:
        assert content is not None  # noqa: S101
        return {"sentence": content["sentence"]}
    if exercise_type == ex.TYPED_RECALL:
        assert content is not None  # noqa: S101
        return {"cue_fr": content.get("cue_fr"), "cue_definition": content.get("cue_definition")}
    if exercise_type == ex.SENTENCE_PRODUCTION:
        assert content is not None  # noqa: S101
        return {"situation": content["situation"]}
    if exercise_type == ex.SPOKEN_ANSWER:
        assert content is not None  # noqa: S101
        return {"question": content["question"]}
    # self_assessment
    sentence = context_sentence(origin_sentence, sheet)
    if direction == CardDirection.RECEPTIVE:
        return {"term": term, "sentence": sentence}
    return {
        "cue_fr": _first_translation(sheet),
        "cue_definition": _definition(sheet),
        "sentence_gapped": gapped(sentence, term) if sentence else None,
    }


def prompt_has_cue(prompt: dict[str, Any]) -> bool:
    """False for a productive self-assessment with nothing to recall the term from."""
    return any(value for value in prompt.values())


def build_solution(
    exercise_type: str,
    content: dict[str, Any] | None,
    *,
    term: str,
    origin_sentence: str | None,
    sheet: UsageSheet | None,
    seed: str,
) -> dict[str, Any]:
    """What is revealed after the attempt."""
    if exercise_type in ex.CHOICE_TYPES:
        assert content is not None  # noqa: S101
        _, correct = shuffled_options(content, seed)
        return {
            "correct_index": correct,
            "meaning": content["meaning"],
            "meaning_fr": content["meaning_fr"],
            "sentence": content["sentence"],
        }
    if exercise_type == ex.GAP_FILL:
        assert content is not None  # noqa: S101
        return {
            "answer": content["answer"],
            "accepted": list(content.get("accepted", [])),
            "sentence": ex.fill_gap(content["sentence"], content["answer"]),
        }
    if exercise_type == ex.TYPED_RECALL:
        assert content is not None  # noqa: S101
        return {"answer": content["answer"], "accepted": list(content.get("accepted", []))}
    if exercise_type in (ex.SENTENCE_PRODUCTION, ex.SPOKEN_ANSWER):
        assert content is not None  # noqa: S101
        return {"example_answer": content["example_answer"]}
    return {
        "term": term,
        "definition_simple": _definition(sheet),
        "translation_fr": list(sheet.translation_fr) if sheet is not None else [],
        "sentence": context_sentence(origin_sentence, sheet),
    }


def sheet_summary(term: str, sheet: UsageSheet | None) -> dict[str, Any] | None:
    """A compact view of the sheet for the reveal; the full sheet is `GET /items/{id}/sheet`."""
    if sheet is None:
        return None
    return {
        "term": term,
        "part_of_speech": sheet.part_of_speech,
        "definition_simple": _definition(sheet),
        "translation_fr": list(sheet.translation_fr),
        "pronunciation": (
            sheet.pronunciation.model_dump(mode="json") if sheet.pronunciation else None
        ),
        "examples": [example.sentence for example in sheet.examples[:2]],
    }


def confusion_words(sheet: UsageSheet | None) -> list[str]:
    """Words of the sheet the user may confuse with the term: confusables and pitfalls."""
    if sheet is None:
        return []
    words = [c.term for c in sheet.confusables]
    words += [p.wrong for p in sheet.french_speaker_pitfalls]
    return words
