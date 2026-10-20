"""`demo seed`: determinism, safety checks, atomic replacement, CLI and demo mode (D-033)."""

import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.cli import main
from app.config import REPO_ROOT, Settings, get_settings
from app.db import migrate
from app.db.demo_marker import DEMO_MARKER_KEY, has_demo_marker, read_demo_marker
from app.db.engine import create_db_engine
from app.db.models import Deck
from app.db.settings_store import get_all_settings, get_setting, set_setting
from app.demo import simulation
from app.demo.seed import DemoSeedError, seed_demo, sqlite_url
from app.domain.settings_defaults import SettingError
from tests.demo_support import DEMO_ANCHOR, fingerprint

# Safety and CLI tests only need a small demo database; determinism uses three weeks.
SHORT_DAYS = 7
DETERMINISM_DAYS = 21


def _fingerprint(path: Path) -> str:
    engine = create_db_engine(sqlite_url(path))
    try:
        return fingerprint(engine)
    finally:
        engine.dispose()


def _personal_database(path: Path) -> None:
    """A migrated database with one row of user data and no demo marker."""
    url = sqlite_url(path)
    migrate.upgrade(url)
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            session.add(Deck(name="My own reading list"))
            session.commit()
    finally:
        engine.dispose()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Settings that point `data_dir` at a temporary folder."""
    monkeypatch.delenv("VOCAB_DATABASE_URL", raising=False)
    # Set (not deleted) so that teardown also removes the value `main(["--demo", ...])` writes.
    monkeypatch.setenv("VOCAB_DEMO", "0")
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


# --- determinism -----------------------------------------------------------------------------


def test_same_seed_gives_the_same_database_and_another_seed_does_not(tmp_path: Path) -> None:
    first, second, other = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3", tmp_path / "c.sqlite3"
    for path, seed in ((first, 7), (second, 7), (other, 8)):
        seed_demo(path, seed=seed, days=DETERMINISM_DAYS, anchor=DEMO_ANCHOR)

    assert _fingerprint(first) == _fingerprint(second)
    assert _fingerprint(first) != _fingerprint(other)


def test_marker_records_the_run(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    summary = seed_demo(path, seed=3, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            marker = read_demo_marker(session)
    finally:
        engine.dispose()
    assert marker == summary.marker
    assert (marker.seed, marker.days, marker.anchor) == (3, SHORT_DAYS, DEMO_ANCHOR)
    assert summary.rows["review_log"] > 0 and summary.errors_by_category


# --- safety checks ---------------------------------------------------------------------------


def test_seed_refuses_a_database_with_data_and_no_marker(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    _personal_database(path)
    before = path.read_bytes()

    for reset in (False, True):
        with pytest.raises(DemoSeedError, match="without the demo marker"):
            seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=reset)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir() if ".tmp-" in p.name) == []


def test_seed_accepts_an_empty_migrated_database(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    migrate.upgrade(sqlite_url(path))
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    try:
        assert has_demo_marker(engine)
    finally:
        engine.dispose()


def test_seed_without_reset_refuses_a_demo_database_and_reset_rebuilds_it(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    before = _fingerprint(path)

    with pytest.raises(DemoSeedError, match="already holds demo data"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert _fingerprint(path) == before


def test_a_failed_build_leaves_the_previous_database_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    before = _fingerprint(path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("app.demo.seed.simulate", broken)
    with pytest.raises(RuntimeError, match="simulated failure"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert _fingerprint(path) == before
    assert [p.name for p in tmp_path.iterdir() if ".tmp-" in p.name] == []


def _recording(folder: Path) -> Path:
    path = folder / "2026" / "09" / ("a" * 32 + ".webm")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old demo recording")
    return path


def _leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if ".tmp-" in p.name or ".old-" in p.name)


def _writing_clips(written: list[Path], *, fail: bool = False) -> Callable[..., None]:
    """A simulation that also writes one clip into its folder, then fails if asked."""
    real = simulation.simulate

    def simulate(*args: Any, audio_dir: Path, **kwargs: Any) -> None:
        real(*args, audio_dir=audio_dir, **kwargs)
        clip = audio_dir / "2026" / "08" / ("b" * 32 + ".wav")
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"new demo recording")
        written.append(clip)
        if fail:
            raise RuntimeError("simulated failure")

    return simulate


def test_the_new_recordings_replace_the_old_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "audio-demo"
    old = _recording(audio)
    written: list[Path] = []
    monkeypatch.setattr("app.demo.seed.simulate", _writing_clips(written))
    summary = seed_demo(tmp_path / "demo.sqlite3", days=SHORT_DAYS, anchor=DEMO_ANCHOR)

    assert not old.exists()
    assert (audio / "2026" / "08" / ("b" * 32 + ".wav")).read_bytes() == b"new demo recording"
    assert [p.parent.parent.parent.name for p in written] == [f"audio-demo.tmp-{os.getpid()}"]
    assert (summary.audio_dir, summary.recordings) == (audio.resolve(), 1)
    assert _leftovers(tmp_path) == []


def test_a_failed_build_keeps_the_previous_recordings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    before = _fingerprint(path)
    old = _recording(tmp_path / "audio-demo")
    written: list[Path] = []
    monkeypatch.setattr("app.demo.seed.simulate", _writing_clips(written, fail=True))
    with pytest.raises(RuntimeError, match="simulated failure"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert written and not written[0].exists()  # the temporary folder is gone
    assert old.read_bytes() == b"old demo recording"
    assert _fingerprint(path) == before
    assert _leftovers(tmp_path) == []


def test_a_refused_seed_keeps_the_demo_recordings(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    old = _recording(tmp_path / "audio-demo")
    with pytest.raises(DemoSeedError):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    assert old.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows locks open files")
def test_a_recording_in_use_is_reported_and_nothing_changes(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    before = _fingerprint(path)
    old = _recording(tmp_path / "audio-demo")

    with old.open("rb"), pytest.raises(DemoSeedError, match="recording is in use"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert _fingerprint(path) == before
    assert old.read_bytes() == b"old demo recording"
    assert _leftovers(tmp_path) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows locks open files")
def test_a_database_in_use_keeps_the_previous_recordings(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    old = _recording(tmp_path / "audio-demo")

    with path.open("rb"), pytest.raises(DemoSeedError, match="in use"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert old.read_bytes() == b"old demo recording"
    assert _leftovers(tmp_path) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows locks open files")
def test_a_database_in_use_is_reported_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "vocab-coach-demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    before = _fingerprint(path)

    with path.open("rb"), pytest.raises(DemoSeedError, match="in use"):
        seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR, reset=True)

    assert _fingerprint(path) == before
    assert [p.name for p in tmp_path.iterdir() if ".tmp-" in p.name] == []


def test_marker_is_not_a_user_setting(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    seed_demo(path, days=SHORT_DAYS, anchor=DEMO_ANCHOR)
    engine = create_db_engine(sqlite_url(path))
    try:
        with Session(engine) as session:
            assert DEMO_MARKER_KEY not in get_all_settings(session)
            with pytest.raises(SettingError):
                get_setting(session, DEMO_MARKER_KEY)
            with pytest.raises(SettingError):
                set_setting(session, DEMO_MARKER_KEY, {})
    finally:
        engine.dispose()


# --- demo mode settings and CLI --------------------------------------------------------------


def test_demo_mode_uses_the_demo_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOCAB_DATABASE_URL", raising=False)
    monkeypatch.delenv("VOCAB_DATA_DIR", raising=False)
    monkeypatch.setenv("VOCAB_DEMO", "1")
    expected = (REPO_ROOT / "data" / "vocab-coach-demo.sqlite3").resolve().as_posix()
    assert Settings(_env_file=None).resolved_database_url == f"sqlite:///{expected}"


def test_demo_mode_and_a_database_url_together_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOCAB_DEMO", "1")
    monkeypatch.setenv("VOCAB_DATABASE_URL", "sqlite:///C:/elsewhere/x.sqlite3")
    with pytest.raises(ValidationError, match="ambiguous"):
        Settings(_env_file=None)


def test_cli_demo_flag_with_a_database_url_fails_clearly(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(env / "personal.sqlite3"))
    assert main(["--demo", "plan", "today"]) == 1
    assert "ambiguous" in capsys.readouterr().err
    assert not (env / "personal.sqlite3").exists()


def test_cli_seed_never_touches_the_personal_database(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    personal = env / "personal.sqlite3"
    _personal_database(personal)
    before = personal.read_bytes()
    monkeypatch.setenv("VOCAB_DATABASE_URL", sqlite_url(personal))
    get_settings.cache_clear()

    args = ["demo", "seed", "--days", str(SHORT_DAYS), "--anchor", DEMO_ANCHOR.isoformat()]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Rows per table" in out and "Errors by category (level 2)" in out
    assert personal.read_bytes() == before
    assert (env / "vocab-coach-demo.sqlite3").exists()


def test_cli_seed_replaces_audio_demo_but_never_the_personal_recordings(env: Path) -> None:
    demo = _recording(env / "audio-demo")
    personal = _recording(env / "audio")
    args = ["demo", "seed", "--days", str(SHORT_DAYS), "--anchor", DEMO_ANCHOR.isoformat()]
    assert main(args) == 0
    assert not demo.exists()
    assert personal.read_bytes() == b"old demo recording"


def test_cli_seed_refuses_then_skips_then_resets(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["demo", "seed", "--days", str(SHORT_DAYS), "--anchor", DEMO_ANCHOR.isoformat()]
    assert main(args) == 0
    first = capsys.readouterr().out.split("built in")[0]

    assert main(args) == 2
    assert "--reset" in capsys.readouterr().err
    assert main([*args, "--if-missing"]) == 0
    assert "already seeded" in capsys.readouterr().out
    assert main([*args, "--reset"]) == 0
    assert capsys.readouterr().out.split("built in")[0] == first


def test_cli_demo_flag_plans_on_the_demo_database(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["demo", "seed", "--days", str(SHORT_DAYS), "--anchor", "2026-09-01"]) == 0
    capsys.readouterr()
    assert main(["--demo", "plan", "today", "--at", "2026-09-01T19:00"]) == 0
    assert "1. Reviews: none due" not in capsys.readouterr().out
