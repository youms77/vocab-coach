"""Run the API with `uv run python -m app` (honours VOCAB_HOST / VOCAB_PORT, loopback only)."""

import sys

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    reload = "--reload" in sys.argv
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=reload)


if __name__ == "__main__":
    main()
