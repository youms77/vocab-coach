"""`python -m app demo seed`: build the demo database atomically, behind safety checks (D-033).

The database is built in a temporary file next to the target (migrations, taxonomy, simulation,
marker), and the demo's recordings in a temporary folder next to `audio-demo/` (D-188). Then:

1. the previous `audio-demo/` is renamed `audio-demo.old-<pid>` (refused while a program holds one
   of its files open on Windows: nothing has changed yet);
2. the new database is moved over the target (refused while the app holds it open on Windows: the
   previous recordings are put back);
3. the temporary folder becomes `audio-demo/`, and the old one is deleted.

A failure leaves the previous database and recordings untouched and removes the temporary file and
folder. `audio_path` is relative to the folder, so it stays valid once the folder is renamed. The
command never targets the personal database: the CLI always passes the demo path; tests pass an
explicit temporary URL.
"""

import contextlib
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.orm import Session

from app.db import migrate
from app.db.base import Base
from app.db.demo_marker import DemoMarker, read_demo_marker, write_demo_marker
from app.db.engine import create_db_engine, sqlite_file
from app.db.models import Card, ErrorCategory, ErrorEvent, LexicalItem
from app.db.settings_store import get_setting
from app.db.taxonomy import sync_taxonomy
from app.demo.dataset import DemoDataset, load_dataset
from app.demo.simulation import SimulationConfig, simulate
from app.domain.study_day import study_day_of
from app.speech.audio_store import DEMO_AUDIO_DIR

DEFAULT_SEED = 42
DEFAULT_DAYS = 60
SQLITE_SIDE_FILES = ("-wal", "-shm")
# Tables filled by `db upgrade` itself: their rows are not user data.
INFRASTRUCTURE_TABLES = frozenset({"alembic_version", ErrorCategory.__tablename__})


class DemoSeedError(Exception):
    """The seed was refused or could not complete; the message says what to do."""


@dataclass
class SeedSummary:
    path: Path
    marker: DemoMarker
    seconds: float
    rows: dict[str, int] = field(default_factory=dict)
    items_by_status: dict[str, int] = field(default_factory=dict)
    cards_by_state: dict[str, int] = field(default_factory=dict)
    errors_by_top_category: dict[str, int] = field(default_factory=dict)
    errors_by_category: dict[str, int] = field(default_factory=dict)
    audio_dir: Path | None = None
    recordings: int = 0


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _side_files(path: Path) -> list[Path]:
    return [path.with_name(path.name + suffix) for suffix in SQLITE_SIDE_FILES]


def _remove_quietly(path: Path) -> None:
    for candidate in (path, *_side_files(path)):
        with contextlib.suppress(OSError):
            candidate.unlink(missing_ok=True)


