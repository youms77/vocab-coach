"""One real enrichment batch of two fictional terms through the gateway.

Settles the open question of M3.b: does the real model return sheets that pass the business rules
(term in every example, gap-fill answers, French translations) without a repair call?
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
from app.db.engine import create_db_engine
from app.db.models import Enrichment
from app.domain.enums import ItemStatus
from app.domain.events import ItemOrigin
from app.services import enrichment, library
from tests.conftest import sqlite_url
from tests.factories import NOW

TERMS = ["to account for", "shed light on"]


@pytest.fixture
def live_engine(tmp_path: Path) -> Iterator[Engine]:
    path = tmp_path / "live.sqlite3"
    migrate.upgrade(sqlite_url(path))
    engine = create_db_engine(sqlite_url(path))
    yield engine
    engine.dispose()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_a_real_batch_gives_valid_sheets(live_settings: Settings, live_engine: Engine) -> None:
    providers = build_providers(live_settings)
    if not any(p.is_configured() for p in providers.values()):
        pytest.skip("no AI provider is configured")
    with Session(live_engine) as session:
        deck = library.create_deck(session, name="Live check", domain="statistics", at=NOW)
        for term in TERMS:
            item = library.create_item(
                session, term=term, at=NOW, origin=ItemOrigin.IMPORT, intake=ItemStatus.QUEUED
            )
            library.add_item_to_deck(session, deck, item, NOW)
        session.commit()
    gateway = Gateway(
        lambda: build_providers(live_settings),
        session_factory=lambda: Session(live_engine, expire_on_commit=False),
        secrets=live_settings.secret_values,
    )
    report = enrichment.run_enrichment(
        lambda: Session(live_engine, expire_on_commit=False), gateway
    )
    if report.status == "unavailable" and report.reason is not None:
        pytest.skip(f"AI unavailable ({report.reason.value}): quota, rate limit or network")
    assert report.status == "ok", report
    assert report.generated == len(TERMS) and report.needs_completion == 0
    with Session(live_engine) as session:
        sheets = list(session.query(Enrichment))
        assert len(sheets) == len(TERMS)
