"""Consolidation productions through the API (M7.a2): the written and the spoken attempt, the
correction that applies the result to the terms, idempotence, and the end-to-end scenario."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import Capability, ErrorKind
from app.db.models import (
    Card,
    ConsolidationTask,
    ErrorEvent,
    EventLog,
    LexicalItem,
    ReviewLog,
)
from app.domain.enums import ErrorSource, ItemStatus
from tests.api.conftest import FakeAiEnv
from tests.api.session_support import code, start_session
from tests.consolidation_deck_support import ready_deck
from tests.consolidation_support import MISUSED_REF, TERMS, TEXT, corrected_output, task_output
from tests.library_support import count, events
from tests.speaking_support import clean_output
from tests.speech_support import heard, wav_bytes

FAR = datetime(2035, 1, 1, tzinfo=UTC)
STT = (Capability.TEXT, Capability.TRANSCRIPTION)
WAV = wav_bytes(1.0)


@pytest.fixture
def deck_id(fake_env: FakeAiEnv) -> int:
    with Session(fake_env.engine) as session:
        deck, _ = ready_deck(session, 10, terms=TERMS, stability=lambda n: 10.0 + n)
        for card in session.scalars(select(Card)):
            card.due = FAR
        session.commit()
        return deck.id


def new_task(env: FakeAiEnv, deck_id: int) -> dict[str, Any]:
    refs = [f"t{i + 1}" for i in range(10)]
    env.script(Success(content=task_output(refs)))
    response = env.client.post(
        "/api/consolidation/tasks",
        json={"deck_id": deck_id, "task_type": "talk", "term_count": 10},
    )
    assert response.status_code == 201, response.text
    return response.json()["task"]


def write(env: FakeAiEnv, task_id: int, text: str = TEXT, **extra: Any) -> Any:
    return env.client.post(
        f"/api/consolidation/tasks/{task_id}/attempts/written", json={"text": text, **extra}
    )


def correct(env: FakeAiEnv, production_id: int) -> Any:
    return env.client.post(f"/api/productions/{production_id}/correct")


def statuses(env: FakeAiEnv) -> dict[str, str]:
    with Session(env.engine) as session:
        return {i.term: str(i.status) for i in session.scalars(select(LexicalItem))}


def test_a_written_attempt(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    response = write(fake_env, task["id"])
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert (attempt["kind"], attempt["modality"]) == ("consolidation", "written")
    assert attempt["prompt_text"] == task["prompt"]["en"]
    assert [t["term"] for t in attempt["targets"]] == TERMS
    assert attempt["corrected"] is False and attempt["word_count"] == len(TEXT.split())
    after = fake_env.client.get(f"/api/consolidation/tasks/{task['id']}").json()
    assert after["status"] == "accepted"
    assert after["attempts"][0]["production_id"] == attempt["id"]
    assert after["attempts"][0]["modality"] == "written" and not after["attempts"][0]["corrected"]
    with Session(fake_env.engine) as session:
        (payload,) = events(session, "production.recorded")
        assert payload["origin"] == "consolidation" and payload["kind"] == "consolidation"
        row = session.scalars(
            select(EventLog).where(EventLog.event_type == "production.recorded")
        ).one()
        assert row.payload_version == 6
    # A second attempt keeps the task accepted (one status change only).
    assert write(fake_env, task["id"]).status_code == 201
    with Session(fake_env.engine) as session:
        assert len(events(session, "consolidation.task_status_changed")) == 1


def test_the_limits_of_a_written_attempt(fake_env: FakeAiEnv, deck_id: int) -> None:
    task_id = new_task(fake_env, deck_id)["id"]
    assert write(fake_env, task_id, "x" * 4001).status_code == 422
    forty_one = " ".join(f"Sentence number {n} is here." for n in range(41))
    too_long = write(fake_env, task_id, forty_one)
    assert too_long.status_code == 422 and code(too_long) == "text_too_long"
    assert write(fake_env, task_id, "   ").status_code == 422
    assert write(fake_env, task_id, "ok.", study_session_id=999).status_code == 404
    assert code(write(fake_env, 999)) == "task_not_found"
    with Session(fake_env.engine) as session:
        assert count(session, ConsolidationTask) == 1
    assert fake_env.client.get(f"/api/consolidation/tasks/{task_id}").json()["status"] == "proposed"


def test_an_attempt_on_a_closed_task(fake_env: FakeAiEnv, deck_id: int) -> None:
    task_id = new_task(fake_env, deck_id)["id"]
    fake_env.client.post(f"/api/consolidation/tasks/{task_id}/status", json={"to": "dismissed"})
    closed = write(fake_env, task_id)
    assert closed.status_code == 409 and code(closed) == "task_closed"
    fake_env.use(FakeProvider("fake", [heard("Some words.")], capabilities=STT))
    spoken = fake_env.client.post(
        "/api/speech/consolidation",
        params={"task_id": task_id, "duration_s": 60},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    assert spoken.status_code == 409 and code(spoken) == "task_closed"


def test_the_whole_scenario(fake_env: FakeAiEnv, deck_id: int) -> None:
    ready = [row for row in fake_env.client.get("/api/consolidation/decks").json()]
    assert ready[0]["ready"] is True
    task = new_task(fake_env, deck_id)
    plan = fake_env.client.get("/api/session/today").json()["plan"]
    assert any(b["kind"] == "consolidation" for b in plan["blocks"])
    attempt = write(fake_env, task["id"]).json()
    fake_env.script(Success(content=corrected_output()))
    response = correct(fake_env, attempt["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    summary = body["consolidation"]
    assert summary["task_id"] == task["id"] and summary["modality"] == "written"
    assert (summary["targets"], summary["used"], summary["used_correctly"]) == (10, 9, 8)
    assert (summary["misused"], summary["absent"]) == (1, 1)
    assert len(summary["activated_item_ids"]) == 8 and len(summary["reinforced_card_ids"]) == 1
    now = statuses(fake_env)
    assert [t for t in TERMS if now[t] == "active"] == [
        t for i, t in enumerate(TERMS) if i not in (MISUSED_REF, 9)
    ]
    assert now["standard error"] == "consolidated"  # absent: unchanged
    assert now["selection bias"] in ("learning", "consolidated")
    with Session(fake_env.engine) as session:
        (review,) = session.scalars(select(ReviewLog)).all()
        assert review.exercise_type == "consolidation_misuse"
        assert review.final_rating == 1 and review.auto_rating == 1
        assert review.production_attempt_id is None
        card = session.get_one(Card, review.card_id)
        assert session.get_one(LexicalItem, card.lexical_item_id).term == "selection bias"
        (error,) = session.scalars(select(ErrorEvent)).all()
        assert error.source is ErrorSource.CONSOLIDATION
        assert error.lexical_item_id == card.lexical_item_id
        assert error.production_attempt_id == attempt["id"]
        (checked,) = events(session, "consolidation.attempt_checked")
        assert checked == {
            "task_id": task["id"],
            "production_attempt_id": attempt["id"],
            "modality": "written",
            "targets": 10,
            "used": 9,
            "used_correctly": 8,
            "misused": 1,
            "absent": 1,
            "activated_item_ids": summary["activated_item_ids"],
            "reinforced_card_ids": summary["reinforced_card_ids"],
        }
        assert len(events(session, "item.status_changed")) >= 8
    detail = fake_env.client.get(f"/api/consolidation/tasks/{task['id']}").json()
    assert detail["attempts"][0]["corrected"] is True
    counts = {t["term"]: t["used_correctly_count"] for t in detail["targets"]}
    assert counts["shed light on"] == 1 and counts["selection bias"] == 0
    assert {t["term"]: t["item_status"] for t in detail["targets"]}["causal effect"] == "active"
    # The task is still open (the owner completes it) and still in today's plan.
    plan = fake_env.client.get("/api/session/today").json()["plan"]
    assert any(b["kind"] == "consolidation" for b in plan["blocks"])
    assert start_session(fake_env.client)


def test_the_result_is_applied_once(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    fake_env.script(Success(content=corrected_output()))
    assert correct(fake_env, attempt["id"]).status_code == 200
    before = statuses(fake_env)
    again = correct(fake_env, attempt["id"])
    assert again.status_code == 409 and code(again) == "already_corrected"
    assert statuses(fake_env) == before
    with Session(fake_env.engine) as session:
        assert count(session, ReviewLog) == 1 and count(session, ErrorEvent) == 1
        assert len(events(session, "consolidation.attempt_checked")) == 1


def test_no_correction_changes_nothing(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    fake_env.script(Failure(ErrorKind.NETWORK))
    body = correct(fake_env, attempt["id"]).json()
    assert body["status"] == "unavailable" and body["consolidation"] is None
    assert set(statuses(fake_env).values()) == {"consolidated"}
    with Session(fake_env.engine) as session:
        assert count(session, ReviewLog) == 0
    fake_env.clock.advance(7200)  # past the provider cool-down
    fake_env.script(Success(content=corrected_output()))  # retried later
    retry = correct(fake_env, attempt["id"])
    assert retry.json()["status"] == "ok", retry.json()
    assert retry.json()["consolidation"]["used_correctly"] == 8


def test_terms_without_a_verdict_do_not_change(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    fake_env.script(Success(content=corrected_output(misused=False, checks=False)))
    summary = correct(fake_env, attempt["id"]).json()["consolidation"]
    assert summary["activated_item_ids"] == [] and summary["misused"] == 0
    assert set(statuses(fake_env).values()) == {"consolidated"}


def test_a_term_archived_meanwhile_is_ignored(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    with Session(fake_env.engine) as session:
        for term in ("causal effect", "selection bias"):
            item = session.scalars(select(LexicalItem).where(LexicalItem.term == term)).one()
            item.status = ItemStatus.ARCHIVED
        session.commit()
    fake_env.script(Success(content=corrected_output()))
    summary = correct(fake_env, attempt["id"]).json()["consolidation"]
    assert len(summary["activated_item_ids"]) == 7
    assert summary["reinforced_card_ids"] == []
    now = statuses(fake_env)
    assert now["causal effect"] == now["selection bias"] == "archived"
    with Session(fake_env.engine) as session:
        assert count(session, ReviewLog) == 0


def test_an_active_term_used_wrongly_stays_active(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    with Session(fake_env.engine) as session:
        item = session.scalars(
            select(LexicalItem).where(LexicalItem.term == "selection bias")
        ).one()
        item.status = ItemStatus.ACTIVE
        session.commit()
    fake_env.script(Success(content=corrected_output()))
    summary = correct(fake_env, attempt["id"]).json()["consolidation"]
    assert len(summary["reinforced_card_ids"]) == 1 and len(summary["activated_item_ids"]) == 8
    assert statuses(fake_env)["selection bias"] == "active"


def test_an_error_tied_to_the_term_blocks_the_activation(fake_env: FakeAiEnv, deck_id: int) -> None:
    """The AI says "used correctly" but logs an error on the term: it is a misuse."""
    task = new_task(fake_env, deck_id)
    attempt = write(fake_env, task["id"]).json()
    output = corrected_output()
    for check in output["targets"]:
        check["used_correctly"] = True
    fake_env.script(Success(content=output))
    summary = correct(fake_env, attempt["id"]).json()["consolidation"]
    assert summary["misused"] == 1 and summary["used_correctly"] == 8
    assert statuses(fake_env)["selection bias"] != "active"


def test_a_spoken_attempt(fake_env: FakeAiEnv, deck_id: int) -> None:
    task = new_task(fake_env, deck_id)
    spoken = (
        "In this reading the authors want to shed light on a causal effect. "
        "They control for a confounder in every model. "
        "The treatment group is compared with a control group and the sample size is large."
    )
    provider = FakeProvider(
        "fake",
        [
            heard(spoken, duration_s=75.0),
            Success(
                content=clean_output(
                    spoken,
                    targets=[
                        {"ref": r, "used": True, "used_correctly": True, "comment": ""}
                        for r in range(6)
                    ],
                )
            ),
        ],
        capabilities=STT,
    )
    fake_env.use(provider)
    params = {"task_id": task["id"], "duration_s": 75.0}
    response = fake_env.client.post(
        "/api/speech/consolidation",
        params=params,
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 201, response.text
    production_id = (
        response.json()["production_id"]
        if "production_id" in response.json()
        else (response.json()["production"]["id"])
    )
    assert "Some" not in str(provider.transcriptions[0])
    assert task["prompt"]["en"] not in str(provider.transcriptions[0])
    detail = fake_env.client.get(f"/api/consolidation/tasks/{task['id']}").json()
    assert detail["status"] == "accepted" and detail["attempts"][0]["modality"] == "oral"
    body = correct(fake_env, production_id).json()
    assert body["status"] == "ok", body
    summary = body["consolidation"]
    assert summary["modality"] == "oral" and summary["used_correctly"] == 6
    assert summary["absent"] == 4  # not heard
    now = statuses(fake_env)
    assert [t for t in TERMS if now[t] == "active"] == TERMS[:6]
    with Session(fake_env.engine) as session:
        recorded = events(session, "production.recorded")
        assert recorded[0]["origin"] == "consolidation" and recorded[0]["modality"] == "oral"


@pytest.mark.parametrize(
    ("seconds", "status"), [(19.0, 422), (20.0, 201), (240.0, 201), (241.0, 422)]
)
def test_the_bounds_of_a_spoken_attempt(
    fake_env: FakeAiEnv, deck_id: int, seconds: float, status: int
) -> None:
    task = new_task(fake_env, deck_id)
    fake_env.use(
        FakeProvider("fake", [heard("Some words here.", duration_s=seconds)], capabilities=STT)
    )
    response = fake_env.client.post(
        "/api/speech/consolidation",
        params={"task_id": task["id"], "duration_s": seconds},
        content=WAV,
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == status, response.text
    if status == 422:
        assert code(response) in ("audio_too_short", "audio_too_long")
        detail = fake_env.client.get(f"/api/consolidation/tasks/{task['id']}").json()
        assert detail["status"] == "proposed" and detail["attempts"] == []


def test_a_free_production_is_not_a_consolidation_one(fake_env: FakeAiEnv, deck_id: int) -> None:
    """`/correct` routes by kind: free writing still uses the writing path, no `consolidation`."""
    response = fake_env.client.post("/api/productions", json={"text": "I live on campus."})
    fake_env.script(
        Success(
            content=corrected_output(misused=False, checks=False)
            | {
                "sentences": [{"index": 1, "corrected": "I live on campus.", "status": "correct"}],
                "corrected_text": "I live on campus.",
                "natural_text": "I live on campus.",
            }
        )
    )
    body = correct(fake_env, response.json()["id"]).json()
    assert body["status"] == "ok" and body["consolidation"] is None
