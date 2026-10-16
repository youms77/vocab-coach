"""Duplicates in the library (module A): groups to review, and merging two terms.

A merge folds the *source* term into the *target*: deck links, sentence and history move, then the
source is deleted. Cards are never merged: if both terms have cards the merge is refused; if only
the source has cards, the direction is inverted so the cards (and their review history) stay.
"""

from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import (
    Card,
    ConsolidationTaskItem,
    DeckItem,
    Enrichment,
    ErrorEvent,
    ExerciseTemplate,
    LexicalItem,
    ProductionTarget,
)
from app.domain.enums import ItemStatus
from app.domain.events import ItemMerged
from app.domain.normalize import MatchKind
from app.domain.study_day import as_utc
from app.services.library import DeckRef, LibraryError, decks_of, get_item, has_cards


class MergeConflict(LibraryError):
    code = "merge_conflict"


class MergeSameItem(LibraryError):
    status, code = 422, "merge_same_item"


class GroupItem(BaseModel):
    id: int
    term: str
    normalized_form: str
    status: ItemStatus
    has_cards: bool
    decks: list[DeckRef]


class DuplicateGroup(BaseModel):
    match: MatchKind
    key: str  # the shared normalised form (exact) or lemma (possible)
    items: list[GroupItem]


def list_groups(session: Session) -> list[DuplicateGroup]:
    """Exact groups (same normalised form), then possible groups (same lemma, other forms)."""
    exact_keys = select(LexicalItem.normalized_form).group_by(LexicalItem.normalized_form)
    exact_keys = exact_keys.having(func.count() > 1)
    lemma_keys = (
        select(LexicalItem.lemma)
        .where(LexicalItem.lemma.is_not(None))
        .group_by(LexicalItem.lemma)
        .having(func.count(func.distinct(LexicalItem.normalized_form)) > 1)
    )
    items = list(
        session.scalars(
            select(LexicalItem)
            .where(LexicalItem.normalized_form.in_(exact_keys) | LexicalItem.lemma.in_(lemma_keys))
            .order_by(LexicalItem.id)
        )
    )
    exact = set(session.scalars(exact_keys))
    possible = set(session.scalars(lemma_keys))
    with_cards = set(
        session.scalars(
            select(Card.lexical_item_id).where(Card.lexical_item_id.in_([i.id for i in items]))
        )
    )
    decks = decks_of(session, (item.id for item in items))
    by_form: dict[str, list[GroupItem]] = defaultdict(list)
    by_lemma: dict[str, list[GroupItem]] = defaultdict(list)
    for item in items:
        entry = GroupItem(
            id=item.id,
            term=item.term,
            normalized_form=item.normalized_form,
            status=ItemStatus(item.status),
            has_cards=item.id in with_cards,
            decks=decks.get(item.id, []),
        )
        if item.normalized_form in exact:
            by_form[item.normalized_form].append(entry)
        if item.lemma in possible:
            by_lemma[item.lemma].append(entry)
    groups = [
        DuplicateGroup(match=MatchKind.EXACT, key=key, items=members)
        for key, members in sorted(by_form.items())
    ]
    groups += [
        DuplicateGroup(match=MatchKind.POSSIBLE, key=key, items=members)
        for key, members in sorted(by_lemma.items())
    ]
    return groups


class MergeResult(BaseModel):
    kept_id: int
    removed_id: int
    inverted: bool  # the source had the cards, so it was kept instead


def _move_unique_links(
    session: Session,
    model: type[ProductionTarget] | type[ConsolidationTaskItem],
    parent: str,
    source_id: int,
    target_id: int,
) -> None:
    """Re-point rows unique per (parent, term): a row the target already has is dropped."""
    parent_column = getattr(model, parent)
    taken = select(parent_column).where(model.lexical_item_id == target_id)
    session.execute(
        delete(model).where(model.lexical_item_id == source_id, parent_column.in_(taken))
    )
    session.execute(
        update(model).where(model.lexical_item_id == source_id).values(lexical_item_id=target_id)
    )


def merge_items(session: Session, source_id: int, target_id: int, at: datetime) -> MergeResult:
    """Fold `source_id` into `target_id` (or the reverse when only the source has cards).

    Raises ItemNotFound, MergeSameItem or MergeConflict (both terms have cards).
    """
    at = as_utc(at)
    if source_id == target_id:
        raise MergeSameItem("A term cannot be merged into itself.")
    source = get_item(session, source_id)
    target = get_item(session, target_id)
    source_cards, target_cards = has_cards(session, source.id), has_cards(session, target.id)
    if source_cards and target_cards:
        raise MergeConflict(
            "Both terms already have cards and review history: they cannot be merged.",
            item_ids=[source.id, target.id],
        )
    inverted = source_cards and not target_cards
    if inverted:
        source, target = target, source
    session.flush()

    # Deck links: re-point, or fill the target's empty deck sentence and drop the source's link.
    target_links = {
        link.deck_id: link
        for link in session.scalars(select(DeckItem).where(DeckItem.lexical_item_id == target.id))
    }
    for link in list(
        session.scalars(select(DeckItem).where(DeckItem.lexical_item_id == source.id))
    ):
        kept = target_links.get(link.deck_id)
        if kept is None:
            link.lexical_item_id = target.id
        else:
            if kept.context_sentence is None:
                kept.context_sentence = link.context_sentence
            session.delete(link)
    for name in ("origin_sentence", "notes", "part_of_speech", "origin_error_event_id"):
        if getattr(target, name) is None and getattr(source, name) is not None:
            setattr(target, name, getattr(source, name))
    session.flush()

    # History that points at the source moves to the target (nothing is lost with the source).
    session.execute(
        update(ErrorEvent)
        .where(ErrorEvent.lexical_item_id == source.id)
        .values(lexical_item_id=target.id)
    )
    _move_unique_links(session, ProductionTarget, "production_attempt_id", source.id, target.id)
    _move_unique_links(
        session, ConsolidationTaskItem, "consolidation_task_id", source.id, target.id
    )
    target_has_sheet = session.scalar(
        select(exists().where(Enrichment.lexical_item_id == target.id))
    )
    if not target_has_sheet:
        for model in (Enrichment, ExerciseTemplate):
            session.execute(
                update(model)
                .where(model.lexical_item_id == source.id)
                .values(lexical_item_id=target.id)
            )

    record_event(
        session, ItemMerged(lexical_item_id=target.id, merged_item_id=source.id), occurred_at=at
    )
    removed_id = source.id
    session.expire(source)
    session.delete(source)
    session.flush()
    session.expire(target)
    return MergeResult(kept_id=target.id, removed_id=removed_id, inverted=inverted)
