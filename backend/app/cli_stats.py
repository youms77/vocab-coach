"""`python -m app stats errors | memory | export` (module I, M9.a).

Read-only: every command reads in a `PRAGMA query_only` session and writes nothing in the database
(`export` writes only its zip file). `--demo` (before the command) reads the demo database.

Exit codes (D-053): 0 done, 2 usage error (invalid dates, no database or not up to date, target
file already there without `--force`).
"""

import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from app.cli_errors import _console_safe
from app.cli_library import EXIT_OK, EXIT_USAGE, _open
from app.db.base import utcnow
from app.domain.stats.common import Granularity, InvalidPeriod, Rate, Share
from app.domain.stats.errors import Trend
from app.services import export, stats
from app.services.stats import read_only

Out = Callable[[str], None]


def _rate(rate: Rate) -> str:
    if rate.value is None:
        return f"n/a ({rate.errors} errors / {rate.words} words: too few words)"
    return f"{rate.value:.2f} per 100 words ({rate.errors} errors / {rate.words} words)"


def _share(value: Share, what: str = "") -> str:
    counts = f"{value.successes} of {value.n}{what}"
    if value.value is None:
        return f"n/a ({counts}: too few)"
    return f"{100 * value.value:.1f} % ({counts})"


def _short(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _period_line(head: stats.Header, title: str) -> str:
    return (
        f"{title} from {head.start} to {head.end} (study days, by {head.granularity.value}); "
        f"today is {head.study_day}{' - demo data' if head.demo else ''}"
    )


def render_errors(result: stats.ErrorStats) -> str:
    rates = result.rates
    lines = [_period_line(result.header, "Errors"), "", f"Overall: {_rate(rates.rate)}"]
    reasons = ", ".join(f"{k} {v}" for k, v in rates.unnormalized.by_reason.items() if v)
    lines.append(
        f"Outside the rates: {rates.unnormalized.total}" + (f" ({reasons})" if reasons else "")
    )
    for level, rows in ((1, rates.level1), (2, rates.level2)):
        lines += ["", f"By category, level {level}:"]
        lines += [f"  {row.code:<36} {_rate(row.rate)}" for row in rows] or ["  (no error)"]
    lines += ["", f"{'Bucket':<12} {'words':>6} {'errors':>6}  rate per 100 words"]
    for bucket in rates.buckets:
        value = "n/a" if bucket.rate.value is None else f"{bucket.rate.value:.2f}"
        lines.append(f"{bucket.key!s:<12} {bucket.rate.words:>6} {bucket.rate.errors:>6}  {value}")
    lines += ["", "Top 5 recurring errors:"]
    if not result.top_recurring:
        lines.append("  (none: no error seen twice)")
    for rank, item in enumerate(result.top_recurring, 1):
        card = "has a card" if item.has_card else "no card"
        lines.append(
            f'  {rank}. "{item.erroneous_text}" -> "{item.correction}" ({item.category}) '
            f"x{item.count}, {item.first_at:%Y-%m-%d} to {item.last_at:%Y-%m-%d}, {card}"
        )
        lines += [f"     e.g. {example}" for example in item.examples]
    trends = result.trends
    lines += [
        "",
        f"Lasting trends: {trends.window_b.start} to {trends.window_b.end} against "
        f"{trends.window_a.start} to {trends.window_a.end} "
        f"({trends.words_a} -> {trends.words_b} words)",
    ]

    def trend_line(trend: Trend) -> str:
        ratio = "" if trend.ratio is None else f" (x{trend.ratio:.2f})"
        return (
            f"    {trend.code} (level {trend.level}): {trend.window_a.errors} -> "
            f"{trend.window_b.errors} errors, {_short(trend.window_a.value)} -> "
            f"{_short(trend.window_b.value)} per 100 words{ratio}"
        )

    for status in ("declining", "rising", "stable"):
        group = trends.by_status[status]
        lines.append(f"  {status}: {len(group)}")
        lines += [trend_line(trend) for trend in group]
    lines.append(f"  insufficient: {len(trends.by_status['insufficient'])}")
    lines.append(
        "Share of fixed errors (level 2, declining): "
        + _share(trends.fixed_share, " errors of the earlier window")
    )
    return "\n".join(lines)


def render_memory(result: stats.MemoryStats) -> str:
    retention = result.retention
    target = "n/a" if retention.target is None else f"{retention.target:.2f}"
    lines = [
        _period_line(result.header, "Memory"),
        "",
        f"Observed retention (cards in Review): {_share(retention.all, ' reviews')}, "
        f"target {target}",
        f"  receptive {_share(retention.receptive)}, productive {_share(retention.productive)}",
        "",
        "Success by exercise type:",
    ]
    lines += [
        f"  {row.exercise_type:<26} {_share(row.success)}" for row in result.success_by_exercise
    ] or ["  (no review)"]
    agreement = result.rating_agreement
    lines += [
        "",
        f"Proposed ratings changed by you: {_share(agreement.changed)}, "
        f"raised {agreement.raised}, lowered {agreement.lowered}",
        f"Lapses: {result.lapses.total}",
    ]
    lines += [
        f"  {t.term or f'(term {t.item_id}, gone)'}: {t.lapses}" for t in result.top_lapsed_terms
    ]
    lines += ["", "Stability now (days):"]
    for row in result.stability:
        ranges = ", ".join(
            f"[{r.low:g}-{'' if r.high is None else f'{r.high:g}'}): {r.count}" for r in row.ranges
        )
        lines.append(
            f"  {row.direction}: {row.cards} cards, {row.unreviewed} never reviewed; {ranges}"
        )
    delay = result.time_to_consolidation
    lines += ["", f"Time before consolidation: {delay.n} terms consolidated in the period"]
    if delay.n:
        lines.append(
            f"  study days: median {delay.days.median:g} (quartiles {delay.days.q1:g} to "
            f"{delay.days.q3:g}); reviews: median {delay.reviews.median:g} "
            f"(quartiles {delay.reviews.q1:g} to {delay.reviews.q3:g})"
        )
    return "\n".join(lines)


def _run(
    url: str,
    compute: Callable[..., object],
    render: Callable[..., str],
    start: date | None,
    end: date | None,
    granularity: Granularity,
    now: datetime | None,
    out: Out,
) -> int:
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    try:
        with read_only(engine) as session:
            try:
                result = compute(session, now or utcnow(), start, end, granularity)
            except InvalidPeriod as exc:
                print(str(exc), file=sys.stderr)
                return EXIT_USAGE
        out(render(result))
        return EXIT_OK
    finally:
        engine.dispose()


def run_stats_errors(
    url: str,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
    *,
    now: datetime | None = None,
    out: Out = print,
) -> int:
    return _run(url, stats.error_stats, render_errors, start, end, granularity, now, out)


def run_stats_memory(
    url: str,
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = Granularity.DAY,
    *,
    now: datetime | None = None,
    out: Out = print,
) -> int:
    return _run(url, stats.memory_stats, render_memory, start, end, granularity, now, out)


def run_stats_export(
    url: str,
    data_dir: Path,
    target: Path | None = None,
    *,
    force: bool = False,
    now: datetime | None = None,
    out: Out = print,
) -> int:
    """Write the CSV archive; by default `<data_dir>/exports/vocab-coach-export-YYYYMMDD.zip`."""
    _console_safe()
    engine = _open(url)
    if engine is None:
        return EXIT_USAGE
    now = now or utcnow()
    try:
        if target is None:
            with read_only(engine) as session:
                today = stats.context(session, now).today
            target = data_dir / "exports" / export.archive_name(today)
        try:
            result = export.export_archive(engine, now, target, force=force)
        except FileExistsError:
            print(f"{target} already exists. Use --force to replace it.", file=sys.stderr)
            return EXIT_USAGE
    finally:
        engine.dispose()
    total = sum(result.rows.values())
    out(f"Exported {total} rows from {len(result.rows)} tables to {result.path}")
    for name, count in result.rows.items():
        out(f"  {name:<24} {count:>7}")
    out("Read it with pandas: see data_dictionary.md inside the archive.")
    return EXIT_OK
