"""Decks ready for a consolidation task, for the tests (fictional data)."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.models import Deck, LexicalItem
from app.domain.enums import ItemStatus
from tests.factories import add_card, add_deck, add_item, add_sheet, link


def ready_deck(
    session: Session,
    count: int = 10,
    *,
    name: str = "Causal inference reading",
    stability: float | Callable[[int], float] = 12.0,
    terms: list[str] | None = None,
) -> tuple[Deck, list[LexicalItem]]:
    """A deck whose `count` terms are consolidated, each with a productive card of `stability`
    days (a number, or a function of the position); `terms` names them (default "term number N")."""
    deck = add_deck(session, name)
    items = []
    for n in range(count):
        term = terms[n] if terms else f"term number {n + 1}"
        item = add_item(session, term, ItemStatus.CONSOLIDATED)
        link(session, deck, item)
        add_sheet(session, item)
        card = add_card(session, item)
        card.stability = stability(n) if callable(stability) else stability
        items.append(item)
    session.flush()
    return deck, items
