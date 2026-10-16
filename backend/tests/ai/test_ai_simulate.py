"""`python -m app ai simulate`: three scenarios, offline, never on the personal database."""

from pathlib import Path

import pytest

from app.cli import main


def test_simulate_runs_three_scenarios_and_prints_log_and_usage(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("VOCAB_DATA_DIR", str(tmp_path / "personal"))
    get_settings.cache_clear()
    try:
        assert main(["ai", "simulate"]) == 0
    finally:
        get_settings.cache_clear()
    output = capsys.readouterr().out

    assert "== 1. A 429 with Retry-After, then success ==" in output
    assert "(would wait 2.0 s)" in output  # printed, never slept
    assert "status=ok provider=fake_a requests=2" in output
    assert "call 1 -> status=ok provider=fake_b requests=2" in output
    assert "call 2 -> status=ok provider=fake_b requests=1" in output  # fake_a skipped
    assert "fake_a: available=False" in output
    assert "status=unavailable reason=all_failed" in output
    assert "== ai_call_log ==" in output and "== Usage, study day 2026-10-16 ==" in output
    assert "fake_a/fake-model: 6 requests" in output
    # The personal database was never created, let alone opened.
    assert not (tmp_path / "personal").exists()
