"""Round trip of a full backup (M10.a): demo database -> archive -> empty database."""

from pathlib import Path

from sqlalchemy import Engine

from app.db import migrate
from app.db.engine import create_db_engine
from app.services.backup_restore import restore_backup
from tests.backup_support import (
    NOW,
    audio_files,
    full_fingerprint,
    make_archive,
    sqlite_url,
)
from tests.stats_support import make_client


def overview(engine: Engine) -> dict:
    """`GET /api/stats/overview` at a fixed instant."""
    with make_client(engine, NOW) as client:
        response = client.get("/api/stats/overview")
        assert response.status_code == 200
        return response.json()


def test_round_trip_is_exact(demo_engine: Engine, demo_source: Path, tmp_path: Path) -> None:
    work = tmp_path / "source"
    archive = tmp_path / "backup.zip"
    manifest = make_archive(demo_engine, work / "audio-demo", archive)
    assert manifest["demo"] is True
    assert manifest["tables"]["event_log"] > 100
    assert manifest["files"]

    target = tmp_path / "restored" / "demo.sqlite3"
    target.parent.mkdir()
    migrate.upgrade(sqlite_url(target))
    result = restore_backup(
        archive, db_file=target, audio_dir=tmp_path / "restored" / "audio-demo", demo=True
    )
    assert result.rows == sum(manifest["tables"].values())
    restored = create_db_engine(sqlite_url(target))
    try:
        assert full_fingerprint(restored) == full_fingerprint(demo_engine)
        assert overview(demo_engine) == overview(restored)
    finally:
        restored.dispose()
    assert audio_files(tmp_path / "restored" / "audio-demo") == audio_files(work / "audio-demo")
    assert audio_files(work / "audio-demo")
