"""Deck status rules and the deck queue (docs/SPEC.md module D). Pure Python.

- `paused` and `done` decks supply no new terms; reviews of their terms' cards always continue.
- Queue order: decks with a future deadline first (earliest first), then the others by manual
  position. A past deadline only produces a warning; the deck keeps its normal place.
- A term in several decks (D-013) is proposed once, through the first eligible deck in queue order.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.domain.enums import DeckStatus, ItemStatus

DECK_TRANSITIONS: dict[DeckStatus, frozenset[DeckStatus]] = {
    DeckStatus.QUEUED: frozenset({DeckStatus.ACTIVE, DeckStatus.PAUSED, DeckStatus.DONE}),
    DeckStatus.ACTIVE: frozenset({DeckStatus.PAUSED, DeckStatus.DONE}),
    DeckStatus.PAUSED: frozenset({DeckStatus.ACTIVE, DeckStatus.DONE}),
    DeckStatus.DONE: frozenset({DeckStatus.ACTIVE}),  # reopen
}

# Decks that may supply new terms.
SUPPLYING_STATUSES = frozenset({DeckStatus.QUEUED, DeckStatus.ACTIVE})


class InvalidDeckTransition(ValueError):
    def __init__(self, deck_id: int | None, from_status: DeckStatus, to_status: DeckStatus):
        self.deck_id = deck_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"deck {deck_id}: {from_status} -> {to_status} is not allowed")


def check_deck_transition(
    deck_id: int | None, from_status: DeckStatus, to_status: DeckStatus
) -> None:
    if to_status not in DECK_TRANSITIONS[from_status]:
        raise InvalidDeckTransition(deck_id, from_status, to_status)


@dataclass(frozen=True)
class DeckItemRef:
    lexical_item_id: int
    status: ItemStatus
    position: int = 0


@dataclass(frozen=True)
class DeckSnapshot:
    id: int
    status: DeckStatus
    deadline: date | None = None
    queue_position: int | None = None
    items: tuple[DeckItemRef, ...] = field(default=())

    def has_future_deadline(self, today: date) -> bool:
        return self.deadline is not None and self.deadline > today

    def remaining(self) -> int:
        """Terms still to discover: queued or discovering."""
        return sum(1 for i in self.items if i.status in (ItemStatus.QUEUED, ItemStatus.DISCOVERING))

    def in_triage(self) -> int:
        return sum(1 for i in self.items if i.status == ItemStatus.TRIAGE)


def queue_order(decks: Iterable[DeckSnapshot], today: date) -> list[DeckSnapshot]:
    """Supplying decks (queued, active) in priority order."""

    def key(deck: DeckSnapshot) -> tuple[int, date, int, int, int]:
        future = deck.has_future_deadline(today)
        position = deck.queue_position
        return (
            0 if future else 1,
            deck.deadline if future and deck.deadline else date.max,
            0 if position is not None else 1,
            position if position is not None else 0,
            deck.id,
        )

    return sorted((d for d in decks if d.status in SUPPLYING_STATUSES), key=key)


@dataclass(frozen=True)
class Candidate:
    lexical_item_id: int
    deck_id: int


def queued_candidates(ordered_decks: Sequence[DeckSnapshot]) -> list[Candidate]:
    """Queued terms in proposal order, each once, attributed to its first deck in queue order."""
    seen: set[int] = set()
    result: list[Candidate] = []
    for deck in ordered_decks:
        for ref in sorted(deck.items, key=lambda i: (i.position, i.lexical_item_id)):
            if ref.status == ItemStatus.QUEUED and ref.lexical_item_id not in seen:
                seen.add(ref.lexical_item_id)
                result.append(Candidate(ref.lexical_item_id, deck.id))
    return result


def dense_positions(deck_ids: Sequence[int], expected: Iterable[int]) -> dict[int, int]:
    """New queue positions 0..n-1. `deck_ids` must list every expected deck exactly once."""
    expected_set = set(expected)
    if len(deck_ids) != len(set(deck_ids)) or set(deck_ids) != expected_set:
        raise ValueError(
            f"reorder must list every deck that is not done exactly once: expected "
            f"{sorted(expected_set)}, got {list(deck_ids)}"
        )
    return {deck_id: position for position, deck_id in enumerate(deck_ids)}
