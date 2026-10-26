"""A real `curriculum_unit` call through the gateway (M8.a2, D-054): the "Job interview" unit of
`content/curriculum.yaml`, written, stored, then taken through its steps.

    VOCAB_RUN_LIVE=1 uv run pytest tests/live/test_live_curriculum_unit.py -m live -v

One or two requests. A quota or a rate limit gives a skip, not a failure. The syllabus text is the
only thing sent. When the model disagrees with a rule, the prompt is adjusted, never the test
(D-132).
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers import build_providers
from app.config import Settings
from app.db import migrate
from app.db.base import utcnow
from app.db.engine import create_db_engine
from app.db.models import CurriculumUnit
from app.domain import curriculum_unit as rules
from app.domain.enums import UnitContentStatus, UnitProgress
from app.services import curriculum, curriculum_units
from tests.conftest import sqlite_url


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def _gateway(live_settings: Settings, factory) -> Gateway:  # type: ignore[no-untyped-def]
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    return Gateway(
        lambda: build_providers(live_settings),
        session_factory=factory,
        secrets=live_settings.secret_values,
    )


def test_a_real_job_interview_unit(live_settings: Settings, live_engine: Engine) -> None:
    factory = lambda: Session(live_engine, expire_on_commit=False)  # noqa: E731
    gateway = _gateway(live_settings, factory)
    with factory() as session:
        curriculum.start_track(session, "speaking_scenarios", utcnow())
        session.commit()
    result = curriculum_units.generate_unit(factory, gateway, "speaking_scenarios", 1)
    if result.status == "unavailable":
        pytest.skip(f"AI unavailable ({result.reason}): quota, rate limit or network")
    assert result.status == "ok" and result.unit is not None, result
    with factory() as session:
        unit = session.get_one(CurriculumUnit, result.unit.id)
        assert unit.code == "job_interview_1" and unit.provider and unit.model
        assert unit.content_status is UnitContentStatus.GENERATED
        scenario = curriculum.get_unit(session, unit.id).scenario
        assert scenario is not None
        assert rules.FORMULAS_MIN <= len(scenario.formulas) <= rules.FORMULAS_MAX
        assert len(scenario.dialogue["lines"]) >= rules.LINES_MIN
        assert rules.SHADOWING_MIN <= len(scenario.shadowing) <= rules.SHADOWING_MAX
        for step in ("formulas", "dialogue"):
            curriculum_units.mark_step(session, unit.id, step, utcnow())
        session.commit()
        assert session.get_one(CurriculumUnit, unit.id).progress is UnitProgress.IN_PROGRESS
