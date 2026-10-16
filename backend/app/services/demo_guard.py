"""Is the application running on demo data? Writes that would touch the owner's real setup (keys in
`.env`, provider order) are refused then, because the demo database is a sandbox (D-064)."""

from sqlalchemy import Engine

from app.config import Settings
from app.db.demo_marker import has_demo_marker
from app.db.engine import sqlite_file


def is_demo(settings: Settings, engine: Engine) -> bool:
    if settings.demo:
        return True
    db_file = sqlite_file(engine.url.render_as_string(hide_password=False))
    if db_file is not None and not db_file.exists():
        return False  # do not create an empty file just by looking
    try:
        return has_demo_marker(engine)
    except Exception:
        return False
