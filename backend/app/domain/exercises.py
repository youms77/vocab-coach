"""Exercise templates and the business rules of generated content (module A, used by M4).

Pure Python. The sentences used by exercises are generated with the usage sheet and stored in
`exercise_template` (one row per exercise). This module documents each type's `content`, derives
the types that need no extra AI text, and checks the rules the AI output must follow. A broken rule
is a short message naming a location and the rule (never the text itself: messages are journalled
and sent back to the model), which makes the gateway ask for a repair (D-039).

| Type | Direction | Content |
|---|---|---|
| `gap_fill` | productive | `{sentence (exactly one "___"), answer, accepted}` |
| `typed_recall` | productive | `{cue_fr, cue_definition, answer, accepted}`, from the sheet |
| `recognition_in_sentence` | receptive | `{sentence, meaning, meaning_fr, distractors (3)}` |
| `listening_comprehension` | receptive | same shape, reuses the first recognition sentence |
| `sentence_production` | productive | `{situation, example_answer}` |
| `spoken_answer` | productive | `{question, example_answer}` |

`self_assessment` (M4, both directions) has no stored template: it is the degraded mode used when a
term has no template of its direction (`app/domain/exercise_choice.py`). The prompt comes from the
sheet or the original sentence, and the user grades themselves after the reveal.
"""

import re
from collections.abc import Iterable, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import CardDirection
from app.domain.normalize import normalize_term, stem_token, term_in_sentence

GAP = "___"

Text = Annotated[str, Field(min_length=1, max_length=400)]
Form = Annotated[str, Field(min_length=1, max_length=300)]


