"""General English tracks (module H, M8.a1): the syllabus, word-list tracks and their units.

Nothing is stored until the user acts. Starting a word-list track creates its `source` row
(reference `curriculum:<code>`) and a `curriculum` deck at the end of the queue (D-241: no new
column, the deck is found again through the source). Opening a unit creates its `curriculum_unit`
row and puts its terms in intake triage through the import core (`importing.commit`, origin
`curriculum`), recording `curriculum.unit_opened` and not `import.completed`. Whether a unit is
`not_opened`, `opened` or `triaged` is computed from its terms, never stored (D-245). No AI call and
no usage sheet here; scenario units are written in M8.a2.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.db.event_log import record_event
from app.db.models import CurriculumTrack, CurriculumUnit, Deck, LexicalItem, Source
from app.domain import curriculum as rules
from app.domain import curriculum_unit as unit_rules
from app.domain.curriculum import (
    Labels,
    SyllabusTrack,
    TrackKind,
    UnitState,
    WordEntry,
    WordlistSource,
)
from app.domain.enums import DeckKind, ItemStatus, UnitContentStatus, UnitProgress
from app.domain.events import (
    CurriculumTrackStarted,
    CurriculumUnitOpened,
    ItemOrigin,
)
from app.domain.markdown_import import ImportHeader
from app.domain.study_day import as_utc
from app.services import importing
from app.services.library import LibraryError, create_deck, create_source

CONTENT_DIR = REPO_ROOT / "content"  # tests point it at a temporary copy
WORDLIST_UNIT_FORMAT = "wordlist-unit-1"
SCENARIO_UNIT_FORMAT = unit_rules.UNIT_FORMAT  # `app/domain/curriculum_unit.py`
DEFAULT_LIMIT = 25
MAX_LIMIT = 200


class TrackNotFound(LibraryError):
    status, code = 404, "track_not_found"


class UnitNotFound(LibraryError):
    status, code = 404, "unit_not_found"


class WordlistMissing(LibraryError):
    status, code = 409, "wordlist_missing"


class TrackNotStarted(LibraryError):
    status, code = 409, "track_not_started"


class NotAWordlistTrack(LibraryError):
    status, code = 422, "not_a_wordlist_track"


class SyllabusUnavailable(LibraryError):
    status, code = 503, "syllabus_unavailable"


# --- Files ---------------------------------------------------------------------------------------


def load_syllabus() -> rules.Syllabus:
    path = CONTENT_DIR / "curriculum.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return rules.parse_syllabus(data)
    except (OSError, yaml.YAMLError, rules.SyllabusError) as exc:
        raise SyllabusUnavailable(f"The syllabus cannot be read: {exc}") from exc


@lru_cache(maxsize=8)
def _read_entries(path: str, mtime_ns: int, size: int, source: str) -> tuple[WordEntry, ...]:
    return tuple(rules.read_wordlist(WordlistSource(source), Path(path).read_bytes()))


def wordlist_path(source: WordlistSource) -> Path:
    return CONTENT_DIR / "wordlists" / rules.WORDLIST_FILES[source]


def wordlist_entries(source: WordlistSource) -> list[WordEntry] | None:
    """The whole list, or None when the file is absent or unreadable (reason `wordlist_missing`)."""
    path = wordlist_path(source)
    try:
        stat = path.stat()
        return list(_read_entries(str(path), stat.st_mtime_ns, stat.st_size, source.value))
    except (OSError, ValueError):
        return None


def _entries_or_raise(track: SyllabusTrack) -> list[WordEntry]:
    assert track.source is not None  # noqa: S101 (a wordlist track always has a source)
    entries = wordlist_entries(track.source)
    if entries is None:
        raise WordlistMissing(
            f"The word list {rules.WORDLIST_FILES[track.source]} is missing or unreadable.",
            track=track.code,
            file=rules.WORDLIST_FILES[track.source],
        )
    return entries


def _syllabus_track(code: str) -> SyllabusTrack:
    track = load_syllabus().track(code)
    if track is None:
        raise TrackNotFound(f"There is no track '{code}'.", track=code)
    return track


# --- Track and deck lookup -----------------------------------------------------------------------


def _reference(code: str) -> str:
    return f"curriculum:{code}"


def find_deck(session: Session, code: str) -> Deck | None:
    return session.scalars(
        select(Deck)
        .join(Source, Source.id == Deck.source_id)
        .where(Deck.kind == DeckKind.CURRICULUM, Source.reference == _reference(code))
        .order_by(Deck.id.desc())
    ).first()


def _track_row(session: Session, code: str) -> CurriculumTrack | None:
    return session.scalars(select(CurriculumTrack).where(CurriculumTrack.code == code)).first()


# --- Shapes --------------------------------------------------------------------------------------


class TrackSummary(BaseModel):
    code: str
    kind: TrackKind
    source: WordlistSource | None
    title: Labels
    description: Labels
    unit_size: int | None
    unit_count: int
    available: bool
    reason: str | None  # `wordlist_missing`
    started: bool
    deck_id: int | None
    opened_units: int
    triaged_units: int
    syllabus_version: int


class UnitRow(BaseModel):
    """A line of the unit list of a track."""

    number: int
    code: str
    title: str
    title_fr: str | None  # scenario units only (word units are titled by their ranks)
    state: UnitState
    unit_id: int | None
    first_rank: int | None
    last_rank: int | None
    word_count: int | None
    content_status: UnitContentStatus | None
    progress: UnitProgress


class TrackDetail(BaseModel):
    track: TrackSummary
    total_units: int
    limit: int
    offset: int
    units: list[UnitRow]


class UnitTerm(BaseModel):
    item_id: int
    term: str
    status: ItemStatus


class FormulaOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    text: str
    item_type: str
    function_en: str
    function_fr: str
    style: str = Field(alias="register")
    item_id: int | None  # the library term, once the formula was added (D-251)


class ShadowingLineOut(BaseModel):
    line_index: int
    text: str
    take_count: int  # transcribed takes linked to the unit
    done: bool


class ScenarioFinalTask(BaseModel):
    prompt_en: str
    prompt_fr: str
    minutes: int
    formula_refs: list[int]
    target_item_ids: list[int]  # the library terms among the formulas to use
    attempt_ids: list[int]  # free-speaking takes linked to the unit
    corrected: bool


class ScenarioOut(BaseModel):
    revision: int
    edited: bool
    format: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    level: str | None
    formulas: list[FormulaOut]
    dialogue: dict[str, Any]
    shadowing: list[ShadowingLineOut]
    final_task: ScenarioFinalTask
    steps: dict[unit_rules.Step, bool]
    next_step: unit_rules.Step | None


class UnitOut(BaseModel):
    id: int
    track_code: str
    number: int
    code: str
    title: str
    state: UnitState
    progress: UnitProgress
    content_status: UnitContentStatus
    deck_id: int | None
    first_rank: int | None
    last_rank: int | None
    terms: list[UnitTerm]
    scenario: ScenarioOut | None = None  # the content of a generated scenario unit (M8.a2)


class OpenResult(BaseModel):
    created: bool  # false when the unit was already open: nothing was written
    imported: int
    attached: int
    skipped: int
    unit: UnitOut


# --- State ---------------------------------------------------------------------------------------


def _item_ids(unit: CurriculumUnit) -> list[int]:
    content: dict[str, Any] = unit.content or {}
    return [int(i) for i in content.get("item_ids", [])]


def _units_in_triage(session: Session, units: list[CurriculumUnit]) -> set[int]:
    """Ids of the units that still have a term waiting for triage (one query for all)."""
    wanted = {i for unit in units for i in _item_ids(unit)}
    if not wanted:
        return set()
    waiting = set(
        session.scalars(
            select(LexicalItem.id).where(
                LexicalItem.id.in_(wanted), LexicalItem.status == ItemStatus.TRIAGE
            )
        )
    )
    return {unit.id for unit in units if waiting & set(_item_ids(unit))}


def _is_scenario(unit: CurriculumUnit) -> bool:
    return (unit.content or {}).get("format") == SCENARIO_UNIT_FORMAT


def _state(unit: CurriculumUnit, in_triage: set[int]) -> UnitState:
    # A scenario unit whose formulas are not in the library yet is simply `opened`.
    waiting = unit.id in in_triage or (_is_scenario(unit) and not _item_ids(unit))
    return "opened" if waiting else "triaged"


def _unit_rows(session: Session, track_id: int) -> list[CurriculumUnit]:
    return list(
        session.scalars(
            select(CurriculumUnit)
            .where(CurriculumUnit.track_id == track_id)
            .order_by(CurriculumUnit.position)
        )
    )


def _summary(session: Session, track: SyllabusTrack, version: int, entries: Any) -> TrackSummary:
    row = _track_row(session, track.code)
    deck = find_deck(session, track.code) if track.kind == TrackKind.WORDLIST else None
    units = _unit_rows(session, row.id) if row else []
    waiting = _units_in_triage(session, units)
    if track.kind == TrackKind.WORDLIST:
        assert track.unit_size is not None  # noqa: S101
        available = entries is not None
        count = rules.unit_count(len(entries), track.unit_size) if available else 0
        started = deck is not None
    else:
        available, count, started = True, len(track.units), row is not None
    return TrackSummary(
        code=track.code,
        kind=track.kind,
        source=track.source,
        title=track.title,
        description=track.description,
        unit_size=track.unit_size,
        unit_count=count,
        available=available,
        reason=None if available else "wordlist_missing",
        started=started,
        deck_id=deck.id if deck else None,
        opened_units=len(units),
        triaged_units=len(units) - len(waiting),
        syllabus_version=version,
    )


def _entries_for(track: SyllabusTrack) -> list[WordEntry] | None:
    if track.kind == TrackKind.WORDLIST and track.source is not None:
        return wordlist_entries(track.source)
    return None


def list_tracks(session: Session) -> list[TrackSummary]:
    syllabus = load_syllabus()
    return [_summary(session, t, syllabus.version, _entries_for(t)) for t in syllabus.tracks]


def track_detail(
    session: Session, code: str, *, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> TrackDetail:
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    syllabus = load_syllabus()
    track = syllabus.track(code)
    if track is None:
        raise TrackNotFound(f"There is no track '{code}'.", track=code)
    entries = _entries_for(track)
    summary = _summary(session, track, syllabus.version, entries)
    row = _track_row(session, code)
    stored = {u.position: u for u in (_unit_rows(session, row.id) if row else [])}
    waiting = _units_in_triage(session, list(stored.values()))
    units: list[UnitRow] = []
    numbers = range(offset + 1, min(offset + limit, summary.unit_count) + 1)
    for number in numbers:
        unit = stored.get(number)
        if track.kind == TrackKind.WORDLIST:
            assert track.source is not None and track.unit_size is not None  # noqa: S101
            word_unit = (
                rules.slice_unit(track.source, entries, track.unit_size, number)
                if entries
                else None
            )
            if word_unit is None:
                continue
            code_, title, title_fr = word_unit.code, word_unit.title, None
            first, last, count = word_unit.first_rank, word_unit.last_rank, len(word_unit.words)
        else:
            scenario = track.units[number - 1]
            code_, title, title_fr = scenario.code, scenario.title.en, scenario.title.fr
            first = last = count = None
        units.append(
            UnitRow(
                number=number,
                code=code_,
                title=title,
                title_fr=title_fr,
                state=_state(unit, waiting) if unit else "not_opened",
                unit_id=unit.id if unit else None,
                first_rank=first,
                last_rank=last,
                word_count=count,
                content_status=unit.content_status if unit else UnitContentStatus.PENDING,
                progress=unit.progress if unit else UnitProgress.NOT_STARTED,
            )
        )
    return TrackDetail(
        track=summary, total_units=summary.unit_count, limit=limit, offset=offset, units=units
    )


# --- Start ---------------------------------------------------------------------------------------


class StartResult(BaseModel):
    track: TrackSummary
    created: bool  # a new deck (word-list track) or a new track row (scenarios) was made


def ensure_track_row(
    session: Session, track: SyllabusTrack, version: int, order: int, at: datetime
) -> tuple[CurriculumTrack, bool]:
    row = _track_row(session, track.code)
    if row is not None:
        return row, False
    row = CurriculumTrack(
        code=track.code,
        title=track.title.en,
        description=track.description.en,
        syllabus_version=str(version),
        sort_order=order,
        created_at=at,
        updated_at=at,
    )
    session.add(row)
    session.flush()
    return row, True


def start_track(session: Session, code: str, at: datetime) -> StartResult:
    """Start a track; calling it again returns the same deck and writes nothing."""
    at = as_utc(at)
    syllabus = load_syllabus()
    track = syllabus.track(code)
    if track is None:
        raise TrackNotFound(f"There is no track '{code}'.", track=code)
    order = [t.code for t in syllabus.tracks].index(code)
    entries = _entries_for(track)
    created = False
    if track.kind == TrackKind.WORDLIST:
        assert track.source is not None  # noqa: S101
        entries = _entries_or_raise(track)
        deck = find_deck(session, code)
        if deck is None:
            source = create_source(
                session,
                title=rules.SOURCE_TITLES[track.source],
                at=at,
                author=rules.SOURCE_AUTHOR,
                domain=rules.SOURCE_DOMAINS[track.source],
            )
            source.reference = _reference(code)
            deck = create_deck(
                session,
                name=track.title.en,
                at=at,
                description=track.description.en,
                domain=rules.SOURCE_DOMAINS[track.source],
                source_id=source.id,
                kind=DeckKind.CURRICULUM,
            )
            created = True
        ensure_track_row(session, track, syllabus.version, order, at)
        record_event(
            session,
            CurriculumTrackStarted(track_code=code, deck_id=deck.id, created=created),
            occurred_at=at,
        )
    else:
        _, created = ensure_track_row(session, track, syllabus.version, order, at)
    session.flush()
    return StartResult(track=_summary(session, track, syllabus.version, entries), created=created)


# --- Units ---------------------------------------------------------------------------------------


def _unit_out(session: Session, unit: CurriculumUnit, track_code: str) -> UnitOut:
    content: dict[str, Any] = unit.content or {}
    ids = _item_ids(unit)
    items = {
        item.id: item
        for item in session.scalars(select(LexicalItem).where(LexicalItem.id.in_(ids)))
    }
    terms = [
        UnitTerm(item_id=i, term=items[i].term, status=items[i].status) for i in ids if i in items
    ]
    waiting = any(t.status == ItemStatus.TRIAGE for t in terms) or (
        _is_scenario(unit) and not terms
    )
    scenario = None
    if _is_scenario(unit):
        from app.services import curriculum_units  # late: that module imports this one

        scenario = curriculum_units.scenario_out(session, unit)
    return UnitOut(
        id=unit.id,
        track_code=track_code,
        number=unit.position,
        code=unit.code,
        title=unit.title,
        state="opened" if waiting else "triaged",
        progress=unit.progress,
        content_status=unit.content_status,
        deck_id=unit.deck_id,
        first_rank=content.get("first_rank"),
        last_rank=content.get("last_rank"),
        terms=terms,
        scenario=scenario,
    )


def get_unit(session: Session, unit_id: int) -> UnitOut:
    unit = session.get(CurriculumUnit, unit_id)
    if unit is None:
        raise UnitNotFound(f"There is no unit {unit_id}.", unit_id=unit_id)
    track = session.get(CurriculumTrack, unit.track_id)
    assert track is not None  # noqa: S101 (foreign key)
    return _unit_out(session, unit, track.code)


def open_unit(session: Session, code: str, number: int, at: datetime) -> OpenResult:
    """Open unit `number` of a word-list track: its terms enter triage in the track's deck.

    Opening it again creates nothing. Raises TrackNotFound, NotAWordlistTrack, TrackNotStarted,
    WordlistMissing, UnitNotFound.
    """
    at = as_utc(at)
    syllabus = load_syllabus()
    track = syllabus.track(code)
    if track is None:
        raise TrackNotFound(f"There is no track '{code}'.", track=code)
    if track.kind != TrackKind.WORDLIST or track.source is None or track.unit_size is None:
        raise NotAWordlistTrack(
            f"Track '{code}' has no word units to open (its units are generated).", track=code
        )
    deck = find_deck(session, code)
    row = _track_row(session, code)
    if deck is None or row is None:
        raise TrackNotStarted(f"Start the track '{code}' first.", track=code)
    entries = _entries_or_raise(track)
    word_unit = rules.slice_unit(track.source, entries, track.unit_size, number)
    if word_unit is None:
        raise UnitNotFound(f"Track '{code}' has no unit {number}.", track=code, number=number)

    existing = session.scalars(
        select(CurriculumUnit).where(
            CurriculumUnit.track_id == row.id, CurriculumUnit.code == word_unit.code
        )
    ).first()
    if existing is not None:
        return OpenResult(
            created=False,
            imported=0,
            attached=0,
            skipped=0,
            unit=_unit_out(session, existing, code),
        )

    summary = importing.commit(
        session,
        header=ImportHeader(),
        rows=[importing.CommitRow(term=word.headword) for word in word_unit.words],
        target=importing.ImportTarget(deck_id=deck.id),
        intake="triage",
        at=at,
        origin=ItemOrigin.CURRICULUM,
        record_completed=False,
    )
    unit = CurriculumUnit(
        track_id=row.id,
        code=word_unit.code,
        title=word_unit.title,
        position=number,
        content={
            "format": WORDLIST_UNIT_FORMAT,
            "source": track.source.value,
            "source_version": rules.NGSL_VERSION
            if track.source == WordlistSource.NGSL
            else rules.NAWL_VERSION,
            "first_rank": word_unit.first_rank,
            "last_rank": word_unit.last_rank,
            "item_ids": summary.item_ids,
        },
        content_status=UnitContentStatus.GENERATED,
        deck_id=deck.id,
        progress=UnitProgress.IN_PROGRESS,
        created_at=at,
        updated_at=at,
    )
    session.add(unit)
    session.flush()
    record_event(
        session,
        CurriculumUnitOpened(
            track_code=code,
            unit_code=unit.code,
            unit_id=unit.id,
            deck_id=deck.id,
            imported=summary.imported,
            attached=summary.attached,
            skipped=summary.skipped,
        ),
        occurred_at=at,
    )
    session.flush()
    return OpenResult(
        created=True,
        imported=summary.imported,
        attached=summary.attached,
        skipped=summary.skipped,
        unit=_unit_out(session, unit, code),
    )
