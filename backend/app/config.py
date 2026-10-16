"""Application settings, read from environment variables and the repository-level `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repository root is two levels above `app/`.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The API must never be reachable from the network: it holds personal data and API keys.
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


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
    # Origins allowed to call the API during development (Vite dev server).
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @field_validator("host")
    @classmethod
    def host_must_be_loopback(cls, value: str) -> str:
        if value not in ALLOWED_HOSTS:
            raise ValueError(
                f"VOCAB_HOST={value!r} is not allowed: the backend only listens on loopback "
                f"({', '.join(sorted(ALLOWED_HOSTS))})."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
