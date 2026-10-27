"""Module H domain: the syllabus, the word-list readers, unit slicing. Real files included."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.domain import curriculum as c

CONTENT = Path(__file__).resolve().parents[2] / "content"


def real_syllabus() -> c.Syllabus:
    return c.parse_syllabus(yaml.safe_load((CONTENT / "curriculum.yaml").read_text("utf-8")))


def real_entries(source: c.WordlistSource) -> list[c.WordEntry]:
    raw = (CONTENT / "wordlists" / c.WORDLIST_FILES[source]).read_bytes()
    return c.read_wordlist(source, raw)


def minimal() -> dict[str, Any]:
    label = {"en": "x", "fr": "y"}
    return {
        "version": 1,
        "tracks": [
            {
                "code": "t1",
                "kind": "wordlist",
                "source": "ngsl",
                "unit_size": 25,
                "title": label,
                "description": label,
            }
        ],
    }


def test_real_syllabus_and_real_files() -> None:
    syllabus = real_syllabus()
    assert [t.code for t in syllabus.tracks] == [
        "general_everyday",
        "academic",
        "speaking_scenarios",
    ]
    scenarios = syllabus.track("speaking_scenarios")
    assert scenarios is not None and len(scenarios.units) == 16
    assert all(unit.level == "B1-B2" for unit in scenarios.units)

    ngsl = real_entries(c.WordlistSource.NGSL)
    assert len(ngsl) == 2809
    assert [e.rank for e in ngsl] == list(range(1, 2810))
    assert (
        ngsl[0].headword == "the"
        and ngsl[477].headword == "true"
        and ngsl[2097].headword == "false"
    )
    assert any(e.headword == "I" for e in ngsl)
    assert c.unit_count(len(ngsl), 25) == 113
    assert len(c.slice_units(c.WordlistSource.NGSL, ngsl, 25)[-1].words) == 9

    nawl = real_entries(c.WordlistSource.NAWL)
    assert len(nawl) == 959
    assert c.unit_count(len(nawl), 25) == 39
    assert nawl[0].headword == "abdominal"
    assert nawl[1].headword == "absorb" and nawl[1].forms == ("absorbs", "absorbed", "absorbing")
    assert [e.headword for e in nawl] == sorted(e.headword for e in nawl)


def test_unit_slicing() -> None:
    ngsl = real_entries(c.WordlistSource.NGSL)
    first = c.slice_unit(c.WordlistSource.NGSL, ngsl, 25, 1)
    assert first is not None
    assert (first.code, first.title, first.first_rank, first.last_rank) == (
        "ngsl_001",
        "Words 1–25",
        1,
        25,
    )
    last = c.slice_unit(c.WordlistSource.NGSL, ngsl, 25, 113)
    assert last is not None and (last.first_rank, last.last_rank) == (2801, 2809)
    assert c.slice_unit(c.WordlistSource.NGSL, ngsl, 25, 114) is None
    assert c.slice_unit(c.WordlistSource.NGSL, ngsl, 25, 0) is None


def test_ngsl_reader_rejects_a_broken_sequence() -> None:
    header = "Lemma,SFI Rank,SFI,Adjusted Frequency per Million (U)\n"
    with pytest.raises(c.WordlistError):
        c.read_ngsl((header + "the,1,1,1\nof,3,1,1\n").encode())
    with pytest.raises(c.WordlistError):
        c.read_ngsl(b"word,rank\nthe,1\n")
    assert [
        e.headword for e in c.read_ngsl((header + "TRUE,1,1,1\nFALSE,2,1,1\nI,3,1,1\n").encode())
    ] == [
        "true",
        "false",
        "I",
    ]


def test_nawl_reader_handles_latin1_and_crlf() -> None:
    entries = c.read_nawl("caf\xe9,caf\xe9s\r\nzoo,zoos\r\n".encode("iso-8859-1"))
    assert [(e.rank, e.headword, e.forms) for e in entries] == [
        (1, "caf\xe9", ("caf\xe9s",)),
        (2, "zoo", ("zoos",)),
    ]


def test_syllabus_validation() -> None:
    assert c.parse_syllabus(minimal()).tracks[0].unit_size == 25

    def broken(change: Any) -> None:
        data = copy.deepcopy(minimal())
        change(data)
        with pytest.raises(c.SyllabusError):
            c.parse_syllabus(data)

    broken(lambda d: d["tracks"][0].update(unit_size=5))
    broken(lambda d: d["tracks"][0].update(unit_size=51))
    broken(lambda d: d["tracks"][0].update(kind="other"))
    broken(lambda d: d["tracks"][0].update(source="coca"))
    broken(lambda d: d["tracks"][0].pop("source"))
    broken(lambda d: d["tracks"][0]["title"].update(fr=" "))
    broken(lambda d: d["tracks"].append(copy.deepcopy(d["tracks"][0])))
    broken(lambda d: d["tracks"][0].update(kind="scenarios", source=None, unit_size=None))
    broken(lambda d: d.update(extra=1))


def test_scenario_unit_codes_must_be_unique() -> None:
    unit = {
        "code": "u1",
        "title": {"en": "a", "fr": "b"},
        "level": "B1-B2",
        "goals": ["one", "two"],
        "situations": ["s"],
    }
    label = {"en": "x", "fr": "y"}
    data = {
        "version": 1,
        "tracks": [
            {
                "code": "s",
                "kind": "scenarios",
                "title": label,
                "description": label,
                "units": [unit, unit],
            }
        ],
    }
    with pytest.raises(c.SyllabusError):
        c.parse_syllabus(data)
