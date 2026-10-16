"""The live tests (real provider calls) can never run by accident: opt-in twice, off by default."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def test_live_tests_are_deselected_by_default_and_the_marker_is_registered(
    pytestconfig: pytest.Config,
) -> None:
    assert "not live" in pytestconfig.getini("addopts")
    assert any(line.startswith("live:") for line in pytestconfig.getini("markers"))


def _run_live(**env: str) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k != "VOCAB_RUN_LIVE"}
    clean.update(
        VOCAB_GEMINI_API_KEY="",  # an empty value also wins over the owner's real .env
        VOCAB_GROQ_API_KEY="",
        VOCAB_OLLAMA_BASE_URL="",
    )
    clean.update(env)
    return subprocess.run(  # noqa: S603 (our own interpreter, fixed arguments)
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/live",
            "-m",
            "live",
            "-rs",
            "-p",
            "no:cacheprovider",
        ],
        cwd=BACKEND,
        env=clean,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_selecting_live_tests_without_the_opt_in_variable_skips_them_all() -> None:
    result = _run_live()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VOCAB_RUN_LIVE=1" in result.stdout  # the skip reason says how to opt in
    assert " passed" not in result.stdout


def test_opting_in_without_any_key_still_skips_everything() -> None:
    result = _run_live(VOCAB_RUN_LIVE="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not configured" in result.stdout
    assert " passed" not in result.stdout and " failed" not in result.stdout
