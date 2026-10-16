"""Run Alembic from the application (CLI, tests, health check)."""

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def alembic_config(url: str | None = None) -> Config:
    """Alembic config for `url` (default: the application database)."""
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    if url is not None:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def resolve_url(config: Config) -> str:
    """URL passed by the caller (tests, CLI) or, failing that, the application settings."""
    return config.get_main_option("sqlalchemy.url") or get_settings().resolved_database_url


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


@dataclass(frozen=True)
class SchemaStatus:
    revision: str | None
    head: str | None

    @property
    def at_head(self) -> bool:
        return self.revision is not None and self.revision == self.head


def schema_status(engine: Engine) -> SchemaStatus:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    return SchemaStatus(revision=revision, head=head)
