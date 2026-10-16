"""Import service (app/services/importing.py): read-only preview and atomic commit."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.models import Deck, DeckItem, EventLog, LexicalItem, Source
from app.domain.enums import ItemStatus, ItemType
from app.domain.events import ItemOrigin
from app.domain.markdown_import import ImportHeader, ProblemCode, parse_import
from app.services import importing, library
from app.services.importing import CommitRow, ImportTarget
from tests.factories import NOW
from tests.library_support import count, events, item_by_term

TODAY = date(2026, 10, 16)

TEXT = """---
deck: Causal inference reading
domain: econometrics
source: "Angrist & Pischke, ch. 3"
context: "Reading for my report"
deadline: 2026-11-20
---
- heteroskedasticity
- to account for | We account for regional fixed effects.
- bias = biais
- shed light on
"""


def existing(session: Session, term: str, status: ItemStatus = ItemStatus.QUEUED) -> LexicalItem:
    item = library.create_item(session, term=term, at=NOW, origin=ItemOrigin.IMPORT, intake=None)
    item.status = status
    session.flush()
    return item


def rows_of(text: str) -> tuple[ImportHeader, list[CommitRow]]:
    parsed = parse_import(text, TODAY)
    rows = [
        CommitRow(line=r.line, term=r.term, sentence=r.sentence, include=r.include)
        for r in parsed.rows
    ]
    return parsed.header, rows


def snapshot(session: Session) -> tuple[int, ...]:
    return tuple(count(session, model) for model in (Deck, Source, LexicalItem, DeckItem, EventLog))


# --- Preview -------------------------------------------------------------------------------------


def test_preview_writes_nothing_and_reports_duplicates(session: Session) -> None:
    known = existing(session, "Heteroskedasticity", ItemStatus.KNOWN)
    possible = existing(session, "result")
    session.commit()
    before = snapshot(session)
    result = importing.preview(session, TEXT + "- results\n", TODAY)
    assert snapshot(session) == before and not session.new and not session.dirty
    rows = {row.term: row for row in result.rows}
    hetero = rows["heteroskedasticity"]
    assert [d.id for d in hetero.duplicates] == [known.id]
    assert hetero.default_on_duplicate == "attach"
    assert [p.code for p in hetero.problems] == [
        ProblemCode.DUPLICATE_EXACT,
        ProblemCode.EXISTING_STATUS_KEPT,
    ]
    assert rows["results"].default_on_duplicate == "new"
    assert [d.id for d in rows["results"].duplicates] == [possible.id]
    assert [p.code for p in rows["results"].problems] == [ProblemCode.DUPLICATE_POSSIBLE]
    assert rows["bias = biais"].ambiguous
    assert (result.lines_read, result.importable, result.ambiguous, result.with_duplicates) == (
        5,
        4,
        1,
        2,
    )
    assert result.header.deck == "Causal inference reading"


def test_preview_flags_terms_already_in_the_target_deck(session: Session) -> None:
    deck = library.create_deck(session, name="Reading", at=NOW)
    item = existing(session, "shed light on")
    library.add_item_to_deck(session, deck, item, NOW)
    result = importing.preview(session, "- Shed light on\n- bias\n", TODAY, deck_id=deck.id)
    assert [row.in_target_deck for row in result.rows] == [True, False]
    assert [p.code for p in result.rows[0].problems] == [ProblemCode.ALREADY_IN_DECK]
    assert result.importable == 1
    with pytest.raises(library.DeckNotFound):
        importing.preview(session, "- x", TODAY, deck_id=999)


def test_preview_of_a_too_large_file(session: Session) -> None:
    result = importing.preview(session, "- x\n" * 1001, TODAY)
    assert result.rejected and result.rows == []


# --- Commit --------------------------------------------------------------------------------------


def commit(session: Session, text: str = TEXT, **kwargs: object) -> importing.ImportSummary:
    header, rows = rows_of(text)
    options: dict[str, object] = {
        "header": header,
        "rows": rows,
        "target": ImportTarget(),
        "intake": "triage",
        "at": NOW,
    }
    options.update(kwargs)
    return importing.commit(session, **options)  # type: ignore[arg-type]


def test_commit_new_deck_from_the_header(session: Session) -> None:
    summary = commit(session)
    deck = session.get(Deck, summary.deck_id)
    assert deck is not None and summary.created_deck
    assert (deck.name, deck.domain, deck.deadline) == (
        "Causal inference reading",
        "econometrics",
        date(2026, 11, 20),
    )
    assert deck.description is None
    source = session.get(Source, deck.source_id)
    assert source is not None
    assert (source.title, source.context, source.domain) == (
        "Angrist & Pischke, ch. 3",
        "Reading for my report",
        "econometrics",
    )
    assert (summary.lines_read, summary.imported, summary.attached, summary.skipped) == (4, 3, 0, 1)
    assert summary.ambiguous == 1
    account = item_by_term(session, "to account for")
    assert account.status == ItemStatus.TRIAGE
    assert account.origin_sentence == "We account for regional fixed effects."
    assert account.item_type == ItemType.COLLOCATION
    assert events(session, "import.completed") == [
        {
            "deck_id": deck.id,
            "lines_read": 4,
            "imported": 3,
            "attached": 0,
            "skipped": 1,
            "ambiguous": 1,
        }
    ]
    assert {e["origin"] for e in events(session, "item.created")} == {"import"}


def test_context_goes_to_the_deck_without_a_source(session: Session) -> None:
    summary = commit(session, "---\ndeck: Talk\ncontext: Job interview\n---\n- small talk\n")
    deck = session.get(Deck, summary.deck_id)
    assert deck is not None and deck.description == "Job interview" and deck.source_id is None
    assert count(session, Source) == 0


def test_queued_intake(session: Session) -> None:
    commit(session, intake="queued")
    assert item_by_term(session, "heteroskedasticity").status == ItemStatus.QUEUED


def test_new_deck_needs_a_name(session: Session) -> None:
    with pytest.raises(importing.DeckNameRequired):
        commit(session, "- bias\n")
    summary = commit(session, "- bias\n", target=ImportTarget(new_deck_name="Mine"))
    assert session.get(Deck, summary.deck_id).name == "Mine"  # type: ignore[union-attr]


def test_existing_deck_ignores_the_header(session: Session) -> None:
    deck = library.create_deck(session, name="Mine", at=NOW)
    summary = commit(session, target=ImportTarget(deck_id=deck.id))
    assert summary.deck_id == deck.id and not summary.created_deck
    assert deck.name == "Mine" and deck.domain is None and count(session, Source) == 0
    with pytest.raises(library.DeckNotFound):
        commit(session, target=ImportTarget(deck_id=999))


def test_ambiguous_row_needs_confirmation(session: Session) -> None:
    header, rows = rows_of(TEXT)
    rows[2] = rows[2].model_copy(update={"include": True})
    with pytest.raises(importing.ImportRowRejected) as caught:
        importing.commit(
            session, header=header, rows=rows, target=ImportTarget(), intake="triage", at=NOW
        )
    assert caught.value.extra == {"row": 2, "line": 10, "problems": ["looks_like_definition"]}
    rows[2] = rows[2].model_copy(update={"confirmed": True})
    summary = importing.commit(
        session, header=header, rows=rows, target=ImportTarget(), intake="triage", at=NOW
    )
    assert summary.imported == 4 and summary.ambiguous == 1
    item_by_term(session, "bias = biais")


def test_corrected_row_is_accepted(session: Session) -> None:
    header, rows = rows_of(TEXT)
    rows[2] = CommitRow(line=10, term="bias", sentence=None)
    summary = importing.commit(
        session, header=header, rows=rows, target=ImportTarget(), intake="triage", at=NOW
    )
    assert summary.imported == 4 and summary.ambiguous == 0


@pytest.mark.parametrize("term", ["", "a | b", "x" * 301])
def test_invalid_rows_cannot_be_confirmed(session: Session, term: str) -> None:
    rows = [CommitRow(term=term, confirmed=True)]
    with pytest.raises(importing.ImportRowRejected):
        importing.commit(
            session,
            header=ImportHeader(deck="D"),
            rows=rows,
            target=ImportTarget(),
            intake="triage",
            at=NOW,
        )


def test_attach_new_and_skip(session: Session) -> None:
    other = library.create_deck(session, name="Earlier", at=NOW)
    exact = existing(session, "Heteroskedasticity", ItemStatus.ARCHIVED)
    library.add_item_to_deck(session, other, exact, NOW)
    possible = existing(session, "results", ItemStatus.LEARNING)
    skipped = existing(session, "variance")
    rows = [
        CommitRow(term="heteroskedasticity", sentence="Robust to heteroskedasticity."),
        CommitRow(term="result"),  # possible duplicate: default `new`
        CommitRow(term="variance", on_duplicate="skip"),
        CommitRow(term="heteroskedasticity!", on_duplicate="new"),
    ]
    summary = importing.commit(
        session,
        header=ImportHeader(deck="New"),
        rows=rows,
        target=ImportTarget(),
        intake="queued",
        at=NOW,
    )
    assert (summary.imported, summary.attached, summary.skipped) == (1, 1, 2)
    assert exact.status == ItemStatus.ARCHIVED  # status untouched
    link = session.query(DeckItem).filter_by(deck_id=summary.deck_id, lexical_item_id=exact.id)
    assert link.one().context_sentence == "Robust to heteroskedasticity."
    assert possible.id not in summary.item_ids and skipped.id not in summary.item_ids
    assert item_by_term(session, "result").status == ItemStatus.QUEUED


def test_explicit_attach_to_a_possible_duplicate(session: Session) -> None:
    possible = existing(session, "results")
    rows = [CommitRow(term="result", on_duplicate="attach", attach_to=possible.id)]
    summary = importing.commit(
        session,
        header=ImportHeader(deck="D"),
        rows=rows,
        target=ImportTarget(),
        intake="queued",
        at=NOW,
    )
    assert summary.attached == 1 and summary.item_ids == [possible.id]
    with pytest.raises(library.InvalidAttachTarget):
        importing.commit(
            session,
            header=ImportHeader(deck="E"),
            rows=[CommitRow(term="result", on_duplicate="attach", attach_to=12345)],
            target=ImportTarget(),
            intake="queued",
            at=NOW,
        )


def test_term_already_in_the_target_deck_is_skipped(session: Session) -> None:
    deck = library.create_deck(session, name="Reading", at=NOW)
    item = existing(session, "shed light on")
    library.add_item_to_deck(session, deck, item, NOW)
    summary = commit(
        session, "- Shed light on\n- bias\n- bias\n", target=ImportTarget(deck_id=deck.id)
    )
    assert (summary.imported, summary.attached, summary.skipped) == (1, 0, 2)
    assert count(session, LexicalItem) == 2


def test_import_is_atomic(engine, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}
    real = importing.add_item_to_deck

    def failing(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("injected failure")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importing, "add_item_to_deck", failing)
    with Session(engine) as session:
        before = snapshot(session)
        with pytest.raises(RuntimeError):
            commit(session)
        session.rollback()
    with Session(engine) as session:
        assert snapshot(session) == before
        assert calls["n"] == 3


def test_default_rows_keep_only_clear_lines(session: Session) -> None:
    rows = importing.default_rows(importing.preview(session, TEXT, TODAY))
    assert [row.include for row in rows] == [True, True, False, True]
    assert all(row.on_duplicate is None for row in rows)
