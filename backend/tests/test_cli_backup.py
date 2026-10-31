"""`backup create | verify | restore | auto` (M10.a): exit codes and messages (D-053)."""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import cli_backup
from app.db.engine import create_db_engine
from app.db.settings_store import set_setting
from tests.backup_old_schema import make_settings
from tests.backup_support import NOW, full_fingerprint, sqlite_url
from tests.stats_support import add_sample


def lines() -> tuple[list[str], cli_backup.Out]:
    sink: list[str] = []
    return sink, sink.append


def test_create_verify_restore_cycle(engine: Engine, db_url: str, tmp_path: Path) -> None:
    add_sample(engine)
    database = Path(engine.url.database)  # type: ignore[arg-type]
    settings = make_settings(tmp_path, database=database)
    archive = tmp_path / "out" / "b.zip"
    said, out = lines()
    assert cli_backup.run_backup_create(db_url, settings, archive, now=NOW, out=out) == 0
    assert archive.exists() and "written to" in said[0]
    assert cli_backup.run_backup_create(db_url, settings, archive, now=NOW, out=out) == 2  # exists
    assert (
        cli_backup.run_backup_create(db_url, settings, archive, force=True, now=NOW, out=out) == 0
    )
    assert not list(archive.parent.glob("*.tmp-*"))

    said.clear()
    assert cli_backup.run_backup_verify(archive, out=out) == 0
    assert "is sound" in said[0]

    other = tmp_path / "other"
    other.mkdir()
    target = other / "data.sqlite3"
    restore_settings = make_settings(other, database=target)
    said.clear()
    assert cli_backup.run_backup_restore(restore_settings, archive, out=out) == 0
    assert "not part of a backup" in said[-1]  # the reminder about the AI keys
    restored = create_db_engine(sqlite_url(target))
    try:
        # The source gained one `backup.created` event after the last archive was written: the
        # event is never inside the archive it describes.
        assert full_fingerprint(restored, skip=("event_log",)) == full_fingerprint(
            engine, skip=("event_log",)
        )
        assert events(restored) == events(engine) - 1
    finally:
        restored.dispose()


def events(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql("SELECT COUNT(*) FROM event_log").scalar_one()


def test_restore_into_a_database_with_data(engine: Engine, db_url: str, tmp_path: Path) -> None:
    add_sample(engine)
    database = Path(engine.url.database)  # type: ignore[arg-type]
    settings = make_settings(tmp_path, database=database)
    archive = tmp_path / "b.zip"
    assert cli_backup.run_backup_create(db_url, settings, archive, now=NOW, out=print) == 0
    assert cli_backup.run_backup_restore(settings, archive) == 2  # not empty
    assert cli_backup.run_backup_restore(settings, archive, replace=True) == 2  # needs --yes
    said, out = lines()
    engine.dispose()  # Windows refuses to move a database file that a pooled connection holds
    assert cli_backup.run_backup_restore(settings, archive, replace=True, yes=True, out=out) == 0
    assert list(database.parent.glob("*.bak-*"))
    assert any("previous database was kept" in line for line in said)


def test_verify_refuses_a_damaged_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert cli_backup.run_backup_verify(bad) == 2
    assert "not_a_zip" in capsys.readouterr().err


def test_create_needs_an_up_to_date_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = make_settings(tmp_path, database=tmp_path / "none.sqlite3")
    assert cli_backup.run_backup_create(settings.resolved_database_url, settings) == 2
    assert "db upgrade" in capsys.readouterr().err


def test_auto_exit_codes(engine: Engine, db_url: str, tmp_path: Path) -> None:
    database = Path(engine.url.database)  # type: ignore[arg-type]
    settings = make_settings(tmp_path, database=database)
    assert cli_backup.run_backup_auto(db_url, settings, now=NOW) == 2  # nothing configured
    folder = tmp_path / "cloud"
    with Session(engine) as session:
        set_setting(session, "backup_auto_folder", str(folder))
        session.commit()
    assert cli_backup.run_backup_auto(db_url, settings, now=NOW) == 1  # folder missing
    folder.mkdir()
    assert cli_backup.run_backup_auto(db_url, settings, now=NOW) == 0
    assert len(list(folder.glob("vocab-coach-backup-*.zip"))) == 1


def test_the_parser_knows_the_commands() -> None:
    from app.cli import _build_parser

    args = _build_parser().parse_args(
        ["--demo", "backup", "restore", "x.zip", "--replace", "--yes"]
    )
    assert (args.backup_command, args.replace, args.yes, args.demo) == ("restore", True, True, True)
