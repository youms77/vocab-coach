"""Status rules for lexical items (docs/SPEC.md modules A, B, C, G). Pure Python.

Every allowed transition is listed in `ITEM_TRANSITIONS` together with the only operation that may
perform it; anything else raises `InvalidItemTransition`.
"""

from enum import StrEnum

from app.domain.enums import ItemStatus


class TransitionKind(StrEnum):
    """Which operation may perform a transition."""

    MANUAL = "manual"  # the user's choice: triage, queue, known, archive...
    START_DISCOVERY = "start_discovery"
    COMPLETE_DISCOVERY = "complete_discovery"
    AUTOMATIC = "automatic"  # learning <-> consolidated, after each review
    MARK_ACTIVE = "mark_active"  # module G (M7): correct use in a free production
    UNARCHIVE = "unarchive"


S = ItemStatus
K = TransitionKind

ITEM_TRANSITIONS: dict[ItemStatus, dict[ItemStatus, TransitionKind]] = {
    S.DRAFT: {S.TRIAGE: K.MANUAL, S.QUEUED: K.MANUAL, S.KNOWN: K.MANUAL, S.ARCHIVED: K.MANUAL},
    S.TRIAGE: {S.QUEUED: K.MANUAL, S.KNOWN: K.MANUAL, S.ARCHIVED: K.MANUAL},
    S.QUEUED: {
        S.DISCOVERING: K.START_DISCOVERY,
        S.TRIAGE: K.MANUAL,
        S.KNOWN: K.MANUAL,
        S.ARCHIVED: K.MANUAL,
    },
    S.DISCOVERING: {S.LEARNING: K.COMPLETE_DISCOVERY, S.ARCHIVED: K.MANUAL},
    S.LEARNING: {S.CONSOLIDATED: K.AUTOMATIC, S.ACTIVE: K.MARK_ACTIVE, S.ARCHIVED: K.MANUAL},
    S.CONSOLIDATED: {S.LEARNING: K.AUTOMATIC, S.ACTIVE: K.MARK_ACTIVE, S.ARCHIVED: K.MANUAL},
    # Active stays acquired after a lapse: the card carries the memory information.
    S.ACTIVE: {S.ARCHIVED: K.MANUAL},
    # The user changed their mind about a term they said they knew.
    S.KNOWN: {S.QUEUED: K.MANUAL, S.ARCHIVED: K.MANUAL},
    S.ARCHIVED: {S.LEARNING: K.UNARCHIVE, S.QUEUED: K.UNARCHIVE},
}

del S, K

# Only these statuses have cards that may be reviewed or planned.
REVIEWABLE_STATUSES = frozenset({ItemStatus.LEARNING, ItemStatus.CONSOLIDATED, ItemStatus.ACTIVE})


class InvalidItemTransition(ValueError):
    def __init__(
        self,
        item_id: int | None,
        from_status: ItemStatus,
        to_status: ItemStatus,
        kind: TransitionKind,
    ) -> None:
        self.item_id = item_id
        self.from_status = from_status
        self.to_status = to_status
        self.kind = kind
        allowed = ITEM_TRANSITIONS.get(from_status, {}).get(to_status)
        reason = (
            "not an allowed transition"
            if allowed is None
            else f"only {allowed.value} may perform it, not {kind.value}"
        )
        super().__init__(f"item {item_id}: {from_status} -> {to_status}: {reason}")


def check_item_transition(
    item_id: int | None, from_status: ItemStatus, to_status: ItemStatus, kind: TransitionKind
) -> None:
    if ITEM_TRANSITIONS.get(from_status, {}).get(to_status) != kind:
        raise InvalidItemTransition(item_id, from_status, to_status, kind)


def consolidation_target(
    status: ItemStatus, productive_stability: float | None, threshold_days: float
) -> ItemStatus | None:
    """Status an item should move to after a review, or None if it stays.

    Consolidated <=> its productive card has a stability of at least `threshold_days`.
    Only `learning` and `consolidated` move; `active` is never downgraded.
    """
    consolidated = productive_stability is not None and productive_stability >= threshold_days
    if status == ItemStatus.LEARNING and consolidated:
        return ItemStatus.CONSOLIDATED
    if status == ItemStatus.CONSOLIDATED and not consolidated:
        return ItemStatus.LEARNING
    return None


def unarchive_target(has_cards: bool) -> ItemStatus:
    return ItemStatus.LEARNING if has_cards else ItemStatus.QUEUED
