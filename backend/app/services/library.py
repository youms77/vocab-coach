"""Vocabulary library (module A): sources, decks, terms, deck links, search, deletion rules.

Like every service (D-023), these functions work in the caller's transaction and never commit.
Errors that the user can cause are `LibraryError`s with a stable `code` (the API answers with it).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, exists, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.event_log import record_event
from app.db.models import (
    Card,
    ConsolidationTaskItem,
    Deck,
    DeckItem,
    Enrichment,
    ErrorEvent,
    LexicalItem,
    ProductionTarget,
    Source,
)
from app.domain.enums import DeckKind, DeckStatus, EnrichmentStatus, ItemStatus, ItemType
from app.domain.events import (
    DeckCreated,
    DeckDeleted,
    DeckItemAdded,
    DeckUpdated,
    ItemCreated,
    ItemDeleted,
    ItemEdited,
    ItemOrigin,
)
from app.domain.item_status import TransitionKind
from app.domain.markdown_import import (
    MAX_TERM_CHARS,
    ImportProblem,
    check_term,
    clean_term,
    guess_item_type,
    is_ambiguous,
)
from app.domain.normalize import MatchKind, classify_match, naive_lemma, normalize_term
from app.domain.study_day import as_utc
from app.services.items import set_item_status

QUICK_ADDS_DECK = "Quick adds"


class LibraryError(Exception):
    """A refusal the user can cause; `code` is stable (API error code, i18n key)."""

    status = 409
    code = "library_error"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra


class ItemNotFound(LibraryError):
    status, code = 404, "item_not_found"


class DeckNotFound(LibraryError):
    status, code = 404, "deck_not_found"


class SourceNotFound(LibraryError):
    status, code = 404, "source_not_found"


class InvalidTerm(LibraryError):
    status, code = 422, "invalid_term"


class ItemHasHistory(LibraryError):
    code = "item_has_history"


class DeckHasHistory(LibraryError):
    code = "deck_has_history"


class ItemAlreadyInDeck(LibraryError):
    code = "already_in_deck"


class DuplicateTerm(LibraryError):
    code = "duplicate_term"


class InvalidAttachTarget(LibraryError):
    status, code = 422, "invalid_attach_target"


# --- Read models -------------------------------------------------------------------------------


class DeckRef(BaseModel):
    id: int
    name: str


class DuplicateCandidate(BaseModel):
    """An existing term that matches a new one (archived and known terms included)."""

    id: int
    term: str
    normalized_form: str
    status: ItemStatus
    match: MatchKind
    decks: list[DeckRef]


def decks_of(session: Session, item_ids: Iterable[int]) -> dict[int, list[DeckRef]]:
    ids = list(set(item_ids))
    found: dict[int, list[DeckRef]] = defaultdict(list)
    if not ids:
        return found
    rows = session.execute(
        select(DeckItem.lexical_item_id, Deck.id, Deck.name)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(DeckItem.lexical_item_id.in_(ids))
        .order_by(Deck.id)
    )
    for item_id, deck_id, name in rows:
        found[item_id].append(DeckRef(id=deck_id, name=name))
    return found


def find_duplicates_many(
    session: Session, forms: Sequence[tuple[str, str | None]], *, exclude_id: int | None = None
) -> list[list[DuplicateCandidate]]:
    """Candidates for each (normalized_form, lemma), exact matches first, in one query."""
    normalized = {form for form, _ in forms if form}
    lemmas = {lemma for _, lemma in forms if lemma}
    if not normalized and not lemmas:
        return [[] for _ in forms]
    conditions: list[ColumnElement[bool]] = []
    if normalized:
        conditions.append(LexicalItem.normalized_form.in_(normalized))
    if lemmas:
        conditions.append(LexicalItem.lemma.in_(lemmas))
    query = select(LexicalItem).where(or_(*conditions)).order_by(LexicalItem.id)
    if exclude_id is not None:
        query = query.where(LexicalItem.id != exclude_id)
    existing = list(session.scalars(query))
    decks = decks_of(session, (item.id for item in existing))
    result: list[list[DuplicateCandidate]] = []
    for form, lemma in forms:
        candidates = []
        for item in existing:
            match = classify_match(form, lemma, item.normalized_form, item.lemma)
            if match is not None:
                candidates.append(
                    DuplicateCandidate(
                        id=item.id,
                        term=item.term,
                        normalized_form=item.normalized_form,
                        status=ItemStatus(item.status),
                        match=match,
                        decks=decks.get(item.id, []),
                    )
                )
        candidates.sort(key=lambda c: (c.match != MatchKind.EXACT, c.id))
        result.append(candidates)
    return result


def find_duplicates(
    session: Session, term: str, *, exclude_id: int | None = None
) -> list[DuplicateCandidate]:
    normalized = normalize_term(term)
    return find_duplicates_many(
        session, [(normalized, naive_lemma(normalized))], exclude_id=exclude_id
    )[0]


# --- Sources and decks ---------------------------------------------------------------------------


def create_source(
    session: Session,
    *,
    title: str,
    at: datetime,
    author: str | None = None,
    domain: str | None = None,
    context: str | None = None,
) -> Source:
    at = as_utc(at)
    source = Source(
        title=title, author=author, domain=domain, context=context, created_at=at, updated_at=at
    )
    session.add(source)
    session.flush()
    return source


def _end_of_queue(session: Session) -> int:
    last = session.scalar(
        select(func.max(Deck.queue_position)).where(Deck.status != DeckStatus.DONE)
    )
    return 0 if last is None else last + 1


def create_deck(
    session: Session,
    *,
    name: str,
    at: datetime,
    description: str | None = None,
    domain: str | None = None,
    source_id: int | None = None,
    deadline: date | None = None,
    kind: DeckKind = DeckKind.CUSTOM,
    queue_position: int | None | Literal["end"] = "end",
) -> Deck:
    """A new deck, `queued` (it becomes active when its first term starts discovery, D-026)."""
    at = as_utc(at)
    deck = Deck(
        name=name,
        description=description,
        domain=domain,
        source_id=source_id,
        kind=kind,
        status=DeckStatus.QUEUED,
        deadline=deadline,
        queue_position=_end_of_queue(session) if queue_position == "end" else queue_position,
        created_at=at,
        updated_at=at,
    )
    session.add(deck)
    session.flush()
    record_event(
        session, DeckCreated(deck_id=deck.id, kind=deck.kind, status=deck.status), occurred_at=at
    )
    return deck


def get_deck(session: Session, deck_id: int) -> Deck:
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise DeckNotFound(f"There is no deck {deck_id}.")
    return deck


DECK_EDITABLE = ("name", "description", "domain", "deadline", "priority")


def update_deck(session: Session, deck: Deck, changes: dict[str, Any], at: datetime) -> list[str]:
    """Apply the editable fields that really change; log `deck.updated` with their names."""
    unknown = set(changes) - set(DECK_EDITABLE)
    if unknown:
        raise ValueError(f"not editable here: {sorted(unknown)}")
    changed = [
        key for key in DECK_EDITABLE if key in changes and getattr(deck, key) != changes[key]
    ]
    for key in changed:
        setattr(deck, key, changes[key])
    if changed:
        deck.updated_at = as_utc(at)
        record_event(session, DeckUpdated(deck_id=deck.id, fields=changed), occurred_at=as_utc(at))
        session.flush()
    return changed


def _history_condition(item_id: Any) -> ColumnElement[bool]:
    """True when the item has cards (hence reviews), errors, productions or consolidation tasks."""
    return or_(
        exists().where(Card.lexical_item_id == item_id),
        exists().where(ErrorEvent.lexical_item_id == item_id),
        exists().where(ProductionTarget.lexical_item_id == item_id),
        exists().where(ConsolidationTaskItem.lexical_item_id == item_id),
    )


def has_cards(session: Session, item_id: int) -> bool:
    return bool(session.scalar(select(exists().where(Card.lexical_item_id == item_id))))


def item_has_history(session: Session, item_id: int) -> bool:
    return bool(session.scalar(select(_history_condition(item_id))))


def deck_has_history(session: Session, deck: Deck) -> bool:
    """A term of the deck started discovery, or has any history (even through another deck)."""
    started = select(DeckItem.id).join(LexicalItem, LexicalItem.id == DeckItem.lexical_item_id)
    started = started.where(
        DeckItem.deck_id == deck.id,
        or_(LexicalItem.discovered_at.is_not(None), _history_condition(LexicalItem.id)),
    )
    return bool(session.scalar(select(exists(started))))


def delete_deck(session: Session, deck: Deck, at: datetime) -> list[int]:
    """Delete a deck with no history and the terms that belong to no other deck.

    Returns the ids of the deleted terms. Raises DeckHasHistory.
    """
    at = as_utc(at)
    if deck_has_history(session, deck):
        raise DeckHasHistory(
            "A term of this deck has started discovery: the deck cannot be deleted "
            "(pause it or mark it done instead)."
        )
    other_link = aliased(DeckItem)
    other_deck = (
        select(other_link.id)
        .where(other_link.lexical_item_id == LexicalItem.id, other_link.deck_id != deck.id)
        .exists()
    )
    orphans = list(
        session.scalars(
            select(LexicalItem)
            .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
            .where(DeckItem.deck_id == deck.id, ~other_deck)
            .order_by(LexicalItem.id)
        )
    )
    deleted_ids = [item.id for item in orphans]
    for item in orphans:
        record_event(session, ItemDeleted(lexical_item_id=item.id), occurred_at=at)
        session.delete(item)
    record_event(
        session, DeckDeleted(deck_id=deck.id, deleted_item_ids=deleted_ids), occurred_at=at
    )
    session.delete(deck)
    session.flush()
    return deleted_ids


@dataclass(frozen=True)
class DeckCounts:
    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)


def deck_counts(session: Session, deck_ids: Iterable[int]) -> dict[int, DeckCounts]:
    ids = list(deck_ids)
    counts: dict[int, dict[str, int]] = {deck_id: {} for deck_id in ids}
    if ids:
        rows = session.execute(
            select(DeckItem.deck_id, LexicalItem.status, func.count())
            .join(LexicalItem, LexicalItem.id == DeckItem.lexical_item_id)
            .where(DeckItem.deck_id.in_(ids))
            .group_by(DeckItem.deck_id, LexicalItem.status)
        )
        for deck_id, status, count in rows:
            counts[deck_id][ItemStatus(status).value] = count
    return {
        deck_id: DeckCounts(total=sum(by_status.values()), by_status=by_status)
        for deck_id, by_status in counts.items()
    }


def list_decks(session: Session) -> list[Deck]:
    return list(session.scalars(select(Deck).order_by(Deck.id)))


# --- Terms ---------------------------------------------------------------------------------------


def validate_term(term: str) -> str:
    """Cleaned term, or InvalidTerm when it cannot be stored (empty, too long, contains `|`)."""
    cleaned = clean_term(term)
    if not cleaned:
        raise InvalidTerm("The term is empty.")
    if len(cleaned) > MAX_TERM_CHARS:
        raise InvalidTerm(f"The term is longer than {MAX_TERM_CHARS} characters.")
    if "|" in cleaned:
        raise InvalidTerm("The term cannot contain '|'.")
    return cleaned


def term_problems(term: str, sentence: str | None) -> list[ImportProblem]:
    return check_term(clean_term(term), sentence, None)


def term_is_ambiguous(term: str, sentence: str | None) -> bool:
    return is_ambiguous(term_problems(term, sentence))


def create_item(
    session: Session,
    *,
    term: str,
    at: datetime,
    origin: ItemOrigin,
    sentence: str | None = None,
    item_type: ItemType | None = None,
    part_of_speech: str | None = None,
    deck_id: int | None = None,
    intake: ItemStatus | None = None,
) -> LexicalItem:
    """A new term in `draft`, then moved to `intake` (triage or queued) by the status service.

    `deck_id` is only recorded in `item.created`; link the term with `add_item_to_deck`.
    """
    at = as_utc(at)
    term = validate_term(term)
    normalized = normalize_term(term)
    item = LexicalItem(
        term=term,
        normalized_form=normalized,
        lemma=naive_lemma(normalized),
        item_type=item_type or guess_item_type(term),
        part_of_speech=part_of_speech,
        origin_sentence=(sentence or "").strip() or None,
        status=ItemStatus.DRAFT,
        status_changed_at=at,
        created_at=at,
        updated_at=at,
    )
    session.add(item)
    session.flush()
    record_event(
        session,
        ItemCreated(
            lexical_item_id=item.id, item_type=item.item_type, origin=origin, deck_id=deck_id
        ),
        occurred_at=at,
    )
    if intake is not None:
        set_item_status(session, item, intake, at, TransitionKind.MANUAL)
    return item


def get_item(session: Session, item_id: int) -> LexicalItem:
    item = session.get(LexicalItem, item_id)
    if item is None:
        raise ItemNotFound(f"There is no term {item_id}.")
    return item


def is_in_deck(session: Session, deck_id: int, item_id: int) -> bool:
    return bool(
        session.scalar(
            select(exists().where(DeckItem.deck_id == deck_id, DeckItem.lexical_item_id == item_id))
        )
    )


def add_item_to_deck(
    session: Session,
    deck: Deck,
    item: LexicalItem,
    at: datetime,
    *,
    context_sentence: str | None = None,
    position: int | None = None,
) -> DeckItem:
    """Link a term to a deck (D-013), at the end unless `position` is given. Raises
    ItemAlreadyInDeck."""
    at = as_utc(at)
    if is_in_deck(session, deck.id, item.id):
        raise ItemAlreadyInDeck(f"'{item.term}' is already in the deck '{deck.name}'.")
    if position is None:
        last = session.scalar(
            select(func.max(DeckItem.position)).where(DeckItem.deck_id == deck.id)
        )
        position = 0 if last is None else last + 1
    link = DeckItem(
        deck_id=deck.id,
        lexical_item_id=item.id,
        position=position,
        added_at=at,
        context_sentence=(context_sentence or "").strip() or None,
    )
    session.add(link)
    session.flush()
    record_event(session, DeckItemAdded(deck_id=deck.id, lexical_item_id=item.id), occurred_at=at)
    return link


ITEM_EDITABLE = ("term", "origin_sentence", "item_type", "part_of_speech", "notes")


def update_item(
    session: Session, item: LexicalItem, changes: dict[str, Any], at: datetime
) -> list[DuplicateCandidate]:
    """Edit a term's fields; a new spelling recomputes `normalized_form` and `lemma`.

    Returns the duplicates of the (new) term, for information: they never block the edit.
    """
    unknown = set(changes) - set(ITEM_EDITABLE)
    if unknown:
        raise ValueError(f"not editable here: {sorted(unknown)}")
    changes = dict(changes)
    if "term" in changes:
        changes["term"] = validate_term(changes["term"])
    for key in ("origin_sentence", "part_of_speech", "notes"):
        if key in changes and isinstance(changes[key], str):
            changes[key] = changes[key].strip() or None
    changed = [
        key for key in ITEM_EDITABLE if key in changes and getattr(item, key) != changes[key]
    ]
    for key in changed:
        setattr(item, key, changes[key])
    if "term" in changed:
        item.normalized_form = normalize_term(item.term)
        item.lemma = naive_lemma(item.normalized_form)
    if changed:
        item.updated_at = as_utc(at)
        record_event(
            session, ItemEdited(lexical_item_id=item.id, fields=changed), occurred_at=as_utc(at)
        )
        session.flush()
    return find_duplicates(session, item.term, exclude_id=item.id)


def delete_item(session: Session, item: LexicalItem, at: datetime) -> None:
    """Delete a term with no history. Raises ItemHasHistory (archive it instead)."""
    if item_has_history(session, item.id):
        raise ItemHasHistory(
            "This term has cards, reviews, productions or errors: archive it instead.",
            suggestion="archive",
        )
    record_event(session, ItemDeleted(lexical_item_id=item.id), occurred_at=as_utc(at))
    session.delete(item)
    session.flush()


# --- Search --------------------------------------------------------------------------------------

ItemSort = Literal["term", "created_at", "updated_at", "status", "status_changed_at", "id"]
# State of the current usage sheet (`edited` wins over the status of the sheet).
SheetFilter = Literal["none", "complete", "needs_completion", "edited"]


@dataclass(frozen=True)
class ItemQuery:
    q: str | None = None
    deck_id: int | None = None
    domain: str | None = None
    source_id: int | None = None
    item_type: ItemType | None = None
    statuses: tuple[ItemStatus, ...] = ()
    include_archived: bool = False
    sheet: SheetFilter | None = None
    sort: ItemSort = "created_at"
    descending: bool = False
    limit: int = 50
    offset: int = 0


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _in_deck_where(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    return (
        select(DeckItem.id)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(DeckItem.lexical_item_id == LexicalItem.id, *conditions)
        .exists()
    )


def _current_sheet_where(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    return exists().where(
        Enrichment.lexical_item_id == LexicalItem.id, Enrichment.is_current, *conditions
    )


def _sheet_matches(pattern: str) -> ColumnElement[bool]:
    """`q` in the current sheet: simple definition, meaning in context, French translations."""
    translations = (
        func.json_each(Enrichment.content, "$.translation_fr").table_valued("value").alias("tr")
    )
    in_translation = (
        select(literal(1))
        .select_from(translations)
        .where(func.lower(translations.c.value).like(pattern, escape="\\"))
        .exists()
    )
    return _current_sheet_where(
        or_(
            func.lower(func.json_extract(Enrichment.content, "$.definition_simple")).like(
                pattern, escape="\\"
            ),
            func.lower(func.json_extract(Enrichment.content, "$.meaning_in_context")).like(
                pattern, escape="\\"
            ),
            in_translation,
        )
    )


def _sheet_filter(sheet: SheetFilter) -> ColumnElement[bool]:
    if sheet == "none":
        return ~_current_sheet_where()
    if sheet == "edited":
        return _current_sheet_where(Enrichment.edited_by_user)
    return _current_sheet_where(
        ~Enrichment.edited_by_user, Enrichment.status == EnrichmentStatus(sheet)
    )


def _filtered(query: ItemQuery) -> Select[tuple[LexicalItem]]:
    stmt = select(LexicalItem)
    if query.q and query.q.strip():
        needle = query.q.strip()
        pattern = f"%{_escape_like(needle.casefold())}%"
        normalized_pattern = f"%{_escape_like(normalize_term(needle))}%"
        stmt = stmt.where(
            or_(
                func.lower(LexicalItem.term).like(pattern, escape="\\"),
                LexicalItem.normalized_form.like(normalized_pattern, escape="\\"),
                func.lower(LexicalItem.origin_sentence).like(pattern, escape="\\"),
                _sheet_matches(pattern),
            )
        )
    if query.sheet is not None:
        stmt = stmt.where(_sheet_filter(query.sheet))
    if query.deck_id is not None:
        stmt = stmt.where(_in_deck_where(DeckItem.deck_id == query.deck_id))
    if query.domain is not None:
        stmt = stmt.where(_in_deck_where(Deck.domain == query.domain))
    if query.source_id is not None:
        stmt = stmt.where(_in_deck_where(Deck.source_id == query.source_id))
    if query.item_type is not None:
        stmt = stmt.where(LexicalItem.item_type == query.item_type)
    if query.statuses:
        stmt = stmt.where(LexicalItem.status.in_(query.statuses))
    elif not query.include_archived:
        stmt = stmt.where(LexicalItem.status != ItemStatus.ARCHIVED)
    return stmt


def list_items(session: Session, query: ItemQuery) -> tuple[int, list[LexicalItem]]:
    """Matching terms (archived left out unless asked for) and the total before paging."""
    stmt = _filtered(query)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column: Any = {
        "term": func.lower(LexicalItem.term),
        "created_at": LexicalItem.created_at,
        "updated_at": LexicalItem.updated_at,
        "status": LexicalItem.status,
        "status_changed_at": LexicalItem.status_changed_at,
        "id": LexicalItem.id,
    }[query.sort]
    order = [column.desc(), LexicalItem.id.desc()] if query.descending else [column, LexicalItem.id]
    items = session.scalars(stmt.order_by(*order).limit(query.limit).offset(query.offset))
    return total, list(items)


# --- Quick add -----------------------------------------------------------------------------------


def quick_adds_deck(session: Session, at: datetime) -> Deck:
    """The deck that receives quick adds without a deck, created the first time."""
    deck = session.scalar(
        select(Deck).where(Deck.name == QUICK_ADDS_DECK, Deck.kind == DeckKind.CUSTOM).limit(1)
    )
    return deck or create_deck(session, name=QUICK_ADDS_DECK, at=at)


@dataclass(frozen=True)
class QuickAddResult:
    item: LexicalItem
    deck: Deck
    attached: bool  # an existing term was linked instead of creating one
    duplicates: list[DuplicateCandidate]


def quick_add(
    session: Session,
    *,
    term: str,
    at: datetime,
    sentence: str | None = None,
    deck_id: int | None = None,
    item_type: ItemType | None = None,
    on_duplicate: Literal["attach", "new"] | None = None,
    attach_to: int | None = None,
) -> QuickAddResult:
    """Add one term from the interface, queued for discovery (no triage: the user chose it).

    With a duplicate and no `on_duplicate`, raises DuplicateTerm with the candidates.
    """
    term = validate_term(term)
    deck = get_deck(session, deck_id) if deck_id is not None else quick_adds_deck(session, at)
    duplicates = find_duplicates(session, term)
    if duplicates and on_duplicate is None:
        raise DuplicateTerm(
            f"'{term}' may already be in the library.",
            candidates=[candidate.model_dump(mode="json") for candidate in duplicates],
        )
    if duplicates and on_duplicate == "attach":
        target_id = attach_to if attach_to is not None else duplicates[0].id
        if target_id not in {candidate.id for candidate in duplicates}:
            raise InvalidAttachTarget(f"Term {target_id} is not a duplicate of '{term}'.")
        item = get_item(session, target_id)
        add_item_to_deck(session, deck, item, at, context_sentence=sentence)
        return QuickAddResult(item=item, deck=deck, attached=True, duplicates=duplicates)
    item = create_item(
        session,
        term=term,
        at=at,
        origin=ItemOrigin.QUICK_ADD,
        sentence=sentence,
        item_type=item_type,
        deck_id=deck.id,
        intake=ItemStatus.QUEUED,
    )
    add_item_to_deck(session, deck, item, at)
    return QuickAddResult(item=item, deck=deck, attached=False, duplicates=duplicates)
