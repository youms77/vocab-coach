"""Module H services: start (idempotent), open units, duplicates, computed state, missing lists."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CurriculumUnit, Deck, DeckItem, LexicalItem, Source
from app.domain.enums import DeckKind, DeckStatus, ItemStatus
from app.domain.events import ItemOrigin, TriageDecision
from app.services import curriculum
from app.services.library import create_item
from app.services.triage import apply_triage
from tests.library_support import count, events

AT = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
CONTENT = Path(__file__).resolve().parents[2] / "content"


def terms_of(session: Session, deck_id: int) -> list[str]:
    return list(
        session.scalars(
            select(LexicalItem.term)
            .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
            .where(DeckItem.deck_id == deck_id)
            .order_by(DeckItem.position)
        )
    )


def test_list_tracks_before_anything_is_started(session: Session) -> None:
    tracks = {t.code: t for t in curriculum.list_tracks(session)}
    assert set(tracks) == {"general_everyday", "academic", "speaking_scenarios"}
    assert (tracks["general_everyday"].unit_count, tracks["academic"].unit_count) == (113, 39)
    assert tracks["speaking_scenarios"].unit_count == 16
    assert all(t.available and not t.started for t in tracks.values())
    assert count(session, Deck) == 0 and count(session, CurriculumUnit) == 0


def test_start_is_idempotent_and_makes_a_source_and_a_deck(session: Session) -> None:
    first = curriculum.start_track(session, "general_everyday", AT)
    again = curriculum.start_track(session, "general_everyday", AT)
    assert first.created and not again.created
    assert first.track.deck_id == again.track.deck_id and first.track.started
    deck = session.get(Deck, first.track.deck_id)
    assert deck is not None
    assert (deck.kind, deck.status) == (DeckKind.CURRICULUM, DeckStatus.QUEUED)
    source = session.get(Source, deck.source_id)
    assert source is not None
    assert source.reference == "curriculum:general_everyday"
    assert source.title == "New General Service List 1.2"
    assert count(session, Deck) == 1 and count(session, Source) == 1
    assert [e["created"] for e in events(session, "curriculum.track_started")] == [True, False]
    assert events(session, "import.completed") == []


def test_start_again_after_the_deck_was_deleted_makes_a_new_one(session: Session) -> None:
    first = curriculum.start_track(session, "academic", AT)
    session.delete(session.get(Deck, first.track.deck_id))
    session.flush()
    second = curriculum.start_track(session, "academic", AT)
    assert second.created and second.track.started  # (SQLite may reuse the deleted id)
    assert count(session, Deck) == 1 and count(session, Source) == 2


def test_open_requires_a_started_track(session: Session) -> None:
    with pytest.raises(curriculum.TrackNotStarted) as caught:
        curriculum.open_unit(session, "general_everyday", 1, AT)
    assert caught.value.extra["track"] == "general_everyday"
    with pytest.raises(curriculum.TrackNotFound):
        curriculum.open_unit(session, "nope", 1, AT)
    curriculum.start_track(session, "general_everyday", AT)
    with pytest.raises(curriculum.UnitNotFound):
        curriculum.open_unit(session, "general_everyday", 114, AT)
    with pytest.raises(curriculum.UnitNotFound):
        curriculum.open_unit(session, "general_everyday", 0, AT)


def test_open_unit_puts_the_words_in_triage(session: Session) -> None:
    started = curriculum.start_track(session, "general_everyday", AT)
    result = curriculum.open_unit(session, "general_everyday", 1, AT)
    assert result.created
    assert (result.imported, result.attached, result.skipped) == (25, 0, 0)
    unit = result.unit
    assert (unit.code, unit.title, unit.number, unit.state) == (
        "ngsl_001",
        "Words 1–25",
        1,
        "opened",
    )
    assert terms_of(session, started.track.deck_id)[:3] == ["the", "be", "and"]
    assert {t.status for t in unit.terms} == {ItemStatus.TRIAGE}
    row = session.get(CurriculumUnit, unit.id)
    assert row is not None and row.content is not None
    assert row.content["format"] == "wordlist-unit-1"
    assert (row.content["first_rank"], row.content["last_rank"]) == (1, 25)
    assert row.content["source"] == "ngsl" and row.content["source_version"] == "1.2"
    assert row.content["item_ids"] == [t.item_id for t in unit.terms]
    assert row.deck_id == started.track.deck_id
    opened = events(session, "curriculum.unit_opened")
    assert len(opened) == 1 and opened[0]["unit_code"] == "ngsl_001"
    assert events(session, "import.completed") == []
    assert {e["origin"] for e in events(session, "item.created")} == {ItemOrigin.CURRICULUM.value}


def test_reopening_creates_nothing(session: Session) -> None:
    curriculum.start_track(session, "general_everyday", AT)
    first = curriculum.open_unit(session, "general_everyday", 2, AT)
    items, units, logged = (
        count(session, LexicalItem),
        count(session, CurriculumUnit),
        len(events(session, "curriculum.unit_opened")),
    )
    again = curriculum.open_unit(session, "general_everyday", 2, AT)
    assert not again.created and again.unit.id == first.unit.id
    assert count(session, LexicalItem) == items and count(session, CurriculumUnit) == units
    assert len(events(session, "curriculum.unit_opened")) == logged


def test_exact_and_possible_duplicates(session: Session) -> None:
    known = create_item(session, term="the", at=AT, origin=ItemOrigin.QUICK_ADD)
    known.status = ItemStatus.KNOWN
    similar = create_item(session, term="says", at=AT, origin=ItemOrigin.QUICK_ADD)
    session.flush()
    curriculum.start_track(session, "general_everyday", AT)
    result = curriculum.open_unit(session, "general_everyday", 1, AT)
    assert result.attached == 1  # "the" is attached, not created again
    assert result.imported == 24 and result.skipped == 0
    assert session.scalars(select(LexicalItem).where(LexicalItem.term == "the")).all() == [known]
    assert known.status == ItemStatus.KNOWN  # status kept
    assert known.id in [t.item_id for t in result.unit.terms]
    # "say" is a possible duplicate of "says": a new term is created, "says" is left alone
    assert similar.id not in [t.item_id for t in result.unit.terms]
    assert count(session, LexicalItem) == 2 + 24
    assert result.unit.state == "opened"  # 24 terms still wait


def test_unit_state_is_computed_from_the_terms(session: Session) -> None:
    curriculum.start_track(session, "general_everyday", AT)
    unit = curriculum.open_unit(session, "general_everyday", 1, AT).unit
    detail = curriculum.track_detail(session, "general_everyday", limit=3)
    assert [u.state for u in detail.units] == ["opened", "not_opened", "not_opened"]
    assert detail.track.opened_units == 1 and detail.track.triaged_units == 0
    apply_triage(session, [(t.item_id, TriageDecision.LEARN) for t in unit.terms[:-1]], AT)
    assert curriculum.get_unit(session, unit.id).state == "opened"
    apply_triage(session, [(unit.terms[-1].item_id, TriageDecision.KNOWN)], AT)
    assert curriculum.get_unit(session, unit.id).state == "triaged"
    detail = curriculum.track_detail(session, "general_everyday", limit=3)
    assert detail.units[0].state == "triaged" and detail.track.triaged_units == 1


def test_track_detail_pages_and_the_last_short_unit(session: Session) -> None:
    detail = curriculum.track_detail(session, "general_everyday", limit=25, offset=100)
    assert detail.total_units == 113 and [u.number for u in detail.units][-1] == 113
    last = detail.units[-1]
    assert (last.first_rank, last.last_rank, last.word_count) == (2801, 2809, 9)
    assert curriculum.track_detail(session, "general_everyday", offset=500).units == []
    nawl = curriculum.track_detail(session, "academic", limit=2)
    assert [u.title for u in nawl.units] == ["Words 1–25", "Words 26–50"]


def test_scenario_track_lists_pending_units_and_cannot_be_opened(session: Session) -> None:
    detail = curriculum.track_detail(session, "speaking_scenarios", limit=50)
    assert len(detail.units) == 16
    assert {u.content_status.value for u in detail.units} == {"pending"}
    assert {u.state for u in detail.units} == {"not_opened"}
    assert detail.units[0].title_fr
    started = curriculum.start_track(session, "speaking_scenarios", AT)
    assert started.created and started.track.started and started.track.deck_id is None
    assert not curriculum.start_track(session, "speaking_scenarios", AT).created
    with pytest.raises(curriculum.NotAWordlistTrack):
        curriculum.open_unit(session, "speaking_scenarios", 1, AT)


def test_missing_wordlist(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(CONTENT / "curriculum.yaml", tmp_path / "curriculum.yaml")
    (tmp_path / "wordlists").mkdir()
    shutil.copy(
        CONTENT / "wordlists" / "NGSL_12_stats.csv", tmp_path / "wordlists" / "NGSL_12_stats.csv"
    )
    monkeypatch.setattr(curriculum, "CONTENT_DIR", tmp_path)
    tracks = {t.code: t for t in curriculum.list_tracks(session)}
    assert tracks["general_everyday"].available and tracks["general_everyday"].reason is None
    assert not tracks["academic"].available and tracks["academic"].reason == "wordlist_missing"
    assert tracks["speaking_scenarios"].available
    with pytest.raises(curriculum.WordlistMissing):
        curriculum.start_track(session, "academic", AT)
    assert count(session, Deck) == 0  # nothing half-made
    curriculum.start_track(session, "general_everyday", AT)
    (tmp_path / "wordlists" / "NGSL_12_stats.csv").unlink()
    with pytest.raises(curriculum.WordlistMissing):
        curriculum.open_unit(session, "general_everyday", 1, AT)


def test_syllabus_unavailable(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curriculum, "CONTENT_DIR", tmp_path)
    with pytest.raises(curriculum.SyllabusUnavailable):
        curriculum.list_tracks(session)
