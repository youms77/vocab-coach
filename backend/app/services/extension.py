"""List extension (module A): the AI suggests 10 to 30 terms related to a deck.

The call is made with no session open (D-038); the suggestions are then written in one short
transaction: exact duplicates of the library and repeats inside the answer are dropped, possible
duplicates are kept and reported, and every new term waits for the intake triage (`triage`, origin
`extension`) in the deck, with its example sentence as the deck's context sentence. Only the terms
the user retains stay in the deck: a suggestion triaged as known leaves it (`triage.py`, D-084).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.list_extension import (
    DEFAULT_COUNT,
    MAX_COUNT,
    MIN_COUNT,
    ListExtensionOutput,
    Suggestion,
)
from app.ai.tasks import EXTENSION_TOKENS_PER_SUGGESTION
from app.ai.types import AiStatus, UnavailableReason
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import DeckItem, LexicalItem, Source
from app.domain.enums import ItemStatus
from app.domain.events import ItemOrigin, ListExtensionGenerated
from app.domain.normalize import MatchKind, naive_lemma, normalize_term
from app.services.library import (
    DuplicateCandidate,
    InvalidTerm,
    LibraryError,
    add_item_to_deck,
    create_item,
    find_duplicates_many,
    get_deck,
    validate_term,
)

TASK = "list_extension"
MAX_DECK_TERMS = 80
TERMS_MAX_CHARS = 2400
DECK_FIELD_MAX = 300

SessionFactory = Callable[[], Session]


class NotEnoughContext(LibraryError):
    status, code = 422, "not_enough_context"


class PossibleDuplicate(BaseModel):
    item_id: int  # the new term
    candidates: list[DuplicateCandidate]


class ExtensionReport(BaseModel):
    status: Literal["ok", "incomplete", "unavailable"]
    reason: UnavailableReason | None = None
    created: list[int] = []  # new term ids, waiting for triage
    suggested: int = 0
    dropped_existing: int = 0
    dropped_in_batch: int = 0
    possible_duplicates: list[PossibleDuplicate] = []


def _cut(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _inputs(session: Session, deck_id: int, count: int) -> dict[str, str]:
    """Prompt inputs (raises DeckNotFound, NotEnoughContext)."""
    deck = get_deck(session, deck_id)
    source = session.get(Source, deck.source_id) if deck.source_id is not None else None
    terms = list(
        session.scalars(
            select(LexicalItem.term)
            .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
            .where(DeckItem.deck_id == deck.id)
            .order_by(DeckItem.position, LexicalItem.id)
            .limit(MAX_DECK_TERMS)
        )
    )
    context = deck.description or (source.context if source is not None else None)
    if not terms and not (deck.domain or "").strip() and not (context or "").strip():
        raise NotEnoughContext(
            "Add a few terms, a domain or a context to this deck first: there is nothing to "
            "extend from."
        )
    lines, used = [], 0
    for term in terms:
        term = _cut(term, 100)
        if used + len(term) + 1 > TERMS_MAX_CHARS:
            break
        lines.append(term)
        used += len(term) + 1
    deck_text = "\n".join(
        [
            f"name: {_cut(deck.name, DECK_FIELD_MAX)}",
            f"domain: {_cut(deck.domain, DECK_FIELD_MAX)}",
            f"source: {_cut(source.title if source else None, DECK_FIELD_MAX)}",
            f"context: {_cut(context, DECK_FIELD_MAX)}",
        ]
    )
    return {"deck": deck_text, "terms": "\n".join(lines) or "(none yet)", "count": str(count)}


def extend_deck(
    session_factory: SessionFactory,
    gateway: Gateway,
    deck_id: int,
    *,
    count: int = DEFAULT_COUNT,
    clock: Callable[[], datetime] = utcnow,
) -> ExtensionReport:
    """Ask for `count` suggestions and store the new ones in triage. Raises DeckNotFound,
    NotEnoughContext; an AI failure is a report (`unavailable` / `incomplete`), not an error."""
    if not MIN_COUNT <= count <= MAX_COUNT:
        raise ValueError(f"count must be between {MIN_COUNT} and {MAX_COUNT}")
    with session_factory() as session:
        inputs = _inputs(session, deck_id, count)
        session.rollback()
    result = gateway.generate_json(
        TASK,
        inputs,
        ListExtensionOutput,
        max_output_tokens=EXTENSION_TOKENS_PER_SUGGESTION * (count + 5),
    )
    if result.status is AiStatus.INCOMPLETE:
        return ExtensionReport(status="incomplete")
    if not result.ok or result.data is None:
        return ExtensionReport(status="unavailable", reason=result.reason)
    with session_factory() as session:
        report = _store(session, deck_id, count, result.data.suggestions, clock())
        session.commit()
    return report


def _store(
    session: Session, deck_id: int, count: int, suggestions: list[Suggestion], at: datetime
) -> ExtensionReport:
    deck = get_deck(session, deck_id)  # it may have been deleted during the call
    kept: list[tuple[Suggestion, str]] = []
    seen: set[str] = set()
    dropped_in_batch = max(0, len(suggestions) - count)
    for suggestion in suggestions[:count]:
        try:
            term = validate_term(suggestion.term)
        except InvalidTerm:
            dropped_in_batch += 1
            continue
        normalized = normalize_term(term)
        if not normalized or normalized in seen:
            dropped_in_batch += 1
            continue
        seen.add(normalized)
        kept.append((suggestion.model_copy(update={"term": term}), normalized))

    matches = find_duplicates_many(session, [(n, naive_lemma(n)) for _, n in kept])
    created: list[int] = []
    possible: list[PossibleDuplicate] = []
    dropped_existing = 0
    for (suggestion, _), candidates in zip(kept, matches, strict=True):
        if any(c.match == MatchKind.EXACT for c in candidates):
            dropped_existing += 1
            continue
        item = create_item(
            session,
            term=suggestion.term,
            at=at,
            origin=ItemOrigin.EXTENSION,
            item_type=suggestion.item_type,
            deck_id=deck.id,
            intake=ItemStatus.TRIAGE,
        )
        add_item_to_deck(session, deck, item, at, context_sentence=suggestion.example_sentence)
        created.append(item.id)
        if candidates:
            possible.append(PossibleDuplicate(item_id=item.id, candidates=candidates))
    record_event(
        session,
        ListExtensionGenerated(
            deck_id=deck.id,
            requested=count,
            suggested=len(suggestions),
            created=len(created),
            dropped_existing=dropped_existing,
            dropped_in_batch=dropped_in_batch,
        ),
        occurred_at=at,
    )
    session.flush()
    return ExtensionReport(
        status="ok",
        created=created,
        suggested=len(suggestions),
        dropped_existing=dropped_existing,
        dropped_in_batch=dropped_in_batch,
        possible_duplicates=possible,
    )
