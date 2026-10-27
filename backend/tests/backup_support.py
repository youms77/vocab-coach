"""Shared helpers of the backup tests (M10.a)."""

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.db.base import Base
from app.db.engine import create_db_engine
from app.demo.seed import seed_demo
from app.services import backup

DEMO_ANCHOR = "2026-09-01"
NOW = datetime(2026, 9, 2, 8, 30, tzinfo=UTC)


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def full_fingerprint(engine: Engine, skip: tuple[str, ...] = ()) -> str:
    """SHA-256 of every table as SQLite stores it, **clock columns included**."""
    digest = hashlib.sha256()
    with engine.connect() as connection:
        for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
            if table.name in skip:
                continue
            order = ", ".join(f'"{c.name}"' for c in table.primary_key.columns)
            names = ", ".join(f'"{c.name}"' for c in table.columns)
            digest.update(table.name.encode())
            sql = f'SELECT {names} FROM "{table.name}" ORDER BY {order}'  # noqa: S608
            for row in connection.exec_driver_sql(sql):
                digest.update(json.dumps(list(row), default=str).encode())
    return digest.hexdigest()


def audio_files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def make_archive(engine: Engine, audio_root: Path, target: Path, **kwargs: object) -> dict:
    with target.open("wb") as stream:
        info = backup.write_backup(engine, NOW, audio_root, stream, **kwargs)  # type: ignore[arg-type]
    return info.manifest


def read_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_members(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def with_manifest(members: dict[str, bytes], change: Callable[[dict], None]) -> dict[str, bytes]:
    manifest = json.loads(members["manifest.json"])
    change(manifest)
    return {**members, "manifest.json": json.dumps(manifest).encode()}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def memory_zip(members: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer


@pytest.fixture(scope="session")
def demo_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The demo database (seed 42, 60 days, fixed anchor) and its recordings, built once."""
    folder = tmp_path_factory.mktemp("demo-source")
    from datetime import date

    seed_demo(
        folder / "demo.sqlite3",
        seed=42,
        days=60,
        anchor=date.fromisoformat(DEMO_ANCHOR),
        audio_dir=folder / "audio-demo",
    )
    return folder


@pytest.fixture
def demo_engine(demo_source: Path, tmp_path: Path) -> Engine:
    """A private copy of the demo database, so a test may write into it."""
    import shutil

    work = tmp_path / "source"
    shutil.copytree(demo_source, work)
    engine = create_db_engine(sqlite_url(work / "demo.sqlite3"))
    yield engine  # type: ignore[misc]
    engine.dispose()
