"""List extension service and the triage of its suggestions (M3.b). Offline, `FakeProvider`."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind, UnavailableReason
from app.db.models import DeckItem, LexicalItem
from app.domain.enums import ItemStatus
from app.domain.events import ItemOrigin, TriageDecision
from app.services import extension, library, triage
from tests.factories import NOW
from tests.library_support import count, events

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


def _deck(engine: Engine, terms: list[str], **fields: Any) -> int:
    with Session(engine) as session:
        deck = library.create_deck(
            session, name=fields.pop("name", "Causal inference reading"), at=NOW, **fields
        )
        for term in terms:
            item = library.create_item(
                session, term=term, at=NOW, origin=ItemOrigin.IMPORT, intake=ItemStatus.QUEUED
            )
            library.add_item_to_deck(session, deck, item, NOW)
        session.commit()
        return deck.id


def _s(term: str, **change: Any) -> dict[str, Any]:
    return {
        "term": term,
        "item_type": "collocation",
        "category": "technical",
        "example_sentence": f"In this paper we discuss {term} at length.",
    } | change


def _extend(engine: Engine, gateway: Gateway, deck_id: int, **kwargs: Any) -> Any:
    return extension.extend_deck(_factory(engine), gateway, deck_id, **kwargs)


def test_suggestions_are_created_in_triage_and_duplicates_dropped(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, ["instrumental variable", "estimate"], domain="econometrics")
    suggestions = [
        _s("instrumental variable"),  # exact duplicate of the library
        _s("Instrumental variables"),  # another form, same lemma? multi-word: no lemma -> new
        _s("selection bias"),
        _s("Selection bias."),  # repeated in the answer
        _s("estimates", item_type="word"),  # possible duplicate of "estimate": kept and marked
        _s("as you can see", item_type="spoken_formula", category="spoken"),
    ]
    fake = provider_factory("a", Success(content={"suggestions": suggestions}))
    report = _extend(engine, make_gateway(fake), deck_id, count=10)

    assert report.status == "ok"
    assert (report.suggested, report.dropped_existing, report.dropped_in_batch) == (6, 1, 1)
    assert len(report.created) == 4
    assert [p.candidates[0].term for p in report.possible_duplicates] == ["estimate"]
    with Session(engine) as session:
        created = [session.get(LexicalItem, i) for i in report.created]
        assert {i.status for i in created} == {ItemStatus.TRIAGE}  # type: ignore[union-attr]
        link = session.scalar(select(DeckItem).where(DeckItem.lexical_item_id == report.created[1]))
        assert link is not None and link.deck_id == deck_id
        assert link.context_sentence == "In this paper we discuss selection bias at length."
        origins = [e["origin"] for e in events(session, "item.created")][-4:]
        assert origins == ["extension"] * 4
        [event] = events(session, "list_extension.generated")
        assert event == {
            "deck_id": deck_id,
            "requested": 10,
            "suggested": 6,
            "created": 4,
            "dropped_existing": 1,
            "dropped_in_batch": 1,
        }
        # The triage list shows them with their sentence, never a sheet.
        listed = triage.list_triage(session, deck_id)
        assert [e.term for e in listed][-1] == "as you can see"


def test_the_request_frames_the_deck_and_its_terms(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, ["heteroskedasticity"], domain="econometrics")
    fake = provider_factory("a", Success(content={"suggestions": [_s("robust errors")]}))
    _extend(engine, make_gateway(fake), deck_id, count=12)
    request = fake.requests[0]
    assert "Suggest 12 terms" in request.user
    assert "domain: econometrics" in request.user and "heteroskedasticity" in request.user
    assert request.user.count("<<<USER_DATA") == 2
    assert request.max_output_tokens == 60 * 17


def test_more_suggestions_than_requested_are_cut(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, ["estimate"])
    suggestions = [_s(f"term number {n}") for n in range(13)]
    fake = provider_factory("a", Success(content={"suggestions": suggestions}))
    report = _extend(engine, make_gateway(fake), deck_id, count=10)
    assert len(report.created) == 10 and report.dropped_in_batch == 3


def test_a_deck_without_terms_domain_or_context_is_refused(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, [])
    fake = provider_factory("a")
    with pytest.raises(extension.NotEnoughContext):
        _extend(engine, make_gateway(fake), deck_id)
    assert fake.calls == 0
    with pytest.raises(library.DeckNotFound):
        _extend(engine, make_gateway(fake), 999)
    context_only = _deck(engine, [], name="Talk", description="My talk on policy evaluation")
    fake = provider_factory("b", Success(content={"suggestions": [_s("policy evaluation")]}))
    assert _extend(engine, make_gateway(fake), context_only).status == "ok"


@pytest.mark.parametrize("bad", [9, 31])
def test_count_bounds(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory, bad: int
) -> None:
    with pytest.raises(ValueError, match="count"):
        _extend(engine, make_gateway(provider_factory("a")), _deck(engine, ["x"]), count=bad)


def test_unavailable_and_incomplete_write_nothing(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, ["estimate"])
    report = _extend(engine, make_gateway(provider_factory("a", configured=False)), deck_id)
    assert (report.status, report.reason) == (
        "unavailable",
        UnavailableReason.NO_PROVIDER_CONFIGURED,
    )
    report = _extend(
        engine, make_gateway(provider_factory("a", Failure(ErrorKind.NETWORK))), deck_id
    )
    assert (report.status, report.reason) == ("unavailable", UnavailableReason.NETWORK)
    bad = {"suggestions": [_s("selection bias", example_sentence="No term here.")]}
    report = _extend(engine, make_gateway(provider_factory("a", Success(content=bad))), deck_id)
    assert report.status == "incomplete"
    with Session(engine) as session:
        assert count(session, LexicalItem) == 1
        assert events(session, "list_extension.generated") == []


def test_known_removes_an_extension_term_from_its_deck_but_keeps_it(
    engine: Engine, provider_factory: ProviderFactory, make_gateway: GatewayFactory
) -> None:
    deck_id = _deck(engine, ["estimate"])
    fake = provider_factory(
        "a", Success(content={"suggestions": [_s("selection bias"), _s("robust errors")]})
    )
    known_id, learn_id = _extend(engine, make_gateway(fake), deck_id, count=10).created
    with Session(engine) as session:
        triage.apply_triage(
            session, [(known_id, TriageDecision.KNOWN), (learn_id, TriageDecision.LEARN)], NOW
        )
        session.commit()
        known = session.get(LexicalItem, known_id)
        assert known is not None and known.status == ItemStatus.KNOWN
        assert library.decks_of(session, [known_id]) == {}
        assert [d.id for d in library.decks_of(session, [learn_id])[learn_id]] == [deck_id]
        assert events(session, "deck.item_removed") == [
            {"deck_id": deck_id, "lexical_item_id": known_id}
        ]
    # Suggested again later: an exact duplicate of a known term, dropped.
    again = provider_factory("b", Success(content={"suggestions": [_s("selection bias")]}))
    assert _extend(engine, make_gateway(again), deck_id).dropped_existing == 1


def test_known_keeps_the_deck_link_of_an_imported_term(engine: Engine) -> None:
    with Session(engine) as session:
        deck = library.create_deck(session, name="Imported", at=NOW)
        item = library.create_item(
            session,
            term="shed light on",
            at=NOW,
            origin=ItemOrigin.IMPORT,
            intake=ItemStatus.TRIAGE,
        )
        library.add_item_to_deck(session, deck, item, NOW)
        triage.apply_triage(session, [(item.id, TriageDecision.KNOWN)], NOW)
        session.commit()
        assert [d.id for d in library.decks_of(session, [item.id])[item.id]] == [deck.id]
        assert events(session, "deck.item_removed") == []
