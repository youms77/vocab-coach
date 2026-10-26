"""General English tracks (module H): syllabus, word-list readers and unit slicing. Pure Python.

The syllabus is `content/curriculum.yaml`; the services read the files and hand the content to the
functions below, which validate it and compute everything else (D-240 to D-245). Two kinds of track:

- `wordlist`: the NGSL (frequency order) or the NAWL (official alphabetical order, no frequency
  rank exists). A unit is a slice of `unit_size` consecutive ranks, computed from the file: unit
  `n` holds ranks `(n-1)*size+1 .. n*size`, the last one may be shorter.
- `scenarios`: units listed in the syllabus, whose content the AI writes later (M8.a2).
"""

import csv
import io
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

NGSL_VERSION = "1.2"
NAWL_VERSION = "1.2"
NGSL_FILE = "NGSL_12_stats.csv"
NAWL_FILE = "NAWL_12_lemmatized_for_teaching.csv"
UNIT_SIZE_MIN, UNIT_SIZE_MAX = 10, 50

Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=60)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SyllabusError(ValueError):
    """The syllabus file is invalid; the message says where."""


class TrackKind(StrEnum):
    WORDLIST = "wordlist"
    SCENARIOS = "scenarios"


class WordlistSource(StrEnum):
    NGSL = "ngsl"
    NAWL = "nawl"


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    en: Text
    fr: Text


class ScenarioUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Code
    title: Labels
    level: Text
    goals: Annotated[list[Text], Field(min_length=2, max_length=4)]
    situations: Annotated[list[Text], Field(min_length=1, max_length=6)]


class SyllabusTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Code
    kind: TrackKind
    title: Labels
    description: Labels
    source: WordlistSource | None = None
    unit_size: Annotated[int, Field(ge=UNIT_SIZE_MIN, le=UNIT_SIZE_MAX)] | None = None
    units: list[ScenarioUnit] = []

    def check(self) -> None:
        if self.kind == TrackKind.WORDLIST:
            if self.source is None or self.unit_size is None:
                raise SyllabusError(
                    f"track '{self.code}': a wordlist track needs source and unit_size"
                )
            if self.units:
                raise SyllabusError(f"track '{self.code}': a wordlist track has no listed units")
        else:
            if self.source is not None or self.unit_size is not None:
                raise SyllabusError(
                    f"track '{self.code}': a scenarios track has no source or unit_size"
                )
            if not self.units:
                raise SyllabusError(f"track '{self.code}': a scenarios track needs units")
            codes = [unit.code for unit in self.units]
            if len(set(codes)) != len(codes):
                raise SyllabusError(f"track '{self.code}': duplicate unit codes")


class Syllabus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Annotated[int, Field(ge=1)]
    tracks: Annotated[list[SyllabusTrack], Field(min_length=1)]

    def track(self, code: str) -> SyllabusTrack | None:
        return next((track for track in self.tracks if track.code == code), None)


def parse_syllabus(data: Any) -> Syllabus:
    """Validate the parsed YAML. Raises SyllabusError (unique codes, sizes, labels, kinds)."""
    try:
        syllabus = Syllabus.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise SyllabusError(f"invalid syllabus at {where}: {first['msg']}") from exc
    codes = [track.code for track in syllabus.tracks]
    if len(set(codes)) != len(codes):
        raise SyllabusError("duplicate track codes")
    for track in syllabus.tracks:
        track.check()
    return syllabus


# --- Word lists ----------------------------------------------------------------------------------


class WordEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int  # 1-based position in the list (frequency rank for the NGSL, alphabetical for NAWL)
    headword: str
    forms: tuple[str, ...] = ()  # inflected forms (NAWL only), for information


class WordlistError(ValueError):
    """The file does not have the documented format."""


_SPREADSHEET_ARTEFACTS = {"TRUE": "true", "FALSE": "false"}


