"""The database at the start of the use mode (M10.b, D-313): copy first, then upgrade."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app import cli
from app.config import get_settings
from app.db import migrate
from app.db.engine import create_db_engine
from app.services import backup_auto, backup_format, startup_upgrade
from app.services.startup_upgrade import StartupError, prepare_database
from tests.backup_old_schema import make_settings
from tests.backup_support import sqlite_url

NOW = datetime(2026, 10, 27, 9, 30, 0)  # noqa: DTZ001 (a file name, local time)


def revision_of(database: Path) -> str | None:
    engine = create_db_engine(sqlite_url(database))
    try:
        return migrate.schema_status(engine).revision
    finally:
        engine.dispose()


def old_database(tmp_path: Path) -> tuple[Path, str]:
    """A personal database at `0001` with one recognisable row; the settings that select it."""
    database = tmp_path / "data" / "vocab-coach.sqlite3"
    database.parent.mkdir()
    url = sqlite_url(database)
    migrate.upgrade(url, "0001")
    engine = create_db_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO lexical_item (id, term, normalized_form, item_type, status, "
                "status_changed_at, created_at, updated_at) VALUES "
                "(1, 'shed light on', 'shed light on', 'word', 'draft', "
                "'2026-08-01 09:00:00', '2026-08-01 09:00:00', '2026-08-01 09:00:00')"
            )
    finally:
        engine.dispose()
    return database, url


def test_a_database_at_0001_is_copied_then_upgraded(tmp_path: Path) -> None:
    database, _url = old_database(tmp_path)
    settings = make_settings(tmp_path, database=database)
    messages: list[str] = []
    result = prepare_database(settings, cli.db_upgrade, NOW, messages.append)

    assert result.action == "upgraded"
    assert result.from_revision == "0001"
    assert revision_of(database) == migrate.head_revision()
    copy = result.backup
    assert copy is not None
    assert copy.parent == tmp_path / "data" / "backups"
    assert copy.name == "vocab-coach-pre-upgrade-from-0001-20261027-093000.sqlite3"
    assert revision_of(copy) == "0001"  # the state before the upgrade
    with sqlite3.connect(copy) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT term FROM lexical_item").fetchall() == [
            ("shed light on",)
        ]
    assert not list(copy.parent.glob("*.tmp-*"))
    assert any(str(copy) in message for message in messages)


def test_the_name_is_not_one_of_the_rotation(tmp_path: Path) -> None:
    name = startup_upgrade.pre_upgrade_name("0001", NOW)
    assert not backup_format.is_backup_file_name(name)


def test_the_automatic_rotation_never_deletes_the_pre_upgrade_copy(tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    folder.mkdir()
    kept = folder / startup_upgrade.pre_upgrade_name("0001", NOW)
    kept.write_bytes(b"x")
    for day in range(1, 6):
        (folder / f"vocab-coach-backup-2026100{day}-120000.zip").write_bytes(b"z")
    removed = backup_auto.rotate(folder, 2)
    assert len(removed) == 3
    assert kept.exists()


def test_when_the_copy_fails_nothing_is_upgraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _url = old_database(tmp_path)
    settings = make_settings(tmp_path, database=database)

    def failing(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(startup_upgrade, "copy_before_upgrade", failing)
    upgraded: list[str] = []
    with pytest.raises(StartupError, match=r"NOT upgraded.*disk full"):
        prepare_database(settings, upgraded.append, NOW, lambda _m: None)
    assert upgraded == []
    assert revision_of(database) == "0001"
    assert not (tmp_path / "data" / "backups").exists() or not list(
        (tmp_path / "data" / "backups").glob("*.sqlite3")
    )


def test_a_failed_integrity_check_stops_the_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _url = old_database(tmp_path)
    settings = make_settings(tmp_path, database=database)
    # The copy comes out with another revision than the original: refused, nothing kept.
    monkeypatch.setattr(startup_upgrade, "_stored_revision", lambda _file: "other")
    with pytest.raises(StartupError, match="NOT upgraded"):
        prepare_database(settings, cli.db_upgrade, NOW, lambda _m: None)
    assert revision_of(database) == "0001"
    assert not list((tmp_path / "data" / "backups").glob("*"))


def test_an_up_to_date_database_is_left_alone(tmp_path: Path) -> None:
    database = tmp_path / "data" / "vocab-coach.sqlite3"
    database.parent.mkdir()
    migrate.upgrade(sqlite_url(database))
    settings = make_settings(tmp_path, database=database)
    result = prepare_database(settings, lambda _url: pytest.fail("no upgrade"), NOW, print)
    assert result.action == "ready"
    assert not (tmp_path / "data" / "backups").exists()


def test_a_missing_database_is_created(tmp_path: Path) -> None:
    database = tmp_path / "data" / "vocab-coach.sqlite3"
    database.parent.mkdir()
    settings = make_settings(tmp_path, database=database)
    result = prepare_database(settings, cli.db_upgrade, NOW, lambda _m: None)
    assert result.action == "created"
    assert revision_of(database) == migrate.head_revision()


def test_a_demo_database_behind_head_is_not_touched(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, demo=True)
    database = settings.demo_database_file
    database.parent.mkdir(parents=True)
    migrate.upgrade(sqlite_url(database), "0001")
    messages: list[str] = []
    result = prepare_database(
        settings, lambda _url: pytest.fail("no upgrade"), NOW, messages.append
    )
    assert result.action == "demo_behind"
    assert revision_of(database) == "0001"
    assert any("demo seed --reset" in message for message in messages)
    assert not (tmp_path / "data" / "backups").exists()


def test_the_command_reports_exit_code_2_when_the_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database, url = old_database(tmp_path)
    monkeypatch.setenv("VOCAB_DATABASE_URL", url)
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("VOCAB_DEMO", raising=False)
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(
            startup_upgrade, "copy_before_upgrade", lambda *_a: (_ for _ in ()).throw(OSError("x"))
        )
        assert cli.main(["db", "prepare"]) == 2
        assert "NOT upgraded" in capsys.readouterr().err
        assert revision_of(database) == "0001"
        monkeypatch.undo()
        monkeypatch.setenv("VOCAB_DATABASE_URL", url)
        monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        assert cli.main(["db", "prepare"]) == 0
        assert revision_of(database) == migrate.head_revision()
        assert len(list((tmp_path / "data" / "backups").glob("vocab-coach-pre-upgrade-*"))) == 1
    finally:
        get_settings.cache_clear()


def test_use_mode_without_a_build_stops_with_code_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VOCAB_FRONTEND_DIST", str(tmp_path / "no-dist"))
    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("VOCAB_USE_MODE", raising=False)
    get_settings.cache_clear()
    try:
        assert cli.main(["--use"]) == 2
        assert "npm --prefix frontend run build" in capsys.readouterr().err
    finally:
        monkeypatch.delenv("VOCAB_USE_MODE", raising=False)
        get_settings.cache_clear()
