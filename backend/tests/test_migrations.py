from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db import migrate
from app.db.base import Base
from app.db.engine import create_db_engine
from tests.conftest import sqlite_url

EXPECTED_TABLES = {
    "source",
    "deck",
    "deck_item",
    "lexical_item",
    "enrichment",
    "exercise_template",
    "card",
    "review_log",
    "production_attempt",
    "production_target",
    "pronunciation_result",
    "consolidation_task",
    "consolidation_task_item",
    "error_category",
    "error_event",
    "curriculum_track",
    "curriculum_unit",
    "study_session",
    "event_log",
    "ai_call_log",
    "setting",
}


def test_upgrade_creates_every_table(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == EXPECTED_TABLES
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_models_and_migrations_do_not_diverge(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "render_as_batch": True}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_alembic_check_reports_nothing(db_url: str) -> None:
    command.check(migrate.alembic_config(db_url))  # raises if autogenerate finds a difference


def test_partial_index_and_triggers_exist(engine: Engine) -> None:
    with engine.connect() as connection:
        rows = dict(
            connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
            ).all()
        )
    assert "WHERE is_current = 1" in rows["uq_enrichment_current"]
    assert {"event_log_no_update", "event_log_no_delete"} <= rows.keys()
    # One named CHECK per closed enum column (autogenerate once emitted three copies).
    assert rows["deck"].count("CHECK") == 2
    assert rows["deck"].count("CONSTRAINT ck_deck_deck_status CHECK") == 1


def test_downgrade_to_base_then_upgrade_again(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "roundtrip.sqlite3")
    migrate.upgrade(url)
    migrate.downgrade(url, "base")
    engine = create_db_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        migrate.upgrade(url)
        inspector = inspect(engine)
        inspector.clear_cache()
        assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
        assert migrate.schema_status(engine).at_head
    finally:
        engine.dispose()


def test_pragmas_are_set_on_every_connection(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_0002_keeps_the_links_from_errors_to_reviews(tmp_path: Path) -> None:
    """Migration 0002 recreates `review_log` with foreign keys on: the `ON DELETE SET NULL` of
    `error_event.review_log_id` must not erase the links (D-127)."""
    url = sqlite_url(tmp_path / "links.sqlite3")
    migrate.upgrade(url, "0001")
    engine = create_db_engine(url)

    def links() -> list[tuple[int, int | None]]:
        with engine.connect() as connection:
            return [
                (row[0], row[1])
                for row in connection.execute(
                    text("SELECT id, review_log_id FROM error_event ORDER BY id")
                )
            ]

    try:
        with engine.begin() as connection:
            for statement in (
                "INSERT INTO lexical_item (id, term, normalized_form, item_type, status, "
                "status_changed_at, created_at, updated_at) VALUES (1, 'effect', 'effect', "
                "'word', 'learning', '2026-10-16', '2026-10-16', '2026-10-16')",
                "INSERT INTO card (id, lexical_item_id, direction, srs_state, due, created_at, "
                "updated_at) VALUES (1, 1, 'productive', 'learning', '2026-10-16', '2026-10-16', "
                "'2026-10-16')",
                "INSERT INTO review_log (id, card_id, reviewed_at, exercise_type, final_rating, "
                "state_before, state_after, due_after, scheduled_days, srs_algorithm) VALUES "
                "(7, 1, '2026-10-16', 'typed_recall', 1, 'learning', 'learning', '2026-10-17', "
                "1, 'fsrs')",
                "INSERT INTO error_category (id, code, label_en, label_fr, description_en, "
                "description_fr, examples, is_builtin, status, sort_order, created_at, updated_at) "
                "VALUES (1, 'lexis', 'Lexis', 'Lexique', '', '', '[]', 1, 'active', 0, "
                "'2026-10-16', '2026-10-16')",
                "INSERT INTO error_event (id, review_log_id, source, original_text, "
                "erroneous_text, correction, alternatives, explanation, category_id, "
                "occurred_at, created_at, updated_at) VALUES "
                "(3, 7, 'review', '', 'affect', 'effect', '[]', '', 1, "
                "'2026-10-16', '2026-10-16', '2026-10-16'), "
                "(4, NULL, 'manual', '', 'a', 'b', '[]', '', 1, "
                "'2026-10-16', '2026-10-16', '2026-10-16')",
            ):
                connection.execute(text(statement))
        migrate.upgrade(url)
        assert links() == [(3, 7), (4, None)]
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("review_log")}
            assert "production_attempt_id" in columns
        migrate.downgrade(url, "0001")
        assert links() == [(3, 7), (4, None)]
    finally:
        engine.dispose()