def read_ngsl(raw: bytes) -> list[WordEntry]:
    """`Lemma,SFI Rank,SFI,Adjusted Frequency per Million (U)`; ranks must be 1..N, contiguous.

    The spreadsheet turned the words `true` and `false` into `TRUE` and `FALSE`: lowercased here.
    Every other lemma is kept as written (`I` stays `I`).
    """
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    if not rows or [c.strip() for c in rows[0][:2]] != ["Lemma", "SFI Rank"]:
        raise WordlistError("NGSL: unexpected header")
    entries: list[WordEntry] = []
    for number, row in enumerate(rows[1:], start=2):
        if not row or not "".join(row).strip():
            continue
        try:
            rank = int(row[1])
        except (IndexError, ValueError) as exc:
            raise WordlistError(f"NGSL: bad rank on line {number}") from exc
        lemma = row[0].strip()
        if not lemma:
            raise WordlistError(f"NGSL: empty lemma on line {number}")
        if rank != len(entries) + 1:
            raise WordlistError(f"NGSL: rank {rank} on line {number} breaks the sequence")
        entries.append(WordEntry(rank=rank, headword=_SPREADSHEET_ARTEFACTS.get(lemma, lemma)))
    if not entries:
        raise WordlistError("NGSL: no word")
    return entries


def read_nawl(raw: bytes) -> list[WordEntry]:
    """No header; one row per headword then its inflected forms (ISO-8859-1, CRLF).

    The file is alphabetical and no official frequency exists, so the rank is the row number.
    """
    entries: list[WordEntry] = []
    for row in csv.reader(io.StringIO(raw.decode("iso-8859-1"), newline="")):
        cells = [cell.strip() for cell in row if cell.strip()]
        if not cells:
            continue
        entries.append(WordEntry(rank=len(entries) + 1, headword=cells[0], forms=tuple(cells[1:])))
    if not entries:
        raise WordlistError("NAWL: no word")
    return entries


def read_wordlist(source: WordlistSource, raw: bytes) -> list[WordEntry]:
    return read_ngsl(raw) if source == WordlistSource.NGSL else read_nawl(raw)


WORDLIST_FILES = {WordlistSource.NGSL: NGSL_FILE, WordlistSource.NAWL: NAWL_FILE}
SOURCE_TITLES = {
    WordlistSource.NGSL: "New General Service List 1.2",
    WordlistSource.NAWL: "New Academic Word List 1.2",
}
SOURCE_AUTHOR = "Browne, Culligan, Phillips"
SOURCE_DOMAINS = {WordlistSource.NGSL: "general", WordlistSource.NAWL: "academic"}


# --- Units ---------------------------------------------------------------------------------------


class WordUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: int  # 1-based
    code: str  # ngsl_001
    title: str  # Words 1–25
    first_rank: int
    last_rank: int
    words: tuple[WordEntry, ...]


def unit_count(total: int, size: int) -> int:
    return -(-total // size)


def unit_code(source: WordlistSource, number: int) -> str:
    return f"{source.value}_{number:03d}"


def slice_unit(
    source: WordlistSource, entries: list[WordEntry], size: int, number: int
) -> WordUnit | None:
    """Unit `number` (1-based), or None when it does not exist."""
    if number < 1 or number > unit_count(len(entries), size):
        return None
    start = (number - 1) * size
    words = tuple(entries[start : start + size])
    first, last = words[0].rank, words[-1].rank
    return WordUnit(
        number=number,
        code=unit_code(source, number),
        title=f"Words {first}–{last}",
        first_rank=first,
        last_rank=last,
        words=words,
    )


def slice_units(source: WordlistSource, entries: list[WordEntry], size: int) -> list[WordUnit]:
    units = [
        slice_unit(source, entries, size, n) for n in range(1, unit_count(len(entries), size) + 1)
    ]
    return [unit for unit in units if unit is not None]


UnitState = Literal["not_opened", "opened", "triaged"]
