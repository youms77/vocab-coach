"""Scenario units through the API (M8.a2): generation as a result, content, edits, steps, terms and
the takes of the shadowing and the final task. Scripted fake provider; both the engine and the
session dependency point at the test database."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.db.models import CurriculumUnit
from tests.api.conftest import FakeAiEnv
from tests.curriculum_unit_support import LINES, broken, unit_output
from tests.speaking_support import clean_output
from tests.speech_support import heard, wav_bytes

WAV = wav_bytes(1.0)
STT = (Capability.TEXT, Capability.TRANSCRIPTION)
API = "/api/curriculum"
GENERATE = f"{API}/tracks/speaking_scenarios/units/1/generate"
TALK = "I would like this job because I work well in a team."


def script(env: FakeAiEnv, *steps: Success | Failure) -> None:
    env.use(FakeProvider("fake", steps, capabilities=STT))


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def started(env: FakeAiEnv) -> None:
    assert env.client.post(f"{API}/tracks/speaking_scenarios/start").status_code == 200


def generated(env: FakeAiEnv) -> int:
    started(env)
    script(env, Success(content=unit_output()))
    response = env.client.post(GENERATE)
    assert response.status_code == 200, response.text
    return response.json()["unit"]["id"]


def shadow(env: FakeAiEnv, unit_id: int | None, text: str, said: str) -> Any:
    script(env, heard(said, duration_s=3.0))
    params: dict[str, Any] = {"target_text": text, "duration_s": 3.0}
    if unit_id is not None:
        params["unit_id"] = unit_id
    return env.client.post(
        "/api/speech/shadowing", params=params, content=WAV, headers={"Content-Type": "audio/wav"}
    )


def test_generation_returns_the_unit_with_its_content(fake_env: FakeAiEnv) -> None:
    started(fake_env)
    script(fake_env, Success(content=unit_output()))
    response = fake_env.client.post(GENERATE)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["reason"]) == ("ok", None)
    unit = body["unit"]
    assert unit["content_status"] == "generated" and unit["progress"] == "not_started"
    scenario = unit["scenario"]
    assert scenario["revision"] == 1 and scenario["prompt_version"] == "curriculum_unit.v1"
    assert scenario["formulas"][0] == {
        "index": 0,
        "text": "Thank you for having me",
        "item_type": "spoken_formula",
        "function_en": "Function 0",
        "function_fr": "Fonction 0",
        "register": "neutral",
        "item_id": None,
    }
    assert [s["line_index"] for s in scenario["shadowing"]] == [0, 2, 4, 6, 8]
    assert scenario["next_step"] == "formulas"
    assert scenario["final_task"]["minutes"] == 1
    assert fake_env.client.get(f"{API}/units/{unit['id']}").json()["scenario"] == scenario
    listed = fake_env.client.get(f"{API}/tracks/speaking_scenarios?limit=2").json()["units"][0]
    assert (listed["unit_id"], listed["content_status"]) == (unit["id"], "generated")

    again = fake_env.client.post(GENERATE)
    assert again.status_code == 409 and code(again) == "unit_generated"


def test_an_ai_failure_is_an_answer_and_writes_nothing(fake_env: FakeAiEnv) -> None:
    started(fake_env)
    script(fake_env, Failure(ErrorKind.AUTH))
    response = fake_env.client.post(GENERATE)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable" and response.json()["unit"] is None
    with Session(fake_env.engine) as session:
        assert session.scalars(select(CurriculumUnit)).first() is None


def test_a_broken_answer_is_incomplete_and_can_be_retried(fake_env: FakeAiEnv) -> None:
    started(fake_env)
    script(fake_env, Success(content=broken("unknown_ref")), Success(content=broken("two_refs")))
    incomplete = fake_env.client.post(GENERATE).json()
    assert (incomplete["status"], incomplete["unit"]) == ("incomplete", None)
    with Session(fake_env.engine) as session:
        assert session.scalars(select(CurriculumUnit)).first() is None
    script(fake_env, Success(content=unit_output()))
    assert fake_env.client.post(GENERATE).json()["status"] == "ok"


def test_refusals_of_generation(fake_env: FakeAiEnv) -> None:
    refused = fake_env.client.post(GENERATE)
    assert refused.status_code == 409 and code(refused) == "track_not_started"
    started(fake_env)
    wordlist = fake_env.client.post(f"{API}/tracks/academic/units/1/generate")
    assert wordlist.status_code == 422 and code(wordlist) == "not_a_scenario_track"
    assert (
        fake_env.client.post(f"{API}/tracks/speaking_scenarios/units/99/generate").status_code
        == 404
    )
    assert fake_env.client.post(f"{API}/tracks/nope/units/1/generate").status_code == 404


def test_steps_edits_and_terms(fake_env: FakeAiEnv) -> None:
    unit_id = generated(fake_env)
    client = fake_env.client
    marked = client.post(f"{API}/units/{unit_id}/steps/formulas").json()
    assert marked["changed"] is True and marked["unit"]["progress"] == "in_progress"
    assert client.post(f"{API}/units/{unit_id}/steps/formulas").json()["changed"] is False
    assert code(client.post(f"{API}/units/{unit_id}/steps/shadowing")) == "invalid_step"
    assert client.post(f"{API}/units/999/steps/formulas").status_code == 404

    edit = {"expected_revision": 1, "shadowing": [0, 2, 4, 6, 9]}
    edited = client.put(f"{API}/units/{unit_id}/content", json=edit)
    assert edited.status_code == 200, edited.text
    assert edited.json()["content_status"] == "edited"
    assert edited.json()["scenario"]["revision"] == 2
    stale = client.put(f"{API}/units/{unit_id}/content", json=edit)
    assert stale.status_code == 409 and code(stale) == "unit_changed"
    assert stale.json()["detail"]["revision"] == 2
    bad = client.put(
        f"{API}/units/{unit_id}/content", json={"expected_revision": 2, "shadowing": [0, 1]}
    )
    assert bad.status_code == 422 and code(bad) == "invalid_content"
    assert bad.json()["detail"]["problems"]
    empty = client.put(f"{API}/units/{unit_id}/content", json={"expected_revision": 2, "x": 1})
    assert empty.status_code == 422 and code(empty) == "invalid_content"

    terms = client.post(f"{API}/units/{unit_id}/terms", json={"indices": [0, 1, 2]}).json()
    assert (terms["imported"], terms["skipped"]) == (3, 0)
    assert [t["status"] for t in terms["unit"]["terms"]] == ["triage"] * 3
    assert terms["unit"]["state"] == "opened" and terms["unit"]["deck_id"]
    all_terms = client.post(f"{API}/units/{unit_id}/terms", json={}).json()
    assert (all_terms["imported"], all_terms["skipped"]) == (6, 3)
    assert (
        code(client.post(f"{API}/units/{unit_id}/terms", json={"indices": [50]}))
        == "invalid_content"
    )


def test_a_unit_reaches_done_through_the_speech_routes(fake_env: FakeAiEnv) -> None:
    unit_id = generated(fake_env)
    client = fake_env.client
    client.post(f"{API}/units/{unit_id}/terms", json={"indices": [0, 1, 2]})
    for step in ("formulas", "dialogue"):
        client.post(f"{API}/units/{unit_id}/steps/{step}")
    for index in (0, 2, 4, 6, 8):
        response = shadow(fake_env, unit_id, LINES[index][1], LINES[index][1])
        assert response.status_code == 201, response.text
    scenario = client.get(f"{API}/units/{unit_id}").json()["scenario"]
    assert scenario["steps"]["shadowing"] is True and scenario["next_step"] == "final_task"

    script(fake_env, heard(TALK, duration_s=30.0))
    talk = client.post(
        "/api/speech/speaking",
        params={"duration_s": 30.0, "unit_id": unit_id},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    assert talk.status_code == 201, talk.text
    attempt_id = talk.json()["production_id"]
    production = client.get(f"/api/productions/{attempt_id}").json()
    assert production["prompt_text"].startswith("You are in an interview")
    assert len(production["targets"]) == 3  # the formulas of the task that are library terms
    script(fake_env, Success(content=clean_output(TALK)))
    assert client.post(f"/api/productions/{attempt_id}/correct").json()["status"] == "ok"
    done = client.get(f"{API}/units/{unit_id}").json()
    assert done["progress"] == "done" and done["scenario"]["next_step"] is None
    assert done["scenario"]["final_task"]["corrected"] is True


def test_the_unit_of_a_take_must_be_a_scenario_unit(fake_env: FakeAiEnv) -> None:
    missing = shadow(fake_env, 999, LINES[0][1], LINES[0][1])
    assert missing.status_code == 404 and code(missing) == "unit_not_found"
    fake_env.client.post(f"{API}/tracks/academic/start")
    word_unit = fake_env.client.post(f"{API}/tracks/academic/units/1/open").json()["unit"]["id"]
    refused = shadow(fake_env, word_unit, LINES[0][1], LINES[0][1])
    assert refused.status_code == 422 and code(refused) == "not_a_scenario_unit"
    speak = fake_env.client.post(
        "/api/speech/speaking",
        params={"duration_s": 30.0, "unit_id": 999},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    assert speak.status_code == 404
