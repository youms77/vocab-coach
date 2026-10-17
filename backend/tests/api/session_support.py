"""Helpers for the session, review and discovery API tests (fictional data only)."""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from app.db.models import ExerciseTemplate
from app.domain import exercises as ex

# The fake clock of the API fixture starts here: 13:00 in Douala, study day 2026-10-16.
DAY_1 = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
# Start of study day 2026-10-17 (04:00 in Douala, day_start_hour 4).
DAY_2_START = datetime(2026, 10, 17, 3, 0, tzinfo=UTC)

TERM = "rule out"
SENTENCE = "We cannot rule out reverse causality with a single cross-section."


def sheet_for(term: str = TERM, **changes: Any) -> dict[str, Any]:
    sheet: dict[str, Any] = {
        "schema_version": 1,
        "part_of_speech": "phrasal verb",
        "definition_simple": "to say that something is not possible",
        "translation_fr": ["exclure", "écarter"],
        "examples": [
            {"sentence": f"The authors {term} measurement error.", "kind": "academic"},
            {"sentence": f"I wouldn't {term} a late train.", "kind": "spoken"},
        ],
        "pronunciation": {"ipa_us": "/ˌruːl ˈaʊt/", "stressed_syllable": "out"},
        "confusables": [{"term": "rule over", "difference": "to govern a country"}],
    }
    sheet.update(changes)
    return sheet


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def quick_add(client: TestClient, term: str = TERM, sentence: str | None = SENTENCE) -> int:
    response = client.post("/api/items", json={"term": term, "sentence": sentence})
    assert response.status_code == 201, response.text
    return response.json()["item"]["id"]


def write_sheet(client: TestClient, item_id: int, sheet: dict[str, Any] | None = None) -> None:
    response = client.put(f"/api/items/{item_id}/sheet", json={"content": sheet or sheet_for()})
    assert response.status_code == 200, response.text


def add_template(engine: Engine, item_id: int, exercise_type: str, content: dict[str, Any]) -> int:
    with Session(engine) as session:
        template = ExerciseTemplate(
            lexical_item_id=item_id,
            exercise_type=exercise_type,
            direction=ex.EXERCISE_TYPES[exercise_type][0],
            content=ex.validate_content(exercise_type, content),
            origin="user",
        )
        session.add(template)
        session.commit()
        return template.id


RECOGNITION = {
    "sentence": SENTENCE,
    "meaning": "to say that something is not possible",
    "meaning_fr": "exclure",
    "distractors": ["to prove something", "to measure something", "to ignore something"],
}
GAP_FILL = {"sentence": "We cannot ___ a placebo effect.", "answer": "rule out", "accepted": []}
PRODUCTION = {
    "situation": "Say that chance is not a possible cause.",
    "example_answer": "We can rule out chance.",
}
SPOKEN = {
    "question": "What can your design not exclude?",
    "example_answer": "It cannot rule out selection.",
}


def add_all_templates(engine: Engine, item_id: int) -> dict[str, int]:
    return {
        ex.RECOGNITION: add_template(engine, item_id, ex.RECOGNITION, RECOGNITION),
        ex.LISTENING: add_template(engine, item_id, ex.LISTENING, RECOGNITION),
        ex.GAP_FILL: add_template(engine, item_id, ex.GAP_FILL, GAP_FILL),
        ex.SENTENCE_PRODUCTION: add_template(engine, item_id, ex.SENTENCE_PRODUCTION, PRODUCTION),
        ex.SPOKEN_ANSWER: add_template(engine, item_id, ex.SPOKEN_ANSWER, SPOKEN),
    }


def start_session(client: TestClient) -> int:
    response = client.post("/api/session/start")
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def discover(client: TestClient, item_id: int, session_id: int, **complete: Any) -> dict[str, Any]:
    started = client.post(f"/api/discovery/{item_id}/start", json={"session_id": session_id})
    assert started.status_code == 200, started.text
    done = client.post(
        f"/api/discovery/{item_id}/complete",
        json={"session_id": session_id, "duration_ms": 120_000, **complete},
    )
    assert done.status_code == 200, done.text
    return done.json()


def table_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        names = inspect(connection).get_table_names()
        return {
            name: connection.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()  # noqa: S608
            for name in names
        }


def scalar(engine: Engine, statement: Any) -> Any:
    with Session(engine) as session:
        return session.scalar(statement)
