"""Application settings, read from environment variables and the repository-level `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repository root is two levels above `app/`.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The API must never be reachable from the network: it holds personal data and API keys.
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

DATABASE_FILENAME = "vocab-coach.sqlite3"
# Demo mode (`VOCAB_DEMO=1`, `python -m app --demo`) uses its own file: the personal database is
# never touched.
DEMO_DATABASE_FILENAME = "vocab-coach-demo.sqlite3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="VOCAB_",
        extra="ignore",
    )

    app_name: str = "vocab-coach"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    data_dir: Path = REPO_ROOT / "data"
    # SQLAlchemy URL. Empty means `<data_dir>/vocab-coach.sqlite3`, resolved as an absolute path
    # so the result does not depend on the current directory (the backend runs from `backend/`).
    database_url: str = ""
    # Demo mode: the default database becomes `<data_dir>/vocab-coach-demo.sqlite3`.
    demo: bool = False
    # Origins allowed to call the API during development (Vite dev server).
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    # AI providers (M2). Empty or missing means "not configured". Keys never leave the backend.
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    ollama_base_url: str | None = None
    # Model overrides (M2.b). Empty or missing means "the adapter's default model".
    gemini_model: str | None = None
    groq_text_model: str | None = None
    groq_transcription_model: str | None = None
    ollama_model: str | None = None

    @field_validator(
        "gemini_api_key",
        "groq_api_key",
        "ollama_base_url",
        "gemini_model",
        "groq_text_model",
        "groq_transcription_model",
        "ollama_model",
        mode="before",
    )
    @classmethod
    def empty_means_not_configured(cls, value: object) -> object:
        # `VOCAB_GROQ_API_KEY=` in .env arrives as an empty string.
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("host")
    @classmethod
    def host_must_be_loopback(cls, value: str) -> str:
        if value not in ALLOWED_HOSTS:
            raise ValueError(
                f"VOCAB_HOST={value!r} is not allowed: the backend only listens on loopback "
                f"({', '.join(sorted(ALLOWED_HOSTS))})."
            )
        return value

    @model_validator(mode="after")
    def demo_excludes_database_url(self) -> "Settings":
        if self.demo and self.database_url:
            raise ValueError(
                "VOCAB_DEMO and VOCAB_DATABASE_URL are both set: the target database would be "
                "ambiguous. Unset VOCAB_DATABASE_URL to use the demo database, or VOCAB_DEMO to "
                "use that URL."
            )
        return self

    def secret_values(self) -> list[str]:
        """Every configured secret value, for masking error messages (see app/ai/redact.py)."""
        keys = (self.gemini_api_key, self.groq_api_key)
        return [key.get_secret_value() for key in keys if key is not None]

    @property
    def resolved_data_dir(self) -> Path:
        """`data_dir` as an absolute path; a relative value is taken from the repository root."""
        path = self.data_dir if self.data_dir.is_absolute() else REPO_ROOT / self.data_dir
        return path.resolve()

    @property
    def demo_database_file(self) -> Path:
        """Where the demo database lives, whatever the mode: `demo` commands only ever use it."""
        return self.resolved_data_dir / DEMO_DATABASE_FILENAME

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        personal = self.resolved_data_dir / DATABASE_FILENAME
        db_file = self.demo_database_file if self.demo else personal
        return f"sqlite:///{db_file.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
