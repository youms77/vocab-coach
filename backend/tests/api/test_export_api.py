"""CSV export (M9.a): `/api/export/csv`, `/api/export/csv/{table}` and the export service.

Headers are stable, every CSV reads back with `csv.DictReader` with the database's row counts, the
format rules hold, no secret goes into the archive and a read writes nothing.
"""

import csv
import io
import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base
from app.db.models import Card, ReviewLog
from app.db.settings_store import set_setting
from app.domain.enums import SrsState
from app.services import export
from app.services.export_dictionary import TABLES
from tests.stats_support import NOW, add_sample, counts, make_client

GEMINI_KEY = "AIzaTEST-export-secret-0123456789"
GROQ_KEY = "gsk_TEST_export_secret_9876543210"


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("VOCAB_GEMINI_API_KEY", GEMINI_KEY)
    monkeypatch.setenv("VOCAB_GROQ_API_KEY", GROQ_KEY)
    get_settings.cache_clear()
    add_sample(engine)
    with Session(engine) as session:
        set_setting(session, "target_retention", 0.85)  # the `setting` table is never exported
        card = session.scalars(select(Card)).first()
        assert card is not None
        # 03:30 in Douala: study day 2026-08-19.
        late = datetime(2026, 8, 20, 2, 30, tzinfo=UTC)
        session.add(
            ReviewLog(
                card_id=card.id,
                reviewed_at=late,
                exercise_type="gap_fill",
                answer_text='He said "on campus",\nthen left',
                final_rating=3,
                state_before=SrsState.REVIEW,
                state_after=SrsState.REVIEW,
                due_after=NOW,
                scheduled_days=2.5,
                srs_algorithm="test",
            )  # fmt: skip
        )
        session.commit()
    with make_client(engine) as test_client:
        yield test_client
    get_settings.cache_clear()


def _archive(client: TestClient) -> zipfile.ZipFile:
    answer = client.get("/api/export/csv")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/zip"
    assert answer.headers["content-disposition"] == (
        'attachment; filename="vocab-coach-export-20260901.zip"'
    )
    return zipfile.ZipFile(io.BytesIO(answer.content))


def _rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    raw = archive.read(f"{name}.csv")
    assert not raw.startswith(b"\xef\xbb\xbf")  # no BOM
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))


def test_the_archive_has_one_csv_per_table_with_the_database_counts(
    client: TestClient, engine: Engine
) -> None:
    before = counts(engine)
    archive = _archive(client)
    names = archive.namelist()
    assert names == [f"{t}.csv" for t in export.EXPORT_TABLES] + [
        "manifest.json",
        "data_dictionary.md",
    ]
    assert "setting.csv" not in names
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format"] == "vocab-coach-csv-1"
    assert manifest["alembic_revision"] == "0002"
    assert (manifest["demo"], manifest["study_day"]) == (False, "2026-09-01")
    with Session(engine) as session:
        for name in export.EXPORT_TABLES:
            table = Base.metadata.tables[name]
            expected = session.scalar(select(func.count()).select_from(table))
            rows = _rows(archive, name)
            assert len(rows) == expected == manifest["tables"][name], name
    assert counts(engine) == before  # nothing written


def test_headers_are_stable(client: TestClient) -> None:
    archive = _archive(client)
    header = archive.read("review_log.csv").decode().splitlines()[0]
    assert header == (
        "id,card_id,study_session_id,reviewed_at,exercise_type,exercise_template_id,"
        "production_attempt_id,answer_text,audio_path,auto_rating,final_rating,response_time_ms,"
        "state_before,stability_before,difficulty_before,due_before,elapsed_days,retrievability,"
        "state_after,stability_after,difficulty_after,due_after,scheduled_days,srs_algorithm,"
        "study_day"
    )
    for name in export.EXPORT_TABLES:
        first = archive.read(f"{name}.csv").decode().split("\r\n")[0]
        assert first.split(",") == export.columns(name)
    assert "study_day" not in export.columns("production_target")


def test_value_formats(client: TestClient) -> None:
    archive = _archive(client)
    reviews = _rows(archive, "review_log")
    late = next(r for r in reviews if r["exercise_type"] == "gap_fill")
    assert late["reviewed_at"] == "2026-08-20T02:30:00.000000Z"
    assert late["study_day"] == "2026-08-19"  # 03:30 in Douala counts for the day before
    assert late["answer_text"] == 'He said "on campus",\nthen left'  # quotes and line break kept
    assert late["auto_rating"] == "" and late["scheduled_days"] == "2.5"
    categories = _rows(archive, "error_category")
    assert {c["is_builtin"] for c in categories} == {"true"}
    errors = _rows(archive, "error_event")
    assert errors[0]["alternatives"] == "[]"
    assert errors[0]["source"] == "writing"
    events = _rows(archive, "event_log")
    payload = next(e["payload"] for e in events if e["event_type"] == "setting.changed")
    assert payload == '{"key":"target_retention","old_value":0.9,"new_value":0.85}'
    assert json.loads(payload)["new_value"] == 0.85


def test_no_secret_in_the_archive(client: TestClient) -> None:
    answer = client.get("/api/export/csv")
    archive = zipfile.ZipFile(io.BytesIO(answer.content))
    for name in archive.namelist():
        data = archive.read(name)
        for secret in (GEMINI_KEY, GROQ_KEY):
            assert secret.encode() not in data, name
            assert secret[-8:].encode() not in data, name


def test_one_table_and_an_unknown_one(client: TestClient) -> None:
    answer = client.get("/api/export/csv/error_event")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "text/csv; charset=utf-8"
    assert answer.headers["content-disposition"] == 'attachment; filename="error_event.csv"'
    rows = list(csv.DictReader(io.StringIO(answer.text, newline="")))
    assert len(rows) == 4
    for name in ("setting", "alembic_version", "nothing"):
        missing = client.get(f"/api/export/csv/{name}")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "unknown_table"


def test_the_data_dictionary_describes_every_column() -> None:
    assert set(TABLES) == set(export.EXPORT_TABLES)
    for name in export.EXPORT_TABLES:
        model_columns = {c.name for c in Base.metadata.tables[name].columns}
        assert set(TABLES[name][1]) == model_columns, name


def test_the_data_dictionary_is_in_the_archive(client: TestClient) -> None:
    text = _archive(client).read("data_dictionary.md").decode()
    assert "pd.read_csv(" in text and "parse_dates=" in text
    assert "| `retrievability` | Float |" in text
