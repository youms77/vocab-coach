"""Term normalisation and duplicate matching (docs/SPEC.md module A). Pure Python.

`lexical_item.term` keeps the user's spelling; `normalized_form` is what duplicates are matched
on, and `lemma` is a cautious stem used only to *suggest* possible duplicates. The normalised form
is not unique in the database (homographs are allowed): a match is a proposal, never a merge.
"""

import re
import unicodedata
from enum import StrEnum

# Typographic characters pasted from Word or a PDF.
_APOSTROPHES = str.maketrans(dict.fromkeys("‘’‚‛′ʼ´`", "'"))
_QUOTES = str.maketrans(dict.fromkeys("“”„‟«»″", '"'))
_DASHES = str.maketrans(dict.fromkeys("‐‑‒–—―−", "-"))

_TRAILING_PUNCTUATION = ".,;:!?"
_ENCLOSING_QUOTES = ('"', "'")

# Placeholder spellings, with or without parentheses, mapped to one canonical form.
_PLACEHOLDERS = {
    "sb": "sb",
    "sb.": "sb",
    "someone": "sb",
    "somebody": "sb",
    "sth": "sth",
    "sth.": "sth",
    "something": "sth",
    "one's": "one's",
    "ones": "one's",
    "sb's": "sb's",
    "someone's": "sb's",
    "somebody's": "sb's",
}
_PLACEHOLDER_TOKENS = frozenset(_PLACEHOLDERS.values())


def clean_typography(text: str) -> str:
    """NFKC, then typographic apostrophes, quotes and dashes to their ASCII forms."""
    text = unicodedata.normalize("NFKC", text)
    return text.translate(_APOSTROPHES).translate(_QUOTES).translate(_DASHES)


def _canonical_token(token: str) -> str:
    bare = token[1:-1] if token.startswith("(") and token.endswith(")") else token
    return _PLACEHOLDERS.get(bare, token)


def normalize_term(term: str) -> str:
    """The form duplicates are matched on: "To account for (sth)." -> "account for sth"."""
    text = clean_typography(term).casefold()
    text = " ".join(text.split())
    previous = None
    while text != previous:  # quotes and final punctuation can wrap each other
        previous = text
        text = text.rstrip(_TRAILING_PUNCTUATION).strip()
        for quote in _ENCLOSING_QUOTES:
            if len(text) >= 2 and text.startswith(quote) and text.endswith(quote):
                text = text[1:-1].strip()
    if text.startswith("to ") and len(text) > 3:
        text = text[3:].lstrip()
    return " ".join(_canonical_token(token) for token in text.split())


# --- Naive lemma -----------------------------------------------------------------------------

# Words the suffix rules would damage. Returned unchanged.
LEMMA_EXCEPTIONS = frozenset(
    {
        # -s that is not a plural
        "news", "series", "species", "means", "analysis", "analyses", "basis", "bases",
        "thesis", "theses", "hypothesis", "hypotheses", "crisis", "crises", "axis", "axes",
        "bias", "biases", "gas", "canvas", "alias", "atlas", "chaos", "lens", "always",
        "perhaps", "besides", "sometimes", "afterwards", "towards", "whereas", "unless",
        "nevertheless", "thus", "this", "plus", "minus", "bus", "yes", "physics",
        "economics", "statistics", "mathematics", "econometrics", "politics", "ethics",
        "linguistics", "logistics", "headquarters", "whereabouts", "data", "criteria",
        "phenomena", "media",
        # -ing / -ed that are not inflections
        "thing", "nothing", "anything", "everything", "something", "string", "bring",
        "during", "morning", "evening", "spring", "ceiling", "sibling", "wing", "king",
        "ring", "sing", "swing", "sting", "bed", "red", "need", "seed", "speed", "feed",
        "indeed", "hundred", "sacred", "naked", "wicked", "rugged", "kindred",
    }
)  # fmt: skip

_KEEP_DOUBLE = ("ll", "ss", "ff", "zz")


def _undouble(stem: str) -> str:
    doubled = len(stem) >= 3 and stem[-1] == stem[-2] and stem[-2:] not in _KEEP_DOUBLE
    return stem[:-1] if doubled and stem[-1] not in "aeiouy" else stem


def stem_token(word: str) -> str:
    """A cautious stem of one normalised word: studies, studied, studying -> "studi".

    Not a dictionary form: both sides of a comparison go through the same rules, so
    "estimate" and "estimated" meet at "estimat". Short words and exceptions are left alone.
    """
    if len(word) < 4 or word in LEMMA_EXCEPTIONS or not word.isalpha():
        return word
    stem = word
    if word.endswith("ies") and len(word) > 4:
        stem = word[:-3] + "y"
    elif word.endswith(("sses", "shes", "ches", "xes", "zes")):
        stem = word[:-2]
    elif word.endswith(("ss", "us", "is", "ics")):
        stem = word
    elif word.endswith("s"):
        stem = word[:-1]
    elif word.endswith("ied") and len(word) > 4:
        stem = word[:-3] + "y"
    elif word.endswith("eed"):
        stem = word
    elif word.endswith("ed") and len(word) > 4:
        stem = _undouble(word[:-2])
    elif word.endswith("ing") and len(word) > 5:
        stem = _undouble(word[:-3])
    if stem.endswith("e") and not stem.endswith("ee") and len(stem) > 3:
        stem = stem[:-1]
    if stem.endswith("y") and len(stem) > 2:
        stem = stem[:-1] + "i"
    return stem


def naive_lemma(normalized: str) -> str | None:
    """Lemma of a single-word term, None for anything longer (never guessed for expressions)."""
    if not normalized or " " in normalized:
        return None
    return stem_token(normalized)


# --- Matching --------------------------------------------------------------------------------


class MatchKind(StrEnum):
    EXACT = "exact"  # same normalised form
    POSSIBLE = "possible"  # same lemma, different form: the user decides


def classify_match(
    normalized: str, lemma: str | None, other_normalized: str, other_lemma: str | None
) -> MatchKind | None:
    if normalized == other_normalized:
        return MatchKind.EXACT
    if lemma is not None and lemma == other_lemma:
        return MatchKind.POSSIBLE
    return None


_WORD = re.compile(r"[\w']+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(clean_typography(text).casefold())


def term_in_sentence(term: str, sentence: str) -> bool:
    """Does `sentence` contain `term`, in order, tolerating simple inflections and gaps?

    "to account for sth" is found in "We accounted for regional effects". Placeholders are
    ignored (the sentence uses a real object). A term with no word left is considered found.
    """
    words = [token for token in normalize_term(term).split() if token not in _PLACEHOLDER_TOKENS]
    wanted = [stem_token(token) for token in _tokens(" ".join(words))]
    if not wanted:
        return True
    have = [(token, stem_token(token)) for token in _tokens(sentence)]
    position = 0
    for target in wanted:
        while position < len(have):
            token, stem = have[position]
            position += 1
            if stem == target or token == target or (len(target) >= 4 and token.startswith(target)):
                break
        else:
            return False
    return True
