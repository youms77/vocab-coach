"""Restoring a backup (M10.a): old schemas, refusals, replacement, injected failures, locks."""

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, select

from app.db import migrate
from app.db.engine import create_db_engine
from app.db.models import LexicalItem, Setting
from app.services import backup_restore
from app.services.backup import BackupError
from app.services.backup_restore import restore_backup
from tests.backup_old_schema import archive_at_revision_0001
from tests.backup_support import (
    audio_files,
    full_fingerprint,
    make_archive,
    read_members,
    sqlite_url,
    with_manifest,
    write_members,
)


def demo_archive(demo_engine: Engine, tmp_path: Path) -> Path:
    archive = tmp_path / "demo.zip"
    make_archive(demo_engine, tmp_path / "source" / "audio-demo", archive)
    return archive


def names(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()}


def live_copy(demo_source: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    folder = tmp_path / "live"
    shutil.copytree(demo_source, folder)
    return folder, folder / "demo.sqlite3", folder / "audio-demo"


def fingerprint_of(path: Path) -> str:
    engine = create_db_engine(sqlite_url(path))
    try:
        return full_fingerprint(engine)
    finally:
        engine.dispose()


def test_restore_from_revision_0001_upgrades_to_head(tmp_path: Path) -> None:
    archive, terms = archive_at_revision_0001(tmp_path)
    target = tmp_path / "restored" / "data.sqlite3"
    result = restore_backup(
        archive, db_file=target, audio_dir=tmp_path / "restored" / "audio", demo=False
    )
    assert result.upgraded_from == "0001"
    engine = create_db_engine(sqlite_url(target))
    try:
        assert migrate.schema_status(engine).at_head
        columns = {c["name"] for c in inspect(engine).get_columns("review_log")}
        assert "production_attempt_id" in columns  # added by 0002 after the rows were loaded
        with engine.connect() as connection:
            found = connection.execute(select(LexicalItem.term).order_by(LexicalItem.id))
            assert list(found.scalars()) == terms
            assert connection.execute(select(Setting.value)).scalar_one() == 0.85
    finally:
        engine.dispose()


def test_unknown_revision_is_refused_without_writing(tmp_path: Path, demo_engine: Engine) -> None:
    members = read_members(demo_archive(demo_engine, tmp_path))
    newer = tmp_path / "newer.zip"
    write_members(newer, with_manifest(members, lambda m: m.update(alembic_revision="9999")))
    folder = tmp_path / "restored"
    folder.mkdir()
    with pytest.raises(BackupError) as caught:
        restore_backup(newer, db_file=folder / "d.sqlite3", audio_dir=folder / "audio", demo=True)
    assert caught.value.code == "backup_from_newer_version"
    assert not list(folder.iterdir())


def test_non_empty_target_needs_replace_and_keeps_a_bak(
    tmp_path: Path, demo_engine: Engine, demo_source: Path
) -> None:
    archive = demo_archive(demo_engine, tmp_path)
    _folder, target, audio = live_copy(demo_source, tmp_path)
    (audio / "old-only.txt").write_text("previous", encoding="utf-8")
    before = fingerprint_of(target)
    before_audio = audio_files(audio)
    with pytest.raises(BackupError) as caught:
        restore_backup(archive, db_file=target, audio_dir=audio, demo=True)
    assert caught.value.code == "target_not_empty"
    assert fingerprint_of(target) == before
    assert audio_files(audio) == before_audio

    result = restore_backup(archive, db_file=target, audio_dir=audio, demo=True, replace=True)
    assert result.db_backup is not None and ".bak-" in result.db_backup.name
    assert result.audio_backup is not None
    assert result.audio_backup.name.startswith("audio-demo.bak-")
    assert fingerprint_of(result.db_backup) == before
    assert audio_files(result.audio_backup) == before_audio
    assert "old-only.txt" not in audio_files(audio)


def test_demo_and_personal_archives_never_cross(
    tmp_path: Path, demo_engine: Engine, engine: Engine
) -> None:
    demo_zip = demo_archive(demo_engine, tmp_path)
    personal_zip = tmp_path / "personal.zip"
    make_archive(engine, tmp_path / "audio", personal_zip)
    folder = tmp_path / "t"
    folder.mkdir()
    with pytest.raises(BackupError) as caught:
        restore_backup(demo_zip, db_file=folder / "p.sqlite3", audio_dir=folder / "a", demo=False)
    assert caught.value.code == "demo_mismatch"
    with pytest.raises(BackupError) as caught:
        restore_backup(
            personal_zip, db_file=folder / "d.sqlite3", audio_dir=folder / "b", demo=True
        )
    assert caught.value.code == "demo_mismatch"
    assert not list(folder.iterdir())


def test_failure_in_the_middle_of_the_insertion_changes_nothing(
    tmp_path: Path, demo_engine: Engine, demo_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = demo_archive(demo_engine, tmp_path)
    folder, target, audio = live_copy(demo_source, tmp_path)
    before = fingerprint_of(target)
    before_audio, before_names = audio_files(audio), names(folder)
    real = backup_restore._insert_table
    calls: list[str] = []

    def failing(connection, table, rows):  # noqa: ANN001, ANN202
        calls.append(table.name)
        if len(calls) == 6:
            raise RuntimeError("injected")
        return real(connection, table, rows)

    monkeypatch.setattr(backup_restore, "_insert_table", failing)
    with pytest.raises(RuntimeError, match="injected"):
        restore_backup(archive, db_file=target, audio_dir=audio, demo=True, replace=True)
    assert len(calls) == 6
    assert fingerprint_of(target) == before
    assert audio_files(audio) == before_audio
    assert names(folder) == before_names  # no temporary file or folder left


def test_locked_file_gives_a_clear_message_and_changes_nothing(
    tmp_path: Path, demo_engine: Engine, demo_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database cannot be moved: the audio folder, already set aside, is put back."""
    archive = demo_archive(demo_engine, tmp_path)
    folder, target, audio = live_copy(demo_source, tmp_path)
    before = fingerprint_of(target)
    before_audio, before_names = audio_files(audio), names(folder)
    real = backup_restore.os.replace

    def locked(source, destination):  # noqa: ANN001, ANN202
        if Path(source) == target:
            raise PermissionError(32, "The process cannot access the file")
        return real(source, destination)

    monkeypatch.setattr(backup_restore.os, "replace", locked)
    with pytest.raises(BackupError) as caught:
        restore_backup(archive, db_file=target, audio_dir=audio, demo=True, replace=True)
    monkeypatch.undo()
    assert caught.value.code == "file_locked"
    assert "Stop the app" in caught.value.message
    assert fingerprint_of(target) == before
    assert audio_files(audio) == before_audio
    assert names(folder) == before_names


@pytest.mark.skipif(sys.platform != "win32", reason="SQLite files cannot be renamed while open")
def test_database_held_open_by_another_connection(
    tmp_path: Path, demo_engine: Engine, demo_source: Path
) -> None:
    archive = demo_archive(demo_engine, tmp_path)
    folder, target, audio = live_copy(demo_source, tmp_path)
    before_audio, before_names = audio_files(audio), names(folder)
    holder = sqlite3.connect(target)
    holder.execute("SELECT count(*) FROM setting").fetchone()
    try:
        with pytest.raises(BackupError) as caught:
            restore_backup(archive, db_file=target, audio_dir=audio, demo=True, replace=True)
    finally:
        holder.close()
    assert caught.value.code == "file_locked"
    assert audio_files(audio) == before_audio
    assert names(folder) == before_names
    assert target.exists()
