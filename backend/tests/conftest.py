"""Shared fixtures: every database test runs on a temporary SQLite file built by the migrations."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import migrate
from app.db.engine import create_db_engine, get_engine
from app.main import create_app
from tests.backup_support import demo_engine, demo_source  # noqa: F401  (fixtures of the backup tests)


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


def make_api_client(engine: Engine) -> TestClient:
    """A client on the application, talking to the loopback address the API guard expects."""
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}")


@pytest.fixture
def api_client(engine: Engine) -> TestClient:
    return make_api_client(engine)


@pytest.fixture(autouse=True)
def no_startup_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API's startup copy (M10.a) would look at the real `data/` folder: off in every test
    (`test_startup_hook_runs_in_the_lifespan` turns it back on with a spy)."""
    monkeypatch.setattr("app.main.startup_backup", lambda settings: None)
