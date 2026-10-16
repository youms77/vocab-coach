"""Usage sheet and list-extension endpoints end to end (M3.b), with a scripted fake provider."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.ai.providers.fake import FakeProvider, Success
from app.config import get_settings
from app.db.engine import get_engine, get_session
from app.domain.enums import ItemStatus
from app.domain.events import ItemOrigin
from app.main import create_app
from app.services import enrichment, library
from tests.ai.conftest import FakeClock, FixedRng
from tests.enrichment_support import batch_output, generated_entry
from tests.factories import NOW

TERMS = ["to account for", "heteroskedasticity"]


class Env:
    def __init__(self, client: TestClient, provider: FakeProvider) -> None:
        self.client = client
        self.provider = provider

    def script(self, *steps: Any) -> None:
        self.provider.script = list(steps)
        self.provider._calls = 0  # noqa: SLF001 (restart the script)


@pytest.fixture
def env(engine: Engine, clock: FakeClock) -> Iterator[Env]:
    provider = FakeProvider("fake", [], advance=clock.advance)
    gateway = Gateway(
        {"fake": provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: ["fake"],
        clock=clock.now,
        sleep=clock.sleep,
        rng=FixedRng(),
    )

    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_gateway] = lambda: gateway
    with TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}") as client:
        yield Env(client, provider)


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def _seed(engine: Engine, terms: list[str] = TERMS, **deck: Any) -> tuple[int, list[int]]:
    with Session(engine) as session:
        d = library.create_deck(
            session,
            name=deck.pop("name", "Causal inference"),
            at=NOW,
            domain="econometrics",
            **deck,
        )
        ids = []
        for term in terms:
            item = library.create_item(
                session, term=term, at=NOW, origin=ItemOrigin.IMPORT, intake=ItemStatus.QUEUED
            )
            library.add_item_to_deck(session, d, item, NOW)
            ids.append(item.id)
        session.commit()
        return d.id, ids


def _enrich(env: Env, engine: Engine) -> list[int]:
    _, ids = _seed(engine)
    env.script(Success(content=batch_output(TERMS)))
    assert env.client.post("/api/enrichment/run", json={}).json()["status"] == "ok"
    return ids


def test_pending_then_run(env: Env, engine: Engine) -> None:
    deck_id, ids = _seed(engine)
    pending = env.client.get("/api/enrichment/pending", params={"deck_id": deck_id}).json()
    assert pending == {
        "count": 2,
        "items": [
            {"item_id": ids[0], "term": TERMS[0], "status": "queued"},
            {"item_id": ids[1], "term": TERMS[1], "status": "queued"},
        ],
    }
    env.script(Success(content=batch_output(TERMS)))
    response = env.client.post("/api/enrichment/run", json={"deck_id": deck_id})
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "reason": None,
        "generated": 2,
        "needs_completion": 0,
        "superseded": 0,
        "failed": 0,
        "remaining": 0,
        "item_ids": ids,
    }
    assert env.client.get("/api/enrichment/pending").json()["count"] == 0


def test_unavailable_is_a_200_with_a_reason(env: Env, engine: Engine) -> None:
    _seed(engine)
    env.provider.configured = False
    body = env.client.post("/api/enrichment/run", json={}).json()
    assert (body["status"], body["reason"], body["remaining"]) == (
        "unavailable",
        "no_provider_configured",
        2,
    )


def test_concurrent_run_is_a_409(env: Env, engine: Engine) -> None:
    _seed(engine)
    assert enrichment._RUN_LOCK.acquire(blocking=False)  # noqa: SLF001 (a run in progress)
    try:
        response = env.client.post("/api/enrichment/run", json={})
    finally:
        enrichment._RUN_LOCK.release()  # noqa: SLF001
    assert response.status_code == 409 and code(response) == "enrichment_running"


def test_run_errors(env: Env, engine: Engine) -> None:
    deck_id, ids = _seed(engine)
    with Session(engine) as session:
        library.get_item(session, ids[0]).status = ItemStatus.ARCHIVED
        session.commit()
    response = env.client.post("/api/enrichment/run", json={"item_ids": ids})
    assert response.status_code == 409 and code(response) == "item_archived"
    assert response.json()["detail"]["item_ids"] == [ids[0]]
    assert code(env.client.post("/api/enrichment/run", json={"deck_id": 999})) == "deck_not_found"
    response = env.client.post("/api/enrichment/run", json={"limit": 3})
    assert response.status_code == 422 and code(response) == "invalid_request"
    assert env.client.get("/api/enrichment/pending", params={"deck_id": 999}).status_code == 404
    assert deck_id


def test_items_show_the_sheet_status_and_can_be_filtered_and_searched(
    env: Env, engine: Engine
) -> None:
    ids = _enrich(env, engine)
    _, [bare] = _seed(engine, ["shed light on"], name="Second deck")
    items = {i["id"]: i for i in env.client.get("/api/items").json()["items"]}
    assert items[ids[0]]["sheet_status"] == "complete" and items[bare]["sheet_status"] == "none"

    def ids_for(**params: Any) -> list[int]:
        return [i["id"] for i in env.client.get("/api/items", params=params).json()["items"]]

    assert ids_for(sheet="none") == [bare]
    assert ids_for(sheet="complete") == ids
    assert ids_for(sheet="needs_completion") == [] and ids_for(sheet="edited") == []
    assert ids_for(q="rendre compte") == ids  # translation_fr entry
    assert ids_for(q="REASON FOR") == ids  # definition_simple, case-insensitive
    assert ids_for(q="explain a cause") == ids  # meaning_in_context
    assert ids_for(q="shed") == [bare]  # the term itself still matches
    assert env.client.get("/api/items", params={"sheet": "bad"}).status_code == 422


def test_triage_never_shows_a_sheet(env: Env, engine: Engine) -> None:
    _enrich(env, engine)
    with Session(engine) as session:
        deck = library.create_deck(session, name="Triage deck", at=NOW)
        item = library.create_item(
            session, term="to rule out", at=NOW, origin=ItemOrigin.IMPORT, intake=ItemStatus.TRIAGE
        )
        library.add_item_to_deck(session, deck, item, NOW)
        session.commit()
        item_id = item.id
    env.script(Success(content={"sheets": [generated_entry(0, "to rule out")]}))
    env.client.post("/api/enrichment/run", json={"item_ids": [item_id]})
    [entry] = env.client.get("/api/triage").json()
    assert set(entry) == {"item_id", "term", "item_type", "sentence", "decks"}


def test_read_edit_and_regenerate_a_sheet(env: Env, engine: Engine) -> None:
    item_id = _enrich(env, engine)[0]
    sheet = env.client.get(f"/api/items/{item_id}/sheet").json()
    assert sheet["sheet_status"] == "complete" and sheet["version"] == 1
    assert (sheet["provider"], sheet["prompt_version"], sheet["schema_version"]) == (
        "fake",
        "enrichment.v1",
        1,
    )
    content = {**sheet["content"], "usage_notes": "My note."}
    put = env.client.put(
        f"/api/items/{item_id}/sheet",
        json={"content": content, "base_enrichment_id": sheet["enrichment_id"]},
    )
    assert put.status_code == 200
    assert put.json()["sheet_status"] == "edited" and put.json()["version"] == 2
    stale = env.client.put(
        f"/api/items/{item_id}/sheet",
        json={"content": content, "base_enrichment_id": sheet["enrichment_id"]},
    )
    assert stale.status_code == 409 and code(stale) == "sheet_changed"

    refused = env.client.post(f"/api/items/{item_id}/sheet/regenerate", json={})
    assert refused.status_code == 409 and code(refused) == "sheet_edited"
    env.script(Success(content={"sheets": [generated_entry(0, TERMS[0])]}))
    done = env.client.post(
        f"/api/items/{item_id}/sheet/regenerate", json={"confirm_overwrite": True}
    )
    assert done.status_code == 200 and done.json()["generated"] == 1
    versions = env.client.get(f"/api/items/{item_id}/sheet/versions").json()
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert versions[1]["content"]["usage_notes"] == "My note."


def test_manual_entry_and_sheet_errors(env: Env, engine: Engine) -> None:
    _, [item_id] = _seed(engine, ["shed light on"])
    missing = env.client.get(f"/api/items/{item_id}/sheet")
    assert missing.status_code == 404 and code(missing) == "sheet_not_found"
    assert code(env.client.get("/api/items/999/sheet")) == "item_not_found"

    empty = env.client.put(
        f"/api/items/{item_id}/sheet", json={"content": {"usage_notes": "SECRET-LOOKING-TEXT"}}
    )
    assert empty.status_code == 422 and code(empty) == "invalid_request"
    assert "SECRET-LOOKING-TEXT" not in empty.text
    unknown = env.client.put(f"/api/items/{item_id}/sheet", json={"content": {"x": 1}})
    assert unknown.status_code == 422

    typed = env.client.put(
        f"/api/items/{item_id}/sheet", json={"content": {"translation_fr": ["éclairer"]}}
    )
    assert typed.status_code == 200
    assert (typed.json()["provider"], typed.json()["sheet_status"]) == (None, "edited")
    assert env.client.get("/api/items", params={"q": "éclairer"}).json()["total"] == 1
    assert code(env.client.post("/api/items/999/sheet/regenerate", json={})) == "item_not_found"
    text = env.client.put(
        f"/api/items/{item_id}/sheet",
        content="translation_fr=x",
        headers={"Content-Type": "text/plain"},
    )
    assert text.status_code == 415


def test_exercises(env: Env, engine: Engine) -> None:
    item_id = _enrich(env, engine)[0]
    exercises = env.client.get(f"/api/items/{item_id}/exercises").json()
    assert len(exercises) == 9 and exercises[0]["exercise_type"] == "gap_fill"
    gap = exercises[0]
    bad = env.client.patch(f"/api/exercises/{gap['id']}", json={"content": {"sentence": "x"}})
    assert bad.status_code == 422 and code(bad) == "invalid_exercise"
    assert bad.json()["detail"]["errors"]
    good = env.client.patch(
        f"/api/exercises/{gap['id']}",
        json={"content": {"sentence": "We ___ it.", "answer": "account for"}},
    )
    assert good.status_code == 200 and good.json()["edited_by_user"]
    missing = env.client.patch("/api/exercises/999", json={"content": {}})
    assert missing.status_code == 404 and code(missing) == "exercise_not_found"
    assert code(env.client.get("/api/items/999/exercises")) == "item_not_found"


def _suggestions(*terms: str) -> Success:
    return Success(
        content={
            "suggestions": [
                {
                    "term": term,
                    "item_type": "collocation",
                    "category": "technical",
                    "example_sentence": f"We talk about {term} today.",
                }
                for term in terms
            ]
        }
    )


def test_extension_creates_terms_in_triage(env: Env, engine: Engine) -> None:
    deck_id, _ = _seed(engine)
    env.script(_suggestions("selection bias", "heteroskedasticity", "robust errors"))
    response = env.client.post(f"/api/decks/{deck_id}/extension", json={"count": 10})
    assert response.status_code == 201
    body = response.json()
    assert [i["term"] for i in body["created"]] == ["selection bias", "robust errors"]
    assert {i["status"] for i in body["created"]} == {"triage"}
    assert {i["sheet_status"] for i in body["created"]} == {"none"}
    assert (body["dropped_existing"], body["status"], body["reason"]) == (1, "ok", None)
    triage = env.client.get("/api/triage", params={"deck_id": deck_id}).json()
    assert [t["term"] for t in triage] == ["selection bias", "robust errors"]
    assert triage[0]["sentence"] == "We talk about selection bias today."

    decision = {"decisions": [{"item_id": body["created"][0]["id"], "decision": "known"}]}
    assert env.client.post("/api/triage", json=decision).status_code == 200
    item = env.client.get(f"/api/items/{body['created'][0]['id']}").json()
    assert item["status"] == "known" and item["decks"] == []


def test_extension_errors_and_degraded_mode(env: Env, engine: Engine) -> None:
    with Session(engine) as session:
        empty_id = library.create_deck(session, name="Empty", at=NOW).id
        session.commit()
    response = env.client.post(f"/api/decks/{empty_id}/extension", json={})
    assert response.status_code == 422 and code(response) == "not_enough_context"
    assert code(env.client.post("/api/decks/999/extension", json={})) == "deck_not_found"
    deck_id, _ = _seed(engine, name="Full")
    for count in (9, 31):
        bad = env.client.post(f"/api/decks/{deck_id}/extension", json={"count": count})
        assert bad.status_code == 422 and code(bad) == "invalid_request"
    env.provider.configured = False
    degraded = env.client.post(f"/api/decks/{deck_id}/extension")
    assert degraded.status_code == 200
    assert degraded.json()["status"] == "unavailable" and degraded.json()["created"] == []


def test_routes_need_a_database(env: Env, engine: Engine, tmp_path: Any) -> None:
    from app.db.engine import create_db_engine

    missing = create_db_engine(f"sqlite:///{(tmp_path / 'nothing.sqlite3').as_posix()}")
    env.client.app.dependency_overrides[get_engine] = lambda: missing  # type: ignore[attr-defined]
    try:
        response = env.client.post("/api/enrichment/run", json={})
        assert response.status_code == 503 and code(response) == "database_unavailable"
        assert not (tmp_path / "nothing.sqlite3").exists()
    finally:
        missing.dispose()
