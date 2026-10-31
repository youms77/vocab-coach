"""Backup API (M10.a): download, status, automatic copy now, folder setting, after a session."""

import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.demo_marker import DemoMarker, write_demo_marker
from app.db.models import EventLog
from app.services import backup_auto
from tests.api.conftest import ApiEnv
from tests.api.session_support import start_session
from tests.backup_support import NOW
from tests.stats_support import add_sample

STATUS_KEYS = {
    "auto_folder_configured",
    "last_auto_at",
    "last_auto_error",
    "last_manual_at",
    "keep",
    "demo",
}


@pytest.fixture(autouse=True)
def clean_state() -> None:
    backup_auto.state.last_error = None


def backup_events(env: ApiEnv) -> list[EventLog]:
    with Session(env.engine) as session:
        query = (
            select(EventLog).where(EventLog.event_type == "backup.created").order_by(EventLog.id)
        )
        return list(session.scalars(query))


def set_folder(env: ApiEnv, folder: Path | str, keep: int | None = None) -> None:
    changes: dict[str, object] = {"backup_auto_folder": str(folder)}
    if keep is not None:
        changes["backup_auto_keep"] = keep
    response = env.client.patch("/api/settings", json=changes)
    assert response.status_code == 200, response.text


def test_download_is_a_valid_zip_with_an_attachment_name(env: ApiEnv) -> None:
    add_sample(env.engine)
    response = env.client.post("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="vocab-coach-backup-')
    assert disposition.endswith('.zip"')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert "manifest.json" in archive.namelist()
    events = backup_events(env)
    assert [e.payload["kind"] for e in events] == ["manual"]


def test_status_shape_has_no_path(env: ApiEnv, tmp_path: Path) -> None:
    status = env.client.get("/api/backup/status").json()
    assert set(status) == STATUS_KEYS
    assert status["auto_folder_configured"] is False and status["keep"] == 10
    assert status["last_auto_at"] is None and status["last_manual_at"] is None
    folder = tmp_path / "cloud"
    folder.mkdir()
    set_folder(env, folder)
    env.client.post("/api/backup")
    status = env.client.get("/api/backup/status").json()
    assert status["auto_folder_configured"] is True
    assert status["last_manual_at"].endswith("Z")
    assert str(folder) not in str(status)


def test_run_now_copies_into_the_folder(env: ApiEnv, tmp_path: Path) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    set_folder(env, folder, keep=3)
    response = env.client.post("/api/backup/auto/run")
    assert response.status_code == 200, response.text
    assert response.json()["last_auto_at"].endswith("Z")
    assert len(list(folder.glob("vocab-coach-backup-*.zip"))) == 1
    assert [e.payload["kind"] for e in backup_events(env)] == ["auto"]


def test_run_now_refusals(env: ApiEnv, tmp_path: Path) -> None:
    response = env.client.post("/api/backup/auto/run")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "backup_not_configured"
    folder = tmp_path / "cloud"
    folder.mkdir()
    set_folder(env, folder)
    with Session(env.engine) as session:
        write_demo_marker(session, DemoMarker(dataset_version=1, seed=1, days=1, anchor=NOW.date()))
        session.commit()
    response = env.client.post("/api/backup/auto/run")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "demo_read_only"
    assert env.client.get("/api/backup/status").json()["demo"] is True


def test_a_failed_copy_is_reported_in_the_status(env: ApiEnv, tmp_path: Path) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    set_folder(env, folder)
    folder.rmdir()  # the folder disappears after it was accepted
    response = env.client.post("/api/backup/auto/run")
    assert response.status_code == 200
    assert response.json()["last_auto_error"] == "not_found"
    assert not backup_events(env)


@pytest.mark.parametrize(
    ("kind", "reason"),
    [("relative", "not_absolute"), ("missing", "not_found"), ("repository", "inside_repository")],
)
def test_the_folder_setting_is_checked(env: ApiEnv, tmp_path: Path, kind: str, reason: str) -> None:
    if kind == "relative":
        value = "some/folder"
    elif kind == "missing":
        value = str(tmp_path / "nope")
    else:
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        value = str(tmp_path / "repo")
    response = env.client.patch("/api/settings", json={"backup_auto_folder": value})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_setting" and detail["reason"] == reason
    stored = env.client.get("/api/settings").json()["backup_auto_folder"]
    assert stored["value"] == ""  # all or nothing


def test_not_writable_folder(env: ApiEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(backup_auto.tempfile, "TemporaryFile", refuse)
    response = env.client.patch("/api/settings", json={"backup_auto_folder": str(tmp_path)})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "not_writable"


def test_the_keep_setting_has_bounds(env: ApiEnv) -> None:
    for bad in (0, 61):
        response = env.client.patch("/api/settings", json={"backup_auto_keep": bad})
        assert response.status_code == 422
    assert env.client.patch("/api/settings", json={"backup_auto_keep": 60}).status_code == 200


def test_ending_a_session_makes_a_copy_when_a_folder_is_set(env: ApiEnv, tmp_path: Path) -> None:
    folder = tmp_path / "cloud"
    folder.mkdir()
    session_id = start_session(env.client)
    assert env.client.post(f"/api/session/{session_id}/end").status_code == 200
    assert not list(folder.iterdir())  # no folder set: nothing happens
    set_folder(env, folder)
    session_id = start_session(env.client)
    assert env.client.post(f"/api/session/{session_id}/end").status_code == 200
    assert len(list(folder.glob("vocab-coach-backup-*.zip"))) == 1


def test_reading_statistics_writes_nothing(env: ApiEnv) -> None:
    add_sample(env.engine)
    with Session(env.engine) as session:
        before = session.scalar(select(func.count()).select_from(EventLog))
    assert env.client.get("/api/stats/overview").status_code == 200
    with Session(env.engine) as session:
        assert session.scalar(select(func.count()).select_from(EventLog)) == before