def _remove_tree(path: Path) -> None:
    """Delete a folder; a file another program holds open on Windows stays behind."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def user_data_tables(engine: Engine) -> list[str]:
    """Tables (other than migrations and taxonomy) that hold at least one row."""
    present = set(inspect(engine).get_table_names())
    filled = []
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name in INFRASTRUCTURE_TABLES or table.name not in present:
                continue
            if connection.execute(select(func.count()).select_from(table)).scalar_one():
                filled.append(table.name)
    return sorted(filled)


def check_target(path: Path, *, reset: bool) -> bool:
    """Refuse a database we must not overwrite. Returns True when it already holds demo data."""
    if not path.exists():
        return False
    engine = create_db_engine(sqlite_url(path))
    try:
        if not inspect(engine).has_table("setting"):
            marked = False
        else:
            with Session(engine) as session:
                marked = read_demo_marker(session) is not None
        filled = [] if marked else user_data_tables(engine)
    finally:
        engine.dispose()
    if filled:
        raise DemoSeedError(
            f"{path} holds data without the demo marker ({', '.join(filled)}). It may be a "
            "personal database: nothing was changed."
        )
    if marked and not reset:
        raise DemoSeedError(
            f"{path} already holds demo data. Nothing was changed. Use `demo seed --reset` to "
            "rebuild it."
        )
    return marked


def is_seeded(path: Path) -> bool:
    if not path.exists():
        return False
    engine = create_db_engine(sqlite_url(path))
    try:
        if not inspect(engine).has_table("setting"):
            return False
        with Session(engine) as session:
            return read_demo_marker(session) is not None
    finally:
        engine.dispose()


def _build(
    url: str,
    dataset: DemoDataset,
    seed: int,
    days: int,
    anchor: date | None,
    audio_dir: Path,
) -> DemoMarker:
    migrate.upgrade(url)
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            sync_taxonomy(session)
            dataset.check_codes(session.scalars(select(ErrorCategory.code)))
            if anchor is None:
                tz = ZoneInfo(get_setting(session, "timezone"))
                anchor = study_day_of(datetime.now(UTC), tz, get_setting(session, "day_start_hour"))
            marker = DemoMarker(
                dataset_version=dataset.dataset_version, seed=seed, days=days, anchor=anchor
            )
            config = SimulationConfig(seed=seed, days=days, anchor=anchor)
            simulate(session, dataset, config, audio_dir=audio_dir)
            write_demo_marker(session, marker)
            session.commit()
        with engine.connect() as connection:
            # Fold the write-ahead log into the file before it is moved.
            connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    finally:
        engine.dispose()
    return marker


def _replace(temporary: Path, target: Path) -> None:
    try:
        # A leftover log of the previous file would be replayed into the new one.
        for side in _side_files(target):
            side.unlink(missing_ok=True)
        os.replace(temporary, target)
    except PermissionError as exc:
        raise DemoSeedError(
            f"Cannot replace {target}: the file is in use ({exc}). Stop the app (Ctrl+C in its "
            "window) and run the command again. The previous demo database is unchanged."
        ) from exc


def _swap(db_temporary: Path, db_target: Path, audio_temporary: Path, audio_dir: Path) -> None:
    """Put the new database and the new recordings in place, or neither (see the docstring)."""
    old = audio_dir.with_name(f"{audio_dir.name}.old-{os.getpid()}")
    _remove_tree(old)
    set_aside = False
    if audio_dir.exists():
        try:
            os.replace(audio_dir, old)
        except PermissionError as exc:
            raise DemoSeedError(
                f"Cannot replace {audio_dir}: a recording is in use ({exc}). Close the program "
                "playing it, or stop the app, and run the command again. The previous demo "
                "database and recordings are unchanged."
            ) from exc
        set_aside = True
    try:
        _replace(db_temporary, db_target)
    except BaseException:
        if set_aside:
            os.replace(old, audio_dir)
        raise
    if audio_temporary.exists():
        try:
            os.replace(audio_temporary, audio_dir)
        except OSError as exc:  # rare: the folder was locked between the two renames
            if set_aside:
                os.replace(old, audio_dir)
            raise DemoSeedError(
                f"The new demo database is in place, but its recordings could not be moved into "
                f"{audio_dir} ({exc}). Run `demo seed --reset` again."
            ) from exc
    _remove_tree(old)


def seed_demo(
    target: Path,
    *,
    seed: int = DEFAULT_SEED,
    days: int = DEFAULT_DAYS,
    anchor: date | None = None,
    reset: bool = False,
    dataset: DemoDataset | None = None,
    audio_dir: Path | None = None,
) -> SeedSummary:
    """Build the demo database at `target` (a SQLite file) and its recordings in `audio_dir`
    (default: `audio-demo/` next to the database). Raises DemoSeedError when refused."""
    started = time.perf_counter()
    target = target.resolve()
    check_target(target, reset=reset)
    dataset = dataset or load_dataset()
    audio_dir = (audio_dir or target.parent / DEMO_AUDIO_DIR).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    audio_temporary = audio_dir.with_name(f"{audio_dir.name}.tmp-{os.getpid()}")
    _remove_quietly(temporary)
    _remove_tree(audio_temporary)
    try:
        marker = _build(sqlite_url(temporary), dataset, seed, days, anchor, audio_temporary)
        for side in _side_files(temporary):
            side.unlink(missing_ok=True)
        _swap(temporary, target, audio_temporary, audio_dir)
    finally:
        _remove_quietly(temporary)
        _remove_tree(audio_temporary)
    summary = summarize(sqlite_url(target), marker)
    summary.path = target
    summary.audio_dir = audio_dir
    summary.recordings = (
        sum(1 for p in audio_dir.rglob("*") if p.is_file()) if audio_dir.is_dir() else 0
    )
    summary.seconds = time.perf_counter() - started
    return summary


def summarize(url: str, marker: DemoMarker) -> SeedSummary:
    db_file = sqlite_file(url)
    engine = create_db_engine(url)
    try:
        with engine.connect() as connection:
            rows = {
                table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
                for table in Base.metadata.sorted_tables
            }
        with Session(engine) as session:
            items = Counter(str(s) for s in session.scalars(select(LexicalItem.status)))
            cards = Counter(str(s) for s in session.scalars(select(Card.srs_state)))
            codes = list(
                session.scalars(
                    select(ErrorCategory.code).join(
                        ErrorEvent, ErrorEvent.category_id == ErrorCategory.id
                    )
                )
            )
    finally:
        engine.dispose()
    return SeedSummary(
        path=db_file or Path(url),
        marker=marker,
        seconds=0.0,
        rows=dict(sorted(rows.items())),
        items_by_status=dict(sorted(items.items())),
        cards_by_state=dict(sorted(cards.items())),
        errors_by_top_category=_by_prefix(codes, 1),
        errors_by_category=_by_prefix(codes, 2),
    )


def _by_prefix(codes: list[str], depth: int) -> dict[str, int]:
    """Error counts by taxonomy level (1 = grammar, lexis...; 2 = grammar.preposition...)."""
    counts = Counter(".".join(code.split(".")[:depth]) for code in codes)
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def render_summary(summary: SeedSummary) -> str:
    """Readable summary for the terminal (developer tool: English, no i18n)."""
    marker = summary.marker
    lines = [
        f"Demo database ready: {summary.path}",
        f"Dataset v{marker.dataset_version}, seed {marker.seed}, {marker.days} days up to "
        f"{marker.anchor.isoformat()} (anchor study day), built in {summary.seconds:.1f} s.",
    ]
    if summary.audio_dir is not None:
        lines.append(f"Recordings: {summary.recordings} files in {summary.audio_dir}")
    lines += [
        "",
        "Rows per table:",
        *(f"  {name:<26}{count:>7}" for name, count in summary.rows.items() if count),
        "Terms by status: " + _inline(summary.items_by_status),
        "Cards by state: " + _inline(summary.cards_by_state),
        "Errors by category (level 1): " + _inline(summary.errors_by_top_category),
        "Errors by category (level 2): " + _inline(summary.errors_by_category),
    ]
    return "\n".join(lines)


def _inline(counts: dict[str, int]) -> str:
    return ", ".join(f"{key} {value}" for key, value in counts.items()) or "none"
