"""Library service (app/services/library.py): decks, terms, search, quick add, deletion rules."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Deck,
    DeckItem,
    ErrorEvent,
    LexicalItem,
    ProductionAttempt,
    ProductionTarget,
)
from app.domain.enums import DeckStatus, ErrorSource, ItemStatus, ItemType, Modality, ProductionKind
from app.domain.events import ItemOrigin
from app.domain.normalize import MatchKind
from app.services import library as lib
from tests.factories import NOW, add_card, add_category
from tests.library_support import count, events


def make_item(
    session: Session,
    term: str,
    deck: Deck | None = None,
    *,
    sentence: str | None = None,
    intake: ItemStatus | None = ItemStatus.QUEUED,
) -> LexicalItem:
    item = lib.create_item(
        session,
        term=term,
        at=NOW,
        origin=ItemOrigin.IMPORT,
        sentence=sentence,
        deck_id=deck.id if deck else None,
        intake=intake,
    )
    if deck is not None:
        lib.add_item_to_deck(session, deck, item, NOW)
    return item


# --- Decks ---------------------------------------------------------------------------------------


def test_create_deck_goes_to_the_end_of_the_queue(session: Session) -> None:
    first = lib.create_deck(session, name="A", at=NOW)
    second = lib.create_deck(session, name="B", at=NOW, deadline=date(2026, 11, 20))
    assert (first.queue_position, second.queue_position) == (0, 1)
    assert second.status == DeckStatus.QUEUED and second.created_at == NOW
    assert [e["deck_id"] for e in events(session, "deck.created")] == [first.id, second.id]


def test_update_deck_logs_changed_field_names_only(session: Session) -> None:
    deck = lib.create_deck(session, name="A", at=NOW, domain="econometrics")
    changed = lib.update_deck(
        session, deck, {"name": "B", "domain": "econometrics", "deadline": date(2026, 12, 1)}, NOW
    )
    assert changed == ["name", "deadline"]
    assert events(session, "deck.updated") == [{"deck_id": deck.id, "fields": ["name", "deadline"]}]
    assert lib.update_deck(session, deck, {"name": "B"}, NOW) == []
    assert len(events(session, "deck.updated")) == 1
    with pytest.raises(ValueError, match="status"):
        lib.update_deck(session, deck, {"status": "done"}, NOW)


def test_deck_counts(session: Session) -> None:
    deck = lib.create_deck(session, name="A", at=NOW)
    make_item(session, "bias", deck)
    make_item(session, "shed light on", deck, intake=ItemStatus.TRIAGE)
    make_item(session, "account for", deck, intake=ItemStatus.TRIAGE)
    counts = lib.deck_counts(session, [deck.id])[deck.id]
    assert counts.total == 3 and counts.by_status == {"queued": 1, "triage": 2}


# --- Terms ---------------------------------------------------------------------------------------


def test_create_item_normalises_and_goes_through_the_status_service(session: Session) -> None:
    item = make_item(session, "  **To account for (sth)** ", sentence=" We account for it. ")
    assert item.term == "To account for (sth)"
    assert (item.normalized_form, item.lemma) == ("account for sth", None)
    assert item.item_type == ItemType.COLLOCATION and item.origin_sentence == "We account for it."
    assert item.status == ItemStatus.QUEUED
    assert events(session, "item.created")[0]["origin"] == "import"
    assert events(session, "item.status_changed") == [
        {"lexical_item_id": item.id, "from_status": "draft", "to_status": "queued"}
    ]
    word = make_item(session, "Results", intake=None)
    assert (word.lemma, word.status, word.item_type) == ("result", ItemStatus.DRAFT, ItemType.WORD)


@pytest.mark.parametrize("term", ["", "  ** **  ", "a | b", "x" * 301])
def test_invalid_terms_are_refused(session: Session, term: str) -> None:
    with pytest.raises(lib.InvalidTerm):
        make_item(session, term)


def test_add_item_to_deck_twice_is_refused(session: Session) -> None:
    deck = lib.create_deck(session, name="A", at=NOW)
    item = make_item(session, "bias", deck)
    with pytest.raises(lib.ItemAlreadyInDeck):
        lib.add_item_to_deck(session, deck, item, NOW)
    other = make_item(session, "variance")
    link = lib.add_item_to_deck(session, deck, other, NOW, context_sentence=" Low variance. ")
    assert (link.position, link.context_sentence) == (1, "Low variance.")
    assert len(events(session, "deck.item_added")) == 2


def test_update_item_recomputes_forms_and_reports_duplicates(session: Session) -> None:
    make_item(session, "results")
    item = make_item(session, "outcome")
    duplicates = lib.update_item(session, item, {"term": "Result", "notes": "  "}, NOW)
    assert (item.term, item.normalized_form, item.lemma) == ("Result", "result", "result")
    assert [(d.term, d.match) for d in duplicates] == [("results", MatchKind.POSSIBLE)]
    assert events(session, "item.edited") == [{"lexical_item_id": item.id, "fields": ["term"]}]
    lib.update_item(session, item, {"term": "Result"}, NOW)
    assert len(events(session, "item.edited")) == 1  # nothing changed, no event
    with pytest.raises(lib.InvalidTerm):
        lib.update_item(session, item, {"term": " "}, NOW)


def test_find_duplicates_includes_archived_and_known(session: Session) -> None:
    deck = lib.create_deck(session, name="Reading", at=NOW)
    archived = make_item(session, "Shed light on", deck)
    archived.status = ItemStatus.ARCHIVED
    known = make_item(session, "study", intake=ItemStatus.KNOWN)
    found = lib.find_duplicates(session, "to shed light on.")
    assert [(c.id, c.match, c.status) for c in found] == [
        (archived.id, MatchKind.EXACT, ItemStatus.ARCHIVED)
    ]
    assert found[0].decks == [lib.DeckRef(id=deck.id, name="Reading")]
    assert [(c.id, c.match) for c in lib.find_duplicates(session, "studies")] == [
        (known.id, MatchKind.POSSIBLE)
    ]
    assert lib.find_duplicates(session, "news") == []


# --- Search --------------------------------------------------------------------------------------


@pytest.fixture
def library(session: Session) -> dict[str, Deck]:
    econ = lib.create_deck(session, name="Econ", at=NOW, domain="econometrics")
    source = lib.create_source(session, title="Book", at=NOW)
    talk = lib.create_deck(session, name="Talk", at=NOW, domain="speaking", source_id=source.id)
    make_item(session, "heteroskedasticity", econ, sentence="Robust to heteroskedasticity.")
    make_item(session, "shed light on", econ, intake=ItemStatus.TRIAGE)
    make_item(session, "100% sure", talk)
    make_item(session, "under_score", talk)
    old = make_item(session, "obsolete", talk)
    old.status = ItemStatus.ARCHIVED
    session.flush()
    return {"econ": econ, "talk": talk}


def terms(session: Session, **kwargs: object) -> list[str]:
    total, items = lib.list_items(session, lib.ItemQuery(**kwargs))  # type: ignore[arg-type]
    assert total >= len(items)
    return [item.term for item in items]


def test_list_items_filters(session: Session, library: dict[str, Deck]) -> None:
    assert terms(session) == ["heteroskedasticity", "shed light on", "100% sure", "under_score"]
    assert terms(session, deck_id=library["econ"].id) == ["heteroskedasticity", "shed light on"]
    assert terms(session, domain="speaking") == ["100% sure", "under_score"]
    assert terms(session, source_id=library["talk"].source_id) == ["100% sure", "under_score"]
    assert terms(session, item_type=ItemType.COLLOCATION) == ["shed light on", "100% sure"]
    assert terms(session, statuses=(ItemStatus.TRIAGE, ItemStatus.ARCHIVED)) == [
        "shed light on",
        "obsolete",
    ]
    assert "obsolete" in terms(session, include_archived=True)


def test_list_items_search_is_escaped_and_case_insensitive(
    session: Session, library: dict[str, Deck]
) -> None:
    assert terms(session, q="SHED") == ["shed light on"]
    assert terms(session, q="robust") == ["heteroskedasticity"]  # origin sentence
    assert terms(session, q="To shed light on.") == ["shed light on"]  # normalised form
    assert terms(session, q="%") == ["100% sure"]
    assert terms(session, q="_") == ["under_score"]
    assert terms(session, q="\\") == []
    assert terms(session, q="   ") == terms(session)


def test_list_items_sort_and_paging(session: Session, library: dict[str, Deck]) -> None:
    assert terms(session, sort="term") == [
        "100% sure",
        "heteroskedasticity",
        "shed light on",
        "under_score",
    ]
    assert terms(session, sort="term", descending=True)[0] == "under_score"
    total, page = lib.list_items(session, lib.ItemQuery(sort="term", limit=2, offset=1))
    assert total == 4 and [item.term for item in page] == ["heteroskedasticity", "shed light on"]


# --- Quick add -----------------------------------------------------------------------------------


def test_quick_add_creates_the_quick_adds_deck_once(session: Session) -> None:
    first = lib.quick_add(session, term="bias", at=NOW)
    second = lib.quick_add(session, term="variance", sentence="High variance.", at=NOW)
    assert first.deck.name == lib.QUICK_ADDS_DECK and first.deck.id == second.deck.id
    assert first.item.status == ItemStatus.QUEUED and not first.attached
    assert second.item.origin_sentence == "High variance."
    assert events(session, "item.created")[0]["origin"] == "quick_add"
    assert count(session, Deck) == 1


def test_quick_add_duplicate_needs_a_choice(session: Session) -> None:
    deck = lib.create_deck(session, name="Talk", at=NOW)
    existing = make_item(session, "Shed light on")
    with pytest.raises(lib.DuplicateTerm) as caught:
        lib.quick_add(session, term="shed light on", deck_id=deck.id, at=NOW)
    assert caught.value.extra["candidates"][0]["id"] == existing.id
    attached = lib.quick_add(
        session, term="shed light on", deck_id=deck.id, on_duplicate="attach", at=NOW
    )
    assert attached.attached and attached.item.id == existing.id
    assert lib.is_in_deck(session, deck.id, existing.id)
    new = lib.quick_add(session, term="shed light on", on_duplicate="new", at=NOW)
    assert new.item.id != existing.id
    with pytest.raises(lib.InvalidAttachTarget):
        lib.quick_add(session, term="shed light on", on_duplicate="attach", attach_to=999, at=NOW)


def test_quick_add_unknown_deck(session: Session) -> None:
    with pytest.raises(lib.DeckNotFound):
        lib.quick_add(session, term="bias", deck_id=42, at=NOW)


# --- Deletion ------------------------------------------------------------------------------------


def test_delete_item_without_history(session: Session) -> None:
    deck = lib.create_deck(session, name="A", at=NOW)
    item = make_item(session, "bias", deck)
    item_id = item.id
    lib.delete_item(session, item, NOW)
    assert session.get(LexicalItem, item_id) is None and count(session, DeckItem) == 0
    assert events(session, "item.deleted") == [{"lexical_item_id": item_id}]


def _attempt(session: Session) -> ProductionAttempt:
    attempt = ProductionAttempt(
        kind=ProductionKind.WRITING, modality=Modality.WRITTEN, prompt_text="p", text="t"
    )
    session.add(attempt)
    session.flush()
    return attempt


@pytest.mark.parametrize("history", ["card", "error", "production"])
def test_delete_item_with_history_is_refused(session: Session, history: str) -> None:
    item = make_item(session, "bias")
    if history == "card":
        add_card(session, item)
    elif history == "error":
        category = add_category(session)
        session.add(
            ErrorEvent(
                source=ErrorSource.MANUAL,
                original_text="o",
                erroneous_text="e",
                correction="c",
                category_id=category.id,
                lexical_item_id=item.id,
                occurred_at=NOW,
            )
        )
    else:
        session.add(
            ProductionTarget(production_attempt_id=_attempt(session).id, lexical_item_id=item.id)
        )
    session.flush()
    with pytest.raises(lib.ItemHasHistory) as caught:
        lib.delete_item(session, item, NOW)
    assert caught.value.extra == {"suggestion": "archive"}
    assert events(session, "item.deleted") == []


def test_delete_deck_removes_terms_of_no_other_deck(session: Session) -> None:
    deck = lib.create_deck(session, name="A", at=NOW)
    other = lib.create_deck(session, name="B", at=NOW)
    own = make_item(session, "bias", deck)
    shared = make_item(session, "variance", deck)
    lib.add_item_to_deck(session, other, shared, NOW)
    own_id, deck_id = own.id, deck.id
    assert lib.delete_deck(session, deck, NOW) == [own_id]
    assert session.get(Deck, deck_id) is None and session.get(LexicalItem, own_id) is None
    assert session.get(LexicalItem, shared.id) is not None
    assert events(session, "deck.deleted") == [{"deck_id": deck_id, "deleted_item_ids": [own_id]}]
    assert events(session, "item.deleted") == [{"lexical_item_id": own_id}]


@pytest.mark.parametrize("how", ["discovered", "shared_with_cards"])
def test_delete_deck_with_history_is_refused(session: Session, how: str) -> None:
    deck = lib.create_deck(session, name="A", at=NOW)
    item = make_item(session, "bias", deck)
    if how == "discovered":
        item.discovered_at = NOW
    else:
        other = lib.create_deck(session, name="B", at=NOW)
        lib.add_item_to_deck(session, other, item, NOW)
        add_card(session, item)
    session.flush()
    with pytest.raises(lib.DeckHasHistory):
        lib.delete_deck(session, deck, NOW)
    assert session.get(Deck, deck.id) is not None and events(session, "deck.deleted") == []
