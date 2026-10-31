"""The automatic copy (M10.a): folder checks, rotation, retries, demo, startup."""

import threading
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.demo_marker import DemoMarker, write_demo_marker
from app.db.settings_store import set_setting
from app.services import backup, backup_auto
from app.services.backup import BackupError
from app.services.backup_auto import FolderError, run_auto, validate_folder
from app.services.backup_format import is_backup_file_name
from tests.backup_old_schema import make_settings
from tests.backup_support import NOW, read_members


@pytest.fixture(autouse=True)
def clean_state() -> None:
    backup_auto.state.last_error = None


def configure(engine: Engine, folder: Path | str, keep: int = 10) -> None:
    with Session(engine) as session:
        set_setting(session, "backup_auto_folder", str(folder))
        set_setting(session, "backup_auto_keep", keep)
        session.commit()


def copies(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def reason(value: str) -> str:
    with pytest.raises(FolderError) as caught:
        validate_folder(value)
    return caught.value.reason


def test_folder_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    validate_folder("")  # disabled
    validate_folder(str(tmp_path))
    assert reason("relative/folder") == "not_absolute"
    assert reason(str(tmp_path / "missing")) == "not_found"
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    assert reason(str(tmp_path / "file.txt")) == "not_found"  # a file is not a folder

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(backup_auto.tempfile, "TemporaryFile", refuse)
    assert reason(str(tmp_path)) == "not_writable"


def test_a_folder_inside_a_git_repository_is_refused_except_under_data(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "notes").mkdir()
    (repo / "data" / "backups").mkdir(parents=True)
    assert reason(str(repo)) == "inside_repository"
    assert reason(str(repo / "notes")) == "inside_repository"
    validate_folder(str(repo / "data"))
    validate_folder(str(repo / "data" / "backups"))


def test_rotation_keeps_ten_and_never_touches_other_files(engine: Engine, tmp_path: Path) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    foreign = [
        "notes.txt",
        "vocab-coach-backup-20260101-000000.zip.bak",
        "my-vocab-coach-backup-20260101-000000.zip",
        "vocab-coach-backup-2026.zip",
        "vocab-coach-backup-20260101-000000.ZIP",
    ]
    for name in foreign:
        (folder / name).write_text("mine", encoding="utf-8")
    configure(engine, folder, keep=10)
    settings = make_settings(tmp_path)
    for index in range(12):
        result = run_auto(engine, settings, NOW + timedelta(seconds=index))
        assert result.ok
    ours = [n for n in copies(folder) if is_backup_file_name(n)]
    assert len(ours) == 10
    assert ours[0] == "vocab-coach-backup-20260902-093002.zip"  # Douala is UTC+1; the oldest went
    assert set(foreign) <= set(copies(folder))
    assert len(copies(folder)) == 10 + len(foreign)  # no temporary file left


def test_a_locked_target_is_retried_three_times_then_reported(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    configure(engine, folder)
    pauses: list[float] = []
    attempts: list[int] = []
    real = backup.os.replace

    def locked(source, target):  # noqa: ANN001, ANN202
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError(32, "in use by OneDrive")
        return real(source, target)

    monkeypatch.setattr(backup.os, "replace", locked)
    result = run_auto(engine, make_settings(tmp_path), NOW, sleep=pauses.append)
    assert result.ok and pauses == [0.2, 0.2] and len(attempts) == 3

    attempts.clear()

    def always(source, target):  # noqa: ANN001, ANN202
        attempts.append(1)
        raise PermissionError(32, "in use by OneDrive")

    monkeypatch.setattr(backup.os, "replace", always)
    pauses.clear()
    failed = run_auto(
        engine, make_settings(tmp_path), NOW + timedelta(minutes=1), sleep=pauses.append
    )
    assert not failed.ok and failed.error == "file_locked"
    assert len(attempts) == 4 and pauses == [0.2, 0.2, 0.2]  # the first try and three more
    assert backup_auto.state.last_error == "file_locked"
    assert not [n for n in copies(folder) if ".tmp-" in n]


def test_not_configured_and_demo(engine: Engine, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(BackupError) as caught:
        run_auto(engine, settings, NOW)
    assert caught.value.code == "backup_not_configured"
    folder = tmp_path / "cloud"
    folder.mkdir()
    configure(engine, folder)
    with Session(engine) as session:
        write_demo_marker(session, DemoMarker(dataset_version=1, seed=1, days=1, anchor=NOW.date()))
        session.commit()
    with pytest.raises(BackupError) as caught:
        run_auto(engine, settings, NOW)
    assert caught.value.code == "demo_read_only"
    assert copies(folder) == []


def test_a_bad_folder_is_reported_not_raised(engine: Engine, tmp_path: Path) -> None:
    configure(engine, tmp_path / "cloud")  # does not exist yet
    result = run_auto(engine, make_settings(tmp_path), NOW)
    assert not result.ok and result.error == "not_found"
    assert backup_auto.state.last_error == "not_found"


def test_startup_copies_only_when_the_last_one_is_old(engine: Engine, tmp_path: Path) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    configure(engine, folder)
    database = Path(engine.url.database)  # type: ignore[arg-type]
    settings = make_settings(tmp_path, database=database)
    backup_auto.at_startup(settings, NOW)
    assert len(copies(folder)) == 1  # never copied yet
    backup_auto.at_startup(settings, NOW + timedelta(hours=23))
    assert len(copies(folder)) == 1
    backup_auto.at_startup(settings, NOW + timedelta(hours=25))
    assert len(copies(folder)) == 2
    manifest = read_members(folder / copies(folder)[0])["manifest.json"]
    assert b'"kind": "auto"' in manifest


def test_startup_hook_runs_in_the_lifespan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app import main

    called = threading.Event()
    monkeypatch.setattr(main, "startup_backup", lambda settings: called.set())
    with TestClient(main.create_app(make_settings(tmp_path))):
        assert called.wait(timeout=5)
