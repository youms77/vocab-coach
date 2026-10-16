"""Markdown import (module A): a preview that writes nothing, then a commit of the validated rows.

The preview is the parser's result plus what the library already holds (duplicates, terms already
in the target deck). The commit receives the rows *as the user validated them* and re-checks each
one with the same domain functions: the server never trusts the preview it sent. Everything is
written in the caller's transaction, so a failure leaves nothing (the caller rolls back).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.event_log import record_event
from app.db.models import Deck, DeckItem
from app.domain.enums import ItemStatus, ItemType
from app.domain.events import ImportCompleted, ItemOrigin
from app.domain.markdown_import import (
    ImportHeader,
    ImportProblem,
    ParsedRow,
    ProblemCode,
    Severity,
    check_term,
    clean_term,
    is_ambiguous,
    parse_import,
)
from app.domain.normalize import MatchKind, naive_lemma, normalize_term
from app.domain.study_day import as_utc
from app.services.library import (
    DuplicateCandidate,
    InvalidAttachTarget,
    LibraryError,
    add_item_to_deck,
    create_deck,
    create_item,
    create_source,
    find_duplicates_many,
    get_deck,
    get_item,
)

OnDuplicate = Literal["attach", "new", "skip"]
Intake = Literal["triage", "queued"]
_KEEPS_STATUS = (ItemStatus.KNOWN, ItemStatus.ARCHIVED)


class ImportRowRejected(LibraryError):
    """A row the user sent cannot be imported as it is (ambiguous and not confirmed, or invalid)."""

    status, code = 422, "row_rejected"


class DeckNameRequired(LibraryError):
    status, code = 422, "deck_name_required"


# --- Preview -------------------------------------------------------------------------------------


class PreviewRow(ParsedRow):
    duplicates: list[DuplicateCandidate]
    in_target_deck: bool
    # What the commit does by default with this row's duplicate (None: no duplicate).
    default_on_duplicate: OnDuplicate | None


class ImportPreview(BaseModel):
    header: ImportHeader
    rows: list[PreviewRow]
    problems: list[ImportProblem]
    rejected: bool
    lines_read: int
    importable: int
    ambiguous: int
    with_duplicates: int


def _default_action(candidates: list[DuplicateCandidate]) -> OnDuplicate | None:
    if not candidates:
        return None
    return "attach" if candidates[0].match == MatchKind.EXACT else "new"


def _library_problems(
    row: ParsedRow, candidates: list[DuplicateCandidate], in_deck: bool
) -> list[ImportProblem]:
    if in_deck:
        return [
            ImportProblem(
                line=row.line,
                severity=Severity.INFO,
                code=ProblemCode.ALREADY_IN_DECK,
                message="This term is already in the target deck; it will be skipped.",
            )
        ]
    if not candidates:
        return []
    first = candidates[0]
    problems = [
        ImportProblem(
            line=row.line,
            severity=Severity.INFO if first.match == MatchKind.EXACT else Severity.WARNING,
            code=(
                ProblemCode.DUPLICATE_EXACT
                if first.match == MatchKind.EXACT
                else ProblemCode.DUPLICATE_POSSIBLE
            ),
            message=(
                f"'{first.term}' is already in the library; it will be added to this deck."
                if first.match == MatchKind.EXACT
                else f"Possibly the same word as '{first.term}'; a new term will be created."
            ),
            suggestion={"item_id": first.id},
        )
    ]
    if first.match == MatchKind.EXACT and first.status in _KEEPS_STATUS:
        problems.append(
            ImportProblem(
                line=row.line,
                severity=Severity.INFO,
                code=ProblemCode.EXISTING_STATUS_KEPT,
                message=f"The existing term is '{first.status.value}'; its status will not change.",
                suggestion={"item_id": first.id, "status": first.status.value},
            )
        )
    return problems


def _items_in_deck(session: Session, deck_id: int | None) -> set[int]:
    if deck_id is None:
        return set()
    return set(session.scalars(select(DeckItem.lexical_item_id).where(DeckItem.deck_id == deck_id)))


def preview(
    session: Session, text: str, today: date, *, deck_id: int | None = None
) -> ImportPreview:
    """Parse `text` and look up the library. Reads only; `deck_id` is the target deck, if known."""
    if deck_id is not None:
        get_deck(session, deck_id)
    parsed = parse_import(text, today)
    forms = [(row.normalized_form, naive_lemma(row.normalized_form)) for row in parsed.rows]
    all_candidates = find_duplicates_many(session, forms)
    in_deck_ids = _items_in_deck(session, deck_id)
    rows: list[PreviewRow] = []
    for row, candidates in zip(parsed.rows, all_candidates, strict=True):
        in_deck = any(c.id in in_deck_ids and c.match == MatchKind.EXACT for c in candidates)
        rows.append(
            PreviewRow(
                **row.model_dump(exclude={"problems"}),
                problems=[*row.problems, *_library_problems(row, candidates, in_deck)],
                duplicates=candidates,
                in_target_deck=in_deck,
                default_on_duplicate=_default_action(candidates),
            )
        )
    return ImportPreview(
        header=parsed.header,
        rows=rows,
        problems=parsed.problems,
        rejected=parsed.rejected,
        lines_read=len(rows),
        importable=sum(1 for row in rows if row.include and not row.in_target_deck),
        ambiguous=sum(1 for row in rows if row.ambiguous),
        with_duplicates=sum(1 for row in rows if row.duplicates),
    )


# --- Commit --------------------------------------------------------------------------------------


class CommitRow(BaseModel):
    """One row as the user validated it in the preview."""

    model_config = ConfigDict(extra="forbid")

    line: int | None = None
    term: str = Field(max_length=2000)
    sentence: str | None = Field(default=None, max_length=5000)
    item_type: ItemType | None = None
    include: bool = True
    # The user saw the ambiguity (definition, sentence-like term) and imports the row anyway.
    confirmed: bool = False
    on_duplicate: OnDuplicate | None = None
    attach_to: int | None = None


class ImportTarget(BaseModel):
    """An existing deck, or a new one (named after the header unless `new_deck_name` is given)."""

    model_config = ConfigDict(extra="forbid")

    deck_id: int | None = None
    new_deck_name: str | None = Field(default=None, max_length=300)


class ImportSummary(BaseModel):
    deck_id: int
    created_deck: bool
    lines_read: int
    imported: int
    attached: int
    skipped: int
    ambiguous: int
    item_ids: list[int]


# Ambiguities a user may confirm. An empty or over-long term, or a stray `|`, must be corrected.
_CONFIRMABLE = {ProblemCode.LOOKS_LIKE_DEFINITION, ProblemCode.LOOKS_LIKE_SENTENCE}


def _check_rows(rows: list[CommitRow]) -> list[tuple[CommitRow, str, bool]]:
    """(row, cleaned term, was ambiguous) for every row; raises ImportRowRejected."""
    checked = []
    for index, row in enumerate(rows):
        term = clean_term(row.term)
        sentence = (row.sentence or "").strip() or None
        problems = check_term(term, sentence, row.line)
        ambiguous = is_ambiguous(problems)
        if row.include and ambiguous:
            codes = {problem.code for problem in problems if problem.severity == Severity.AMBIGUOUS}
            if not row.confirmed or not codes <= _CONFIRMABLE:
                raise ImportRowRejected(
                    "This row must be corrected or confirmed before it can be imported.",
                    row=index,
                    line=row.line,
                    problems=sorted(code.value for code in codes),
                )
        checked.append((row, term, ambiguous))
    return checked


def _target_deck(
    session: Session, header: ImportHeader, target: ImportTarget, at: datetime
) -> tuple[Deck, bool]:
    if target.deck_id is not None:
        return get_deck(session, target.deck_id), False
    name = (target.new_deck_name or header.deck or "").strip()
    if not name:
        raise DeckNameRequired("Give the new deck a name (or a `deck:` line in the header).")
    source_id = None
    description = None
    if header.source:
        source = create_source(
            session, title=header.source, at=at, domain=header.domain, context=header.context
        )
        source_id = source.id
    else:
        description = header.context
    deck = create_deck(
        session,
        name=name,
        at=at,
        description=description,
        domain=header.domain,
        source_id=source_id,
        deadline=header.deadline,
    )
    return deck, True


def commit(
    session: Session,
    *,
    header: ImportHeader,
    rows: list[CommitRow],
    target: ImportTarget,
    intake: Intake,
    at: datetime,
) -> ImportSummary:
    """Import the validated rows into the target deck, all or nothing (the caller commits).

    Defaults: an exact duplicate is attached, a possible one creates a new term; a term already
    in the target deck is skipped; an attached `known` or `archived` term keeps its status.
    """
    at = as_utc(at)
    checked = _check_rows(rows)
    deck, created = _target_deck(session, header, target, at)
    status = ItemStatus.TRIAGE if intake == "triage" else ItemStatus.QUEUED

    wanted = [(row, term) for row, term, _ in checked if row.include]
    forms = [(normalize_term(term), naive_lemma(normalize_term(term))) for _, term in wanted]
    all_candidates = find_duplicates_many(session, forms)
    in_deck = _items_in_deck(session, deck.id)

    imported = attached = 0
    item_ids: list[int] = []
    seen: set[str] = set()
    for (row, term), (normalized, _), candidates in zip(wanted, forms, all_candidates, strict=True):
        if normalized in seen:
            continue  # the same term twice in the rows: the first one wins
        seen.add(normalized)
        exact_in_deck = [c for c in candidates if c.match == MatchKind.EXACT and c.id in in_deck]
        action = row.on_duplicate or _default_action(candidates) or "new"
        if action == "skip" or (exact_in_deck and action != "new"):
            continue
        sentence = (row.sentence or "").strip() or None
        if action == "attach" and candidates:
            target_id = row.attach_to if row.attach_to is not None else candidates[0].id
            if target_id not in {candidate.id for candidate in candidates}:
                raise InvalidAttachTarget(
                    f"Term {target_id} is not a duplicate of '{term}'.", line=row.line
                )
            if target_id in in_deck:
                continue
            item = get_item(session, target_id)
            add_item_to_deck(session, deck, item, at, context_sentence=sentence)
            in_deck.add(item.id)
            attached += 1
        else:
            item = create_item(
                session,
                term=term,
                at=at,
                origin=ItemOrigin.IMPORT,
                sentence=sentence,
                item_type=row.item_type,
                deck_id=deck.id,
                intake=status,
            )
            add_item_to_deck(session, deck, item, at)
            in_deck.add(item.id)
            imported += 1
        item_ids.append(item.id)

    summary = ImportSummary(
        deck_id=deck.id,
        created_deck=created,
        lines_read=len(rows),
        imported=imported,
        attached=attached,
        skipped=len(rows) - imported - attached,
        ambiguous=sum(1 for _, _, ambiguous in checked if ambiguous),
        item_ids=item_ids,
    )
    record_event(
        session,
        ImportCompleted(
            deck_id=deck.id,
            lines_read=summary.lines_read,
            imported=imported,
            attached=attached,
            skipped=summary.skipped,
            ambiguous=summary.ambiguous,
        ),
        occurred_at=at,
    )
    session.flush()
    return summary


def default_rows(preview_result: ImportPreview) -> list[CommitRow]:
    """The rows the CLI imports with `--commit`: clear rows only, default duplicate choices."""
    return [
        CommitRow(
            line=row.line,
            term=row.term,
            sentence=row.sentence,
            item_type=row.item_type,
            include=row.include,
        )
        for row in preview_result.rows
    ]
