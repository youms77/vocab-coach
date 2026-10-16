"""Shared fixtures: every database test runs on a temporary SQLite file built by the migrations."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.engine import create_db_engine


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A database built once by the migrations; each test gets a fresh copy of it."""
    path = tmp_path_factory.mktemp("template") / "template.sqlite3"
    url = sqlite_url(path)
    migrate.upgrade(url)
    engine = create_db_engine(url)
    try:
        with engine.connect() as connection:
            # Fold the write-ahead log into the file so a plain copy is complete.
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        engine.dispose()
    return path


@pytest.fixture
def db_url(tmp_path: Path, migrated_template: Path) -> str:
    path = tmp_path / "test.sqlite3"
    shutil.copyfile(migrated_template, path)
    return sqlite_url(path)


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    engine = create_db_engine(db_url)
    yield engine
    # Windows cannot delete an open SQLite file: close pooled connections before tmp_path cleanup.
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
