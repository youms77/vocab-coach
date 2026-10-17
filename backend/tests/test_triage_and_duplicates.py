"""Intake triage (app/services/triage.py) and duplicates / merge (app/services/duplicates.py)."""

import pytest
from sqlalchemy.orm import Session

from app.db.models import Deck, DeckItem, Enrichment, ErrorEvent, LexicalItem
from app.domain.enums import ErrorSource, ItemStatus
from app.domain.events import ItemOrigin, TriageDecision
from app.domain.normalize import MatchKind
from app.services import duplicates, library, triage
from tests.factories import NOW, add_card, add_category
from tests.library_support import events


def make(
    session: Session,
    term: str,
    deck: Deck | None = None,
    *,
    sentence: str | None = None,
    intake: ItemStatus | None = ItemStatus.TRIAGE,
    context: str | None = None,
) -> LexicalItem:
    item = library.create_item(
        session, term=term, at=NOW, origin=ItemOrigin.IMPORT, sentence=sentence, intake=intake
    )
    if deck is not None:
        library.add_item_to_deck(session, deck, item, NOW, context_sentence=context)
    return item


# --- Triage --------------------------------------------------------------------------------------


def test_list_triage_shows_the_sentence_only(session: Session) -> None:
    deck = library.create_deck(session, name="Reading", at=NOW)
    first = make(session, "shed light on", deck, sentence="It sheds light on it.")
    second = make(session, "bias", deck, sentence="Origin.", context="Deck sentence.")
    make(session, "queued already", deck, intake=ItemStatus.QUEUED)
    other = make(session, "elsewhere")
    entries = triage.list_triage(session, deck.id)
    assert [(e.item_id, e.sentence) for e in entries] == [
        (first.id, "It sheds light on it."),
        (second.id, "Deck sentence."),
    ]
    assert set(triage.TriageEntry.model_fields) == {
        "item_id",
        "term",
        "item_type",
        "sentence",
        "decks",
    }
    assert [e.item_id for e in triage.list_triage(session)] == [first.id, second.id, other.id]
    with pytest.raises(library.DeckNotFound):
        triage.list_triage(session, 999)


def test_apply_triage(session: Session) -> None:
    learn, unsure, known = (make(session, t) for t in ("bias", "variance", "mean"))
    counts = triage.apply_triage(
        session,
        [
            (learn.id, TriageDecision.LEARN),
            (unsure.id, TriageDecision.UNSURE),
            (known.id, TriageDecision.KNOWN),
        ],
        NOW,
    )
    assert counts == {"known": 1, "unsure": 1, "learn": 1}
    assert (learn.status, unsure.status, known.status) == (
        ItemStatus.QUEUED,
        ItemStatus.QUEUED,
        ItemStatus.KNOWN,
    )
    assert events(session, "item.triaged") == [
        {"lexical_item_id": learn.id, "decision": "learn"},
        {"lexical_item_id": unsure.id, "decision": "unsure"},
        {"lexical_item_id": known.id, "decision": "known"},
    ]


def test_apply_triage_is_all_or_nothing(session: Session) -> None:
    waiting = make(session, "bias")
    queued = make(session, "variance", intake=ItemStatus.QUEUED)
    with pytest.raises(triage.NotInTriage) as caught:
        triage.apply_triage(
            session, [(waiting.id, TriageDecision.LEARN), (queued.id, TriageDecision.KNOWN)], NOW
        )
    assert caught.value.extra == {"item_ids": [queued.id]}
    assert waiting.status == ItemStatus.TRIAGE and events(session, "item.triaged") == []
    with pytest.raises(library.ItemNotFound):
        triage.apply_triage(
            session, [(waiting.id, TriageDecision.LEARN), (999, TriageDecision.LEARN)], NOW
        )
    with pytest.raises(triage.DuplicateDecision):
        triage.apply_triage(
            session, [(waiting.id, TriageDecision.LEARN), (waiting.id, TriageDecision.KNOWN)], NOW
        )
    assert waiting.status == ItemStatus.TRIAGE


