"""`curriculum tracks | show | start | open` on a temporary database."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.cli import main
from app.config import get_settings
from tests.conftest import sqlite_url


@pytest.fixture
def db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "data" / "vocab-coach.sqlite3"
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(path))
    monkeypatch.setenv("VOCAB_DEMO", "0")
    get_settings.cache_clear()
    assert main(["db", "upgrade"]) == 0
    yield path
    get_settings.cache_clear()


def test_tracks_show_start_open(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["curriculum", "tracks"]) == 0
    out = capsys.readouterr().out
    assert "general_everyday" in out and "113 units" in out and "not started" in out
    assert "speaking_scenarios" in out and "16 units" in out

    assert main(["curriculum", "open", "general_everyday", "1"]) == 2
    assert "Start the track 'general_everyday' first" in capsys.readouterr().err

    assert main(["curriculum", "start", "general_everyday"]) == 0
    assert "started: deck 1 (created)" in capsys.readouterr().out
    assert main(["curriculum", "start", "general_everyday"]) == 0
    assert "already started" in capsys.readouterr().out

    assert main(["curriculum", "open", "general_everyday", "1"]) == 0
    out = capsys.readouterr().out
    assert "ngsl_001 opened: 25 new" in out and out.splitlines()[1].startswith("the, be, and")
    assert main(["curriculum", "open", "general_everyday", "1"]) == 0
    assert "already open (opened)" in capsys.readouterr().out

    assert main(["curriculum", "show", "general_everyday"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "113 units, page 1/5" in lines[0]
    assert "ngsl_001" in lines[1] and "opened" in lines[1]
    assert "not_opened" in lines[2]
    assert main(["curriculum", "show", "general_everyday", "--page", "5"]) == 0
    assert "ngsl_113" in capsys.readouterr().out.splitlines()[-1]


def test_usage_errors(db_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["curriculum", "show", "nope"]) == 2
    assert "There is no track 'nope'" in capsys.readouterr().err
    assert main(["curriculum", "start", "nope"]) == 2
    assert main(["curriculum", "start", "speaking_scenarios"]) == 0
    capsys.readouterr()
    assert main(["curriculum", "open", "speaking_scenarios", "1"]) == 2
    assert "generated" in capsys.readouterr().err
