"""`python -m app stats errors | memory | export` (M9.a): output, read-only, exit codes."""

import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.cli import main
from app.cli_stats import (
    run_stats_errors,
    run_stats_export,
    run_stats_memory,
    run_stats_summary,
)
from app.config import get_settings
from app.domain.stats.common import Granularity
from tests.stats_support import NOW, add_sample, counts


@pytest.fixture
def sample(engine: Engine) -> Engine:
    add_sample(engine)
    return engine


def test_stats_errors_prints_rates_top_and_trends(db_url: str, sample: Engine) -> None:
    lines: list[str] = []
    before = counts(sample)
    code = run_stats_errors(db_url, now=NOW, out=lines.append)
    assert code == 0
    text = lines[0]
    assert "Errors from 2026-08-03 to 2026-09-01 (study days, by day)" in text
    assert "Overall: 0.50 per 100 words (3 errors / 600 words)" in text
    assert "Outside the rates: 1 (drill 1)" in text
    assert '1. "in campus" -> "on campus" (grammar.preposition.fixed_expression) x2' in text
    assert "Share of fixed errors" in text
    assert counts(sample) == before


def test_stats_errors_by_week(db_url: str, sample: Engine) -> None:
    lines: list[str] = []
    assert run_stats_errors(db_url, granularity=Granularity.WEEK, now=NOW, out=lines.append) == 0
    assert "by week" in lines[0] and "2026-08-17      600      3  0.50" in lines[0]


def test_stats_memory(db_url: str, sample: Engine) -> None:
    lines: list[str] = []
    before = counts(sample)
    assert run_stats_memory(db_url, now=NOW, out=lines.append) == 0
    text = lines[0]
    assert "Observed retention (cards in Review): 90.0 % (9 of 10 reviews), target 0.85" in text
    assert "typed_recall" in text and "Lapses: 1" in text and "hinge on: 1" in text
    assert counts(sample) == before


def test_an_invalid_period_is_a_usage_error(
    db_url: str, sample: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import date

    code = run_stats_errors(db_url, date(2026, 9, 2), date(2026, 9, 1), now=NOW, out=print)
    assert code == 2
    assert "is after" in capsys.readouterr().err


def test_no_database_is_a_usage_error(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'missing.sqlite3').as_posix()}"
    assert run_stats_memory(url, now=NOW, out=print) == 2
    assert run_stats_export(url, tmp_path, now=NOW, out=print) == 2
    assert not (tmp_path / "missing.sqlite3").exists()


def test_export_to_the_default_folder_then_refuse_then_force(
    db_url: str, sample: Engine, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    lines: list[str] = []
    assert run_stats_export(db_url, data_dir, now=NOW, out=lines.append) == 0
    target = data_dir / "exports" / "vocab-coach-export-20260901.zip"
    assert target.exists()
    assert "review_log" in "\n".join(lines)
    with zipfile.ZipFile(target) as archive:
        assert "manifest.json" in archive.namelist()
    first = target.stat().st_mtime_ns
    assert run_stats_export(db_url, data_dir, now=NOW, out=lines.append) == 2  # already there
    assert target.stat().st_mtime_ns == first
    assert run_stats_export(db_url, data_dir, target, force=True, now=NOW, out=print) == 0
    assert [p.name for p in target.parent.iterdir()] == [target.name]  # no temporary file left


def test_main_parses_the_stats_commands(
    db_url: str, sample: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOCAB_DATABASE_URL", db_url)
    monkeypatch.delenv("VOCAB_DEMO", raising=False)
    get_settings.cache_clear()
    try:
        assert main(["stats", "errors", "--from", "2026-08-01", "--granularity", "week"]) == 0
        assert main(["stats", "export", "--out", str(tmp_path / "x.zip")]) == 0
        assert (tmp_path / "x.zip").exists()
        with pytest.raises(SystemExit) as exc:
            main(["stats", "memory", "--from", "2026-13-01"])
        assert exc.value.code == 2
    finally:
        get_settings.cache_clear()


def test_stats_summary(db_url: str, sample: Engine) -> None:
    lines: list[str] = []
    before = counts(sample)
    assert run_stats_summary(db_url, now=NOW, out=lines.append) == 0
    text = lines[0]
    assert "Summary on 2026-09-01" in text
    assert "Errors, last 28 study days:     0.50 per 100 words (3 errors / 600 words)" in text
    assert "Errors, the 28 days before:     n/a (0 errors / 0 words: too few words)" in text
    assert "90.0 % (9 of 10 reviews), target 0.85 (now 0.85)" in text
    assert "Active terms:                   0 of 1 terms" in text
    assert counts(sample) == before


def test_main_runs_the_summary(
    db_url: str, sample: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOCAB_DATABASE_URL", db_url)
    monkeypatch.delenv("VOCAB_DEMO", raising=False)
    get_settings.cache_clear()
    try:
        assert main(["stats", "summary"]) == 0
    finally:
        get_settings.cache_clear()
