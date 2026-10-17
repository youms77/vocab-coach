"""Term normalisation, naive lemma and duplicate matching (app/domain/normalize.py)."""

import pytest

from app.domain.normalize import (
    MatchKind,
    classify_match,
    naive_lemma,
    normalize_term,
    stem_token,
    term_in_sentence,
)


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Shed light on", "shed light on"),
        ("  shed   light\ton ", "shed light on"),
        ("to account for", "account for"),
        ("To Account For.", "account for"),
        ("account for (sth)", "account for sth"),
        ("account for something", "account for sth"),
        ("depend on someone", "depend on sb"),
        ("depend on (sb)", "depend on sb"),
        ("depend on somebody", "depend on sb"),
        ("make up one’s mind", "make up one's mind"),
        ("make up (one's) mind", "make up one's mind"),
        ("take someone's point", "take sb's point"),
        ("“it is worth noting that”", "it is worth noting that"),
        ("'it is worth noting that.'", "it is worth noting that"),
        ("state–of–the–art", "state-of-the-art"),
        ("state—of-the‐art", "state-of-the-art"),
        ("ﬁndings", "findings"),  # NFKC ligature from a PDF
        ("Straße", "strasse"),  # casefold, not lower
        ("really?!", "really"),
        ("to", "to"),
        ("", ""),
    ],
)
def test_normalize_term(term: str, expected: str) -> None:
    assert normalize_term(term) == expected


@pytest.mark.parametrize(
    "words",
    [
        ("study", "studies", "studied", "studying"),
        ("result", "results"),
        ("estimate", "estimated", "estimates", "estimating"),
        ("run", "running"),
        ("stop", "stopped"),
        ("box", "boxes"),
        ("match", "matches"),
        ("class", "classes"),
        ("movie", "movies"),
    ],
)
def test_stem_groups_inflections(words: tuple[str, ...]) -> None:
    assert len({stem_token(word) for word in words}) == 1


@pytest.mark.parametrize(
    "word",
    ["news", "series", "species", "data", "analysis", "physics", "statistics", "bias", "thing"],
)
def test_lemma_traps_are_left_alone(word: str) -> None:
    assert naive_lemma(word) == word


@pytest.mark.parametrize(
    ("a", "b"),
    [("new", "news"), ("analysis", "analyses"), ("serie", "series"), ("datum", "data")],
)
def test_lemma_traps_do_not_meet(a: str, b: str) -> None:
    assert naive_lemma(a) != naive_lemma(b)


def test_lemma_only_for_single_words() -> None:
    assert naive_lemma("shed light on") is None
    assert naive_lemma("") is None
    assert naive_lemma("results") == "result"


def test_classify_match() -> None:
    assert classify_match("result", "result", "result", "result") == MatchKind.EXACT
    assert classify_match("results", "result", "result", "result") == MatchKind.POSSIBLE
    assert classify_match("account for", None, "account for sth", None) is None
    assert classify_match("news", "news", "new", "new") is None


@pytest.mark.parametrize(
    ("term", "sentence", "found"),
    [
        ("to account for", "We account for regional fixed effects.", True),
        ("to account for", "We accounted for regional fixed effects.", True),
        ("shed light on sth", "This study sheds light on the mechanism.", True),
        ("shed light on", "It sheds some light on the issue.", True),  # gap allowed
        ("heteroskedasticity", "Heteroskedasticity-robust errors.", True),
        ("make up one's mind", "She made up her mind.", False),  # irregular past: warning
        ("estimate", "The estimated effect is small.", True),
        ("heteroskedasticity", "The variance is constant.", False),
        ("light shed", "It sheds light.", False),  # order matters
        ("“worth noting”", "It is worth noting that…", True),
        ("sth", "Anything at all.", True),  # nothing left to look for
    ],
)
def test_term_in_sentence(term: str, sentence: str, found: bool) -> None:
    assert term_in_sentence(term, sentence) is found