class _Content(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GapFillContent(_Content):
    sentence: Text
    answer: Form
    accepted: Annotated[list[Form], Field(max_length=8)] = []

    @field_validator("sentence")
    @classmethod
    def one_gap(cls, value: str) -> str:
        if value.count(GAP) != 1:
            raise ValueError(f"the sentence must contain exactly one {GAP}")
        return value


class TypedRecallContent(_Content):
    cue_fr: Annotated[str, Field(max_length=300)] | None = None
    cue_definition: Annotated[str, Field(max_length=1200)] | None = None
    answer: Form
    accepted: Annotated[list[Form], Field(max_length=8)] = []


class RecognitionContent(_Content):
    sentence: Text
    meaning: Text
    meaning_fr: Text
    distractors: Annotated[list[Text], Field(min_length=3, max_length=3)]


class SentenceProductionContent(_Content):
    situation: Text
    example_answer: Text


class SpokenAnswerContent(_Content):
    question: Text
    example_answer: Text


GAP_FILL = "gap_fill"
TYPED_RECALL = "typed_recall"
RECOGNITION = "recognition_in_sentence"
LISTENING = "listening_comprehension"
SENTENCE_PRODUCTION = "sentence_production"
SPOKEN_ANSWER = "spoken_answer"
SELF_ASSESSMENT = "self_assessment"

# How each type is answered (M4). Self-graded types get no proposed rating.
CHOICE_TYPES = frozenset({RECOGNITION, LISTENING})
TYPED_TYPES = frozenset({TYPED_RECALL, GAP_FILL})
SELF_GRADED_TYPES = frozenset({SELF_ASSESSMENT, SENTENCE_PRODUCTION, SPOKEN_ANSWER})

EXERCISE_TYPES: dict[str, tuple[CardDirection, type[_Content]]] = {
    GAP_FILL: (CardDirection.PRODUCTIVE, GapFillContent),
    TYPED_RECALL: (CardDirection.PRODUCTIVE, TypedRecallContent),
    RECOGNITION: (CardDirection.RECEPTIVE, RecognitionContent),
    LISTENING: (CardDirection.RECEPTIVE, RecognitionContent),
    SENTENCE_PRODUCTION: (CardDirection.PRODUCTIVE, SentenceProductionContent),
    SPOKEN_ANSWER: (CardDirection.PRODUCTIVE, SpokenAnswerContent),
}


def validate_content(exercise_type: str, content: dict[str, Any]) -> dict[str, Any]:
    """Validated content of a known type (raises ValueError / ValidationError)."""
    if exercise_type not in EXERCISE_TYPES:
        raise ValueError(f"unknown exercise type {exercise_type!r}")
    model = EXERCISE_TYPES[exercise_type][1]
    return model.model_validate(content).model_dump(mode="json")


# --- Term forms ----------------------------------------------------------------------------------

_PLACEHOLDERS = frozenset({"sb", "sth", "one's", "sb's"})


def _words(term: str) -> list[str]:
    return [word for word in normalize_term(term).split() if word not in _PLACEHOLDERS]


def without_to(term: str) -> str:
    """The answer form of a "to + verb" term: "to account for" -> "account for"."""
    stripped = term.strip()
    return stripped[3:].lstrip() if stripped.lower().startswith("to ") else stripped


def is_form_of(term: str, form: str) -> bool:
    """Is `form` the term or an inflection of it ("drew a conclusion" for "draw a conclusion")?

    Same words once normalised (placeholders left out), at most one word different, and that word
    starts with the same letter (an irregular form keeps it: draw/drew, take/took; not go/went).
    """
    expected, given = _words(term), _words(form)
    if not expected or len(expected) != len(given):
        return False
    different = [
        (a, b) for a, b in zip(expected, given, strict=True) if stem_token(a) != stem_token(b)
    ]
    if not different:
        return True
    return len(different) == 1 and different[0][0][0] == different[0][1][0]


def contains_term(term: str, sentence: str, forms: Iterable[str] = ()) -> bool:
    """The term (regular inflections tolerated) or one of its declared `forms` is in `sentence`."""
    if term_in_sentence(term, sentence):
        return True
    return any(is_form_of(term, form) and term_in_sentence(form, sentence) for form in forms)


def fill_gap(sentence: str, answer: str) -> str:
    return sentence.replace(GAP, answer, 1)


_PUNCTUATION = re.compile(r"[^\w\s']")


def same_sentence(a: str, b: str) -> bool:
    """Equal once case, punctuation and spaces are ignored."""

    def key(text: str) -> str:
        return " ".join(_PUNCTUATION.sub(" ", normalize_term(text)).split())

    return key(a) == key(b)


# --- Rules of generated content ------------------------------------------------------------------


def check_examples(
    term: str, sentences: Sequence[tuple[str, str]], forms: Sequence[str], where: str
) -> list[str]:
    """Every example contains the term; at least one `academic` and one `spoken` example.
    `sentences` holds (sentence, kind)."""
    problems = [
        f"{where}.examples[{i}]: the sentence must contain the term"
        for i, (sentence, _) in enumerate(sentences)
        if not contains_term(term, sentence, forms)
    ]
    kinds = {kind for _, kind in sentences}
    for needed in ("academic", "spoken"):
        if needed not in kinds:
            problems.append(f"{where}.examples: at least one '{needed}' example is required")
    return problems


def check_answer_forms(term: str, answer: str, accepted: Sequence[str], where: str) -> list[str]:
    """`answer` and `accepted` are forms of the term; no initial "to" for a "to + verb" term."""
    problems = []
    if answer.strip().lower().startswith("to ") and term.strip().lower().startswith("to "):
        problems.append(f"{where}.answer: leave out the initial 'to'")
    if not is_form_of(term, answer):
        problems.append(f"{where}.answer: must be the term or an inflected form of it")
    for i, form in enumerate(accepted):
        if not is_form_of(term, form):
            problems.append(f"{where}.accepted[{i}]: must be an inflected form of the term")
    return problems


def check_gap_fill(
    term: str, sentence: str, answer: str, accepted: Sequence[str], where: str
) -> list[str]:
    if sentence.count(GAP) != 1:
        return [f"{where}.sentence: must contain exactly one {GAP}"]
    problems = check_answer_forms(term, answer, accepted, where)
    if not contains_term(term, fill_gap(sentence, answer), [answer, *accepted]):
        problems.append(f"{where}: the sentence completed with the answer must contain the term")
    return problems


def check_no_term(term: str, text: str, family: Sequence[str], where: str) -> list[str]:
    """Active recall: a production prompt never contains the term nor a form of its family."""
    if term_in_sentence(term, text) or any(
        form.strip() and term_in_sentence(form, text) for form in family
    ):
        return [f"{where}: must not contain the term or a word of its family"]
    return []


def check_not_copied(sentence: str, examples: Sequence[str], where: str) -> list[str]:
    if any(same_sentence(sentence, example) for example in examples):
        return [f"{where}: must not repeat an example of the sheet"]
    return []


# --- Derived templates ---------------------------------------------------------------------------


def typed_recall_content(
    term: str,
    translation_fr: Sequence[str],
    definition_simple: str | None,
    accepted: Iterable[str] = (),
) -> dict[str, Any] | None:
    """French / definition -> English recall, built from the sheet (no AI text). None when the
    sheet has neither a translation nor a definition."""
    cue_fr = next((t for t in translation_fr if t.strip()), None)
    cue_definition = definition_simple if definition_simple and definition_simple.strip() else None
    if cue_fr is None and cue_definition is None:
        return None
    answer = without_to(term)
    forms: list[str] = []
    for form in accepted:
        form = without_to(form)
        if form and not same_sentence(form, answer) and form not in forms:
            forms.append(form)
    return validate_content(
        TYPED_RECALL,
        {
            "cue_fr": cue_fr,
            "cue_definition": cue_definition,
            "answer": answer,
            "accepted": forms[:8],
        },
    )
