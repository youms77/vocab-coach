"""Shared fixtures: every database test runs on a temporary SQLite file built by the migrations."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.engine import create_db_engine


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = sqlite_url(tmp_path / "test.sqlite3")
    migrate.upgrade(url)
    return url


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
