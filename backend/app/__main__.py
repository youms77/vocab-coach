"""`uv run python -m app [--reload]` runs the API (loopback only); `python -m app db --help` for the
database commands. See app/cli.py."""

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main())
