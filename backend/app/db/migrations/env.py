"""Alembic environment: URL from the application settings, batch mode for SQLite."""

from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.engine import create_db_engine
from app.db.migrate import resolve_url
from app.db.types import UTCDateTime

config = context.config

# Only configure logging when run from the `alembic` command line, not when called from the app.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Render project types with a proper import instead of a dotted path."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from app.db.types import UTCDateTime")
        return "UTCDateTime()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_url(config),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(resolve_url(config))
    try:
        with engine.connect() as connection:
            # SQLite cannot ALTER most things: batch mode copies and recreates tables instead.
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
                render_item=render_item,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