# --- Duplicate groups ----------------------------------------------------------------------------


def test_list_groups(session: Session) -> None:
    deck = library.create_deck(session, name="Reading", at=NOW)
    a = make(session, "Shed light on", deck)
    b = make(session, "to shed light on")
    c = make(session, "result")
    d = make(session, "results")
    make(session, "news")
    make(session, "new")
    add_card(session, b)
    groups = duplicates.list_groups(session)
    assert [(g.match, g.key, [i.id for i in g.items]) for g in groups] == [
        (MatchKind.EXACT, "shed light on", [a.id, b.id]),
        (MatchKind.POSSIBLE, "result", [c.id, d.id]),
    ]
    assert [i.has_cards for i in groups[0].items] == [False, True]
    assert groups[0].items[0].decks == [library.DeckRef(id=deck.id, name="Reading")]


# --- Merge ---------------------------------------------------------------------------------------


def test_merge_moves_links_and_sentence(session: Session) -> None:
    first = library.create_deck(session, name="A", at=NOW)
    second = library.create_deck(session, name="B", at=NOW)
    target = make(session, "shed light on", first)
    source = make(session, "Shed light on", first, sentence="It sheds light.", context="Ctx A.")
    library.add_item_to_deck(session, second, source, NOW, context_sentence="Ctx B.")
    source_id = source.id
    result = duplicates.merge_items(session, source_id, target.id, NOW)
    assert result == duplicates.MergeResult(kept_id=target.id, removed_id=source_id, inverted=False)
    assert session.get(LexicalItem, source_id) is None
    assert target.origin_sentence == "It sheds light."
    links = {
        link.deck_id: link.context_sentence
        for link in session.query(DeckItem).filter_by(lexical_item_id=target.id)
    }
    assert links == {first.id: "Ctx A.", second.id: "Ctx B."}
    assert events(session, "item.merged") == [
        {"lexical_item_id": target.id, "merged_item_id": source_id}
    ]


def test_merge_keeps_the_target_sentence_and_moves_history(session: Session) -> None:
    target = make(session, "bias", sentence="Kept.")
    source = make(session, "biases", sentence="Dropped.")
    category = add_category(session)
    error = ErrorEvent(
        source=ErrorSource.MANUAL,
        original_text="o",
        erroneous_text="e",
        correction="c",
        category_id=category.id,
        lexical_item_id=source.id,
        occurred_at=NOW,
    )
    sheet = Enrichment(lexical_item_id=source.id, content={}, schema_version=1)
    session.add_all([error, sheet])
    session.flush()
    duplicates.merge_items(session, source.id, target.id, NOW)
    session.refresh(error)
    session.refresh(sheet)
    assert target.origin_sentence == "Kept."
    assert error.lexical_item_id == target.id and sheet.lexical_item_id == target.id


def test_merge_inverts_when_only_the_source_has_cards(session: Session) -> None:
    target = make(session, "bias")
    source = make(session, "Bias")
    add_card(session, source)
    target_id = target.id
    result = duplicates.merge_items(session, source.id, target_id, NOW)
    assert result.inverted and result.kept_id == source.id and result.removed_id == target_id
    assert session.get(LexicalItem, target_id) is None
    assert events(session, "item.merged") == [
        {"lexical_item_id": source.id, "merged_item_id": target_id}
    ]


def test_merge_conflict_when_both_have_cards(session: Session) -> None:
    a, b = make(session, "bias"), make(session, "Bias")
    add_card(session, a)
    add_card(session, b)
    with pytest.raises(duplicates.MergeConflict):
        duplicates.merge_items(session, a.id, b.id, NOW)
    assert events(session, "item.merged") == []
    with pytest.raises(duplicates.MergeSameItem):
        duplicates.merge_items(session, a.id, a.id, NOW)
    with pytest.raises(library.ItemNotFound):
        duplicates.merge_items(session, a.id, 999, NOW)
