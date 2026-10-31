"""Creating a backup (M10.a): content, exclusions, no key, and nothing written but one event."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base
from app.db.models import EventLog, ProductionAttempt
from app.services import backup
from app.services import backup_format as fmt
from app.services.backup import BackupError
from tests.backup_support import NOW, make_archive, sha
from tests.stats_support import add_sample

GEMINI_KEY = "AIzaTEST-backup-secret-0123456789"
GROQ_KEY = "gsk_TEST_backup_secret_9876543210"


def all_bytes(path: Path) -> list[bytes]:
    """Every member, decompressed, plus the member names."""
    with zipfile.ZipFile(path) as archive:
        return [name.encode() for name in archive.namelist()] + [
            archive.read(name) for name in archive.namelist()
        ]


def test_archive_layout_and_encoding(engine: Engine, tmp_path: Path) -> None:
    add_sample(engine)
    path = tmp_path / "b.zip"
    manifest = make_archive(engine, tmp_path / "audio", path)
    assert manifest["format"] == fmt.FORMAT and manifest["kind"] == "manual"
    assert manifest["alembic_revision"] == "0002" and manifest["demo"] is False
    assert manifest["created_at"] == "2026-09-02T08:30:00.000000Z"
    assert "alembic_version" not in manifest["tables"]
    assert set(manifest["tables"]) == {t.name for t in Base.metadata.sorted_tables}
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"manifest.json", *manifest["files"]}
        for name, entry in manifest["files"].items():
            data = archive.read(name)
            assert sha(data) == entry["sha256"] and len(data) == entry["size"]
        rows = [json.loads(line) for line in archive.read("tables/lexical_item.jsonl").splitlines()]
        table = Base.metadata.tables["lexical_item"]
        assert list(rows[0]) == [c.name for c in table.columns]  # the model's column order
        assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
        assert rows[0]["created_at"].endswith("Z") and "." in rows[0]["created_at"]
        sheets = [json.loads(line) for line in archive.read("tables/enrichment.jsonl").splitlines()]
        assert all(isinstance(r["content"], dict) for r in sheets)  # native JSON, not a string
        assert isinstance(rows[0]["origin_error_event_id"], int | None)


def test_no_key_anywhere_in_the_archive(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOCAB_GEMINI_API_KEY", GEMINI_KEY)
    monkeypatch.setenv("VOCAB_GROQ_API_KEY", GROQ_KEY)
    get_settings.cache_clear()
    try:
        add_sample(engine)
        path = tmp_path / "b.zip"
        make_archive(engine, tmp_path / "audio", path)
    finally:
        get_settings.cache_clear()
    haystack = b"\n".join(all_bytes(path)) + path.read_bytes()
    for key in (GEMINI_KEY, GROQ_KEY):
        assert key.encode() not in haystack
        assert key[-8:].encode() not in haystack


def test_only_referenced_recordings_are_copied_and_missing_ones_listed(
    engine: Engine, tmp_path: Path
) -> None:
    audio = tmp_path / "audio"
    present, absent = "2026/08/" + "a" * 32 + ".webm", "2026/08/" + "b" * 32 + ".webm"
    (audio / "2026" / "08").mkdir(parents=True)
    (audio / present).write_bytes(b"RIFFdata")
    (audio / "2026" / "08" / ("c" * 32 + ".webm")).write_bytes(b"not referenced")
    (tmp_path / "audio-demo").mkdir()
    (tmp_path / "audio-demo" / "other.webm").write_bytes(b"other mode")
    add_sample(engine)
    with Session(engine) as session:
        session.query(ProductionAttempt).limit(1).all()
        attempts = session.scalars(select(ProductionAttempt)).all()
        attempts[0].audio_path = present
        attempts[1].audio_path = absent
        session.commit()
    path = tmp_path / "b.zip"
    manifest = make_archive(engine, audio, path)
    audio_members = [n for n in manifest["files"] if n.startswith("audio/")]
    assert audio_members == [f"audio/{present}"]
    assert manifest["missing_audio"] == [absent]
    assert not any(b"other mode" in blob or b"not referenced" in blob for blob in all_bytes(path))


def test_creating_a_backup_writes_only_one_event(engine: Engine, tmp_path: Path) -> None:
    add_sample(engine)

    def snapshot() -> dict[str, list[tuple]]:
        with engine.connect() as connection:
            return {
                t.name: [tuple(r) for r in connection.exec_driver_sql(f'SELECT * FROM "{t.name}"')]  # noqa: S608
                for t in Base.metadata.sorted_tables
                if t.name != "event_log"
            }

    before = snapshot()
    with Session(engine) as session:
        events_before = session.scalar(select(func.count()).select_from(EventLog))
    path = tmp_path / "b.zip"
    with path.open("wb") as stream:
        info = backup.write_backup(engine, NOW, tmp_path / "audio", stream)
    backup.record_created(engine, info, NOW)
    assert snapshot() == before
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(EventLog)) == events_before + 1
        event = session.scalars(select(EventLog).order_by(EventLog.id.desc())).first()
    assert event is not None and event.event_type == "backup.created"
    assert set(event.payload) >= {"kind", "tables", "rows", "audio_files", "bytes"}
    assert event.payload["rows"] == info.rows
    assert not any(isinstance(v, str) and ("/" in v or "\\" in v) for v in event.payload.values())
    # The event describes the archive without being in it.
    members = zipfile.ZipFile(path).read("tables/event_log.jsonl").decode()
    assert "backup.created" not in members


def test_a_database_that_is_not_up_to_date_cannot_be_backed_up(
    engine: Engine, tmp_path: Path
) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '0001'")
    with pytest.raises(BackupError) as caught:
        backup.write_backup(engine, NOW, tmp_path, io.BytesIO())
    assert caught.value.code == "database_out_of_date"
