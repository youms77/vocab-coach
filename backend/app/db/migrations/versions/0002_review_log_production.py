"""review_log.production_attempt_id: the sentence production a review rated (milestone M5.a1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17

Written by hand (D-127):
- SQLite cannot add a named foreign key to an existing table, so batch mode recreates
  `review_log`. Foreign keys are on during migrations (`app/db/engine.py`): dropping the old table
  runs `ON DELETE SET NULL` on `error_event.review_log_id`. Both directions therefore save those
  links in a temporary table first and put them back afterwards;
- a unique index keeps one review per production.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_review_log_production_attempt_id"
FOREIGN_KEY = "fk_review_log_production_attempt_id_production_attempt"


def _save_review_links() -> None:
    op.execute(
        "CREATE TEMPORARY TABLE _review_links AS "
        "SELECT id, review_log_id FROM error_event WHERE review_log_id IS NOT NULL"
    )


def _restore_review_links() -> None:
    op.execute(
        "UPDATE error_event SET review_log_id = "
        "(SELECT review_log_id FROM _review_links WHERE _review_links.id = error_event.id) "
        "WHERE id IN (SELECT id FROM _review_links)"
    )
    op.execute("DROP TABLE _review_links")


def upgrade() -> None:
    _save_review_links()
    with op.batch_alter_table("review_log") as batch:
        batch.add_column(sa.Column("production_attempt_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            FOREIGN_KEY,
            "production_attempt",
            ["production_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(INDEX, ["production_attempt_id"], unique=True)
    _restore_review_links()


def downgrade() -> None:
    _save_review_links()
    with op.batch_alter_table("review_log") as batch:
        batch.drop_index(INDEX)
        batch.drop_constraint(FOREIGN_KEY, type_="foreignkey")
        batch.drop_column("production_attempt_id")
    _restore_review_links()
