"""`read_only` leaves the connection it used writable, even when the pool holds others (M10.b)."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.db.engine import create_db_engine
from app.services.stats import read_only
from tests.backup_support import sqlite_url


@pytest.fixture
def pooled(tmp_path: Path) -> Engine:
    engine = create_db_engine(sqlite_url(tmp_path / "pool.sqlite3"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE t (x INTEGER)"))
    yield engine
    engine.dispose()


def test_every_pooled_connection_is_writable_after_read_only(pooled: Engine) -> None:
    # Three idle connections in the pool: the pool hands them out oldest first, so a statement
    # issued after the session released its connection would not run on the same one.
    held = [pooled.connect() for _ in range(3)]
    for connection in held:
        connection.close()
    with read_only(pooled) as session:
        session.execute(text("SELECT 1"))
        with pytest.raises(Exception, match="readonly"):
            session.execute(text("INSERT INTO t VALUES (1)"))
    again = [pooled.connect() for _ in range(3)]
    try:
        for connection in again:
            assert connection.execute(text("PRAGMA query_only")).scalar() == 0
            connection.execute(text("INSERT INTO t VALUES (2)"))
            connection.commit()
    finally:
        for connection in again:
            connection.close()
