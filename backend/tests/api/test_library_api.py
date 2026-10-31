"""Library endpoints end to end (/api/import, /items, /decks, /triage, /duplicates)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.engine import get_engine, get_session
from app.db.models import Deck, EventLog, LexicalItem
from app.main import create_app
from tests.factories import add_card
from tests.library_support import count, events

TEXT = """---
deck: Causal inference reading
domain: econometrics
source: "Angrist & Pischke, ch. 3"
deadline: 2099-11-20
---
- heteroskedasticity
- to account for | We account for regional fixed effects.
- bias = biais
- shed light on
"""


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = session_override
    with TestClient(app, base_url=f"http://127.0.0.1:{get_settings().port}") as test_client:
        yield test_client


def code(response: Any) -> str:
    return response.json()["detail"]["code"]


def preview_rows(client: TestClient, text: str = TEXT) -> list[dict[str, Any]]:
    body = client.post("/api/import/preview", json={"text": text}).json()
    return [
        {"line": r["line"], "term": r["term"], "sentence": r["sentence"], "include": r["include"]}
        for r in body["rows"]
    ]


def import_text(client: TestClient, text: str = TEXT, **extra: Any) -> dict[str, Any]:
    preview = client.post("/api/import/preview", json={"text": text}).json()
    rows = preview_rows(client, text)
    response = client.post(
        "/api/import/commit", json={"header": preview["header"], "rows": rows, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


def add(client: TestClient, term: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/api/items", json={"term": term, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# --- Import --------------------------------------------------------------------------------------


def test_preview_then_commit(client: TestClient, engine: Engine) -> None:
    response = client.post("/api/import/preview", json={"text": TEXT})
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["deck"] == "Causal inference reading"
    assert [(r["line"], r["include"], r["ambiguous"]) for r in body["rows"]] == [
        (7, True, False),
        (8, True, False),
        (9, False, True),
        (10, True, False),
    ]
    problem = body["rows"][2]["problems"][0]
    assert problem == {
        "line": 9,
        "severity": "ambiguous",
        "code": "looks_like_definition",
        "message": problem["message"],
        "suggestion": {"term": "bias", "note": "biais"},
    }
    with Session(engine) as session:
        assert count(session, LexicalItem) == 0 and count(session, EventLog) == 0

    summary = import_text(client, intake="queued")
    assert {
        k: summary[k] for k in ("lines_read", "imported", "attached", "skipped", "ambiguous")
    } == {
        "lines_read": 4,
        "imported": 3,
        "attached": 0,
        "skipped": 1,
        "ambiguous": 1,
    }
    deck = client.get(f"/api/decks/{summary['deck_id']}").json()
    assert deck["items_by_status"] == {"queued": 3} and deck["source"]["title"].startswith(
        "Angrist"
    )


def test_commit_errors(client: TestClient) -> None:
    rows = [{"term": "bias = biais", "include": True}]
    response = client.post("/api/import/commit", json={"header": {"deck": "D"}, "rows": rows})
    assert response.status_code == 422 and code(response) == "row_rejected"
    assert response.json()["detail"]["problems"] == ["looks_like_definition"]
    response = client.post("/api/import/commit", json={"rows": [{"term": "bias"}]})
    assert response.status_code == 422 and code(response) == "deck_name_required"
    response = client.post(
        "/api/import/commit", json={"rows": [{"term": "bias"}], "target": {"deck_id": 99}}
    )
    assert response.status_code == 404 and code(response) == "deck_not_found"


def test_preview_csv_then_commit(client: TestClient) -> None:
    text = "terme;phrase\nbias;The bias is small.\nodds ratio\n"
    response = client.post("/api/import/preview", json={"text": text, "format": "csv"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["deck"] is None
    assert [(r["line"], r["term"], r["sentence"]) for r in body["rows"]] == [
        (2, "bias", "The bias is small."),
        (3, "odds ratio", None),
    ]
    assert [p["code"] for p in body["problems"]] == ["header_row_skipped"]
    summary = client.post(
        "/api/import/commit",
        json={
            "rows": [{"term": r["term"], "sentence": r["sentence"]} for r in body["rows"]],
            "target": {"new_deck_name": "From Excel"},
        },
    )
    assert summary.status_code == 200 and summary.json()["imported"] == 2


def test_preview_tsv_and_unknown_format(client: TestClient) -> None:
    body = client.post(
        "/api/import/preview", json={"text": "bias\tA, b; c\n", "format": "tsv"}
    ).json()
    assert [(r["term"], r["sentence"]) for r in body["rows"]] == [("bias", "A, b; c")]
    response = client.post("/api/import/preview", json={"text": "x", "format": "xlsx"})
    assert response.status_code == 422 and code(response) == "invalid_request"


def test_preview_size_limit_and_body_type(client: TestClient) -> None:
    body = client.post("/api/import/preview", json={"text": "- x\n" * 1001}).json()
    assert body["rejected"] and body["problems"][0]["code"] == "too_large"
    response = client.post("/api/import/preview", json={"text": "x" * 300_001})
    assert response.status_code == 422 and code(response) == "invalid_request"
    response = client.post(
        "/api/import/preview", content="- bias", headers={"Content-Type": "text/markdown"}
    )
    assert response.status_code == 415 and code(response) == "unsupported_media_type"
    response = client.post(
        "/api/import/preview",
        content=b"--b\r\nContent-Disposition: form-data; name=file\r\n\r\n- x\r\n--b--",
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert response.status_code == 415


def test_422_does_not_echo_the_received_value(client: TestClient) -> None:
    marker = "UNIQUE-RECOGNISABLE-VALUE-12345"
    response = client.post("/api/items", json={"term": marker, "deck_id": marker})
    assert response.status_code == 422 and code(response) == "invalid_request"
    assert marker not in response.text
    response = client.post(
        "/api/import/commit", json={"rows": [{"term": "x", "on_duplicate": marker}]}
    )
    assert response.status_code == 422 and marker not in response.text


# --- Items ---------------------------------------------------------------------------------------


def test_quick_add_and_duplicate(client: TestClient) -> None:
    first = add(client, "Shed light on", sentence="It sheds light on it.")
    assert first["item"]["status"] == "queued" and not first["attached"]
    assert first["item"]["decks"][0]["name"] == "Quick adds"
    response = client.post("/api/items", json={"term": "to shed light on"})
    assert response.status_code == 409 and code(response) == "duplicate_term"
    assert [c["id"] for c in response.json()["detail"]["candidates"]] == [first["item"]["id"]]
    deck = client.post("/api/decks", json={"name": "Talk"}).json()
    attached = add(client, "to shed light on", deck_id=deck["id"], on_duplicate="attach")
    assert attached["attached"] and attached["item"]["id"] == first["item"]["id"]
    response = client.post("/api/items", json={"term": "  "})
    assert response.status_code == 422 and code(response) == "invalid_term"


def test_list_items_filters_and_paging(client: TestClient) -> None:
    summary = import_text(client)
    add(client, "100% sure")
    add(client, "obsolete")
    obsolete = client.get("/api/items", params={"q": "obsolete"}).json()["items"][0]
    client.post(f"/api/items/{obsolete['id']}/status", json={"to": "archived"})

    def terms(**params: Any) -> list[str]:
        response = client.get("/api/items", params=params)
        assert response.status_code == 200, response.text
        return [item["term"] for item in response.json()["items"]]

    assert terms(deck_id=summary["deck_id"]) == [
        "heteroskedasticity",
        "to account for",
        "shed light on",
    ]
    assert terms(q="%") == ["100% sure"]
    assert terms(q="REGIONAL") == ["to account for"]
    assert terms(domain="econometrics", item_type="word") == ["heteroskedasticity"]
    assert terms(status=["triage", "archived"], sort="term") == [
        "heteroskedasticity",
        "obsolete",
        "shed light on",
        "to account for",
    ]
    assert "obsolete" not in terms() and "obsolete" in terms(include_archived=True)
    page = client.get("/api/items", params={"sort": "term", "order": "desc", "limit": 2}).json()
    assert page["total"] == 4 and [i["term"] for i in page["items"]] == [
        "to account for",
        "shed light on",
    ]
    source_id = client.get(f"/api/decks/{summary['deck_id']}").json()["source"]["id"]
    assert len(terms(source_id=source_id)) == 3
    for bad in ({"limit": 0}, {"limit": 201}, {"offset": -1}, {"status": "nope"}, {"sort": "x"}):
        response = client.get("/api/items", params=bad)
        assert response.status_code == 422 and code(response) == "invalid_request"


def test_get_patch_delete_item(client: TestClient, engine: Engine) -> None:
    add(client, "results")
    item = add(client, "outcome")["item"]
    detail = client.get(f"/api/items/{item['id']}").json()
    assert detail["has_history"] is False and detail["deck_links"][0]["deck_name"] == "Quick adds"
    response = client.patch(f"/api/items/{item['id']}", json={"term": "Result", "notes": "n"})
    assert response.status_code == 200
    body = response.json()
    assert (body["term"], body["normalized_form"], body["lemma"]) == ("Result", "result", "result")
    assert [(d["term"], d["match"]) for d in body["duplicates"]] == [("results", "possible")]
    response = client.patch(f"/api/items/{item['id']}", json={"term": None})
    assert response.status_code == 422 and code(response) == "invalid_term"
    response = client.patch(f"/api/items/{item['id']}", json={"status": "known"})
    assert response.status_code == 422
    assert client.delete(f"/api/items/{item['id']}").status_code == 204
    assert client.get(f"/api/items/{item['id']}").status_code == 404
    assert code(client.delete(f"/api/items/{item['id']}")) == "item_not_found"


def test_delete_item_with_history(client: TestClient, engine: Engine) -> None:
    item = add(client, "bias")["item"]
    with Session(engine) as session:
        add_card(session, session.get(LexicalItem, item["id"]))  # type: ignore[arg-type]
        session.commit()
    response = client.delete(f"/api/items/{item['id']}")
    assert response.status_code == 409 and code(response) == "item_has_history"
    assert response.json()["detail"]["suggestion"] == "archive"
    assert client.get(f"/api/items/{item['id']}").json()["has_history"] is True


def test_status_changes(client: TestClient) -> None:
    item = add(client, "bias")["item"]
    url = f"/api/items/{item['id']}/status"
    assert client.post(url, json={"to": "known"}).json()["status"] == "known"
    response = client.post(url, json={"to": "learning"})
    assert response.status_code == 409 and code(response) == "invalid_transition"
    assert client.post(url, json={"to": "archived"}).json()["status"] == "archived"
    response = client.post(url, json={"to": "learning"})  # no cards: unarchive goes to queued
    assert response.status_code == 409 and code(response) == "invalid_transition"
    assert client.post(url, json={"to": "queued"}).json()["status"] == "queued"
    response = client.post(url, json={"to": "discovering"})  # not a manual transition
    assert response.status_code == 409
    assert code(client.post("/api/items/999/status", json={"to": "known"})) == "item_not_found"


def test_merge(client: TestClient, engine: Engine) -> None:
    deck = client.post("/api/decks", json={"name": "Talk"}).json()
    kept = add(client, "bias")["item"]
    merged = add(client, "Bias", deck_id=deck["id"], on_duplicate="new")["item"]
    groups = client.get("/api/duplicates").json()
    assert [(g["match"], g["key"], [i["id"] for i in g["items"]]) for g in groups] == [
        ("exact", "bias", [kept["id"], merged["id"]])
    ]
    response = client.post(f"/api/items/{merged['id']}/merge", json={"into": kept["id"]})
    assert response.json() == {"kept_id": kept["id"], "removed_id": merged["id"], "inverted": False}
    assert {d["name"] for d in client.get(f"/api/items/{kept['id']}").json()["decks"]} == {
        "Quick adds",
        "Talk",
    }
    assert client.get("/api/duplicates").json() == []

    other = add(client, "bias", on_duplicate="new")["item"]
    with Session(engine) as session:
        for item_id in (kept["id"], other["id"]):
            add_card(session, session.get(LexicalItem, item_id))  # type: ignore[arg-type]
        session.commit()
    response = client.post(f"/api/items/{other['id']}/merge", json={"into": kept["id"]})
    assert response.status_code == 409 and code(response) == "merge_conflict"
    response = client.post(f"/api/items/{kept['id']}/merge", json={"into": kept["id"]})
    assert response.status_code == 422 and code(response) == "merge_same_item"


# --- Decks ---------------------------------------------------------------------------------------


def test_deck_crud(client: TestClient, engine: Engine) -> None:
    response = client.post(
        "/api/decks", json={"name": "Talk", "domain": "speaking", "deadline": "2026-12-01"}
    )
    assert response.status_code == 201
    deck = response.json()
    assert (deck["status"], deck["kind"], deck["item_count"]) == ("queued", "custom", 0)
    add(client, "small talk", deck_id=deck["id"])
    response = client.patch(f"/api/decks/{deck['id']}", json={"name": "Job talk", "priority": 2})
    assert (response.json()["name"], response.json()["item_count"]) == ("Job talk", 1)
    assert [d["name"] for d in client.get("/api/decks").json()] == ["Job talk"]
    for bad in ({"name": ""}, {"name": None}, {"status": "done"}):
        response = client.patch(f"/api/decks/{deck['id']}", json=bad)
        assert response.status_code == 422, bad
    response = client.post("/api/decks", json={"name": "X", "source_id": 42})
    assert response.status_code == 404 and code(response) == "source_not_found"

    response = client.delete(f"/api/decks/{deck['id']}")
    assert response.status_code == 200 and len(response.json()["deleted_item_ids"]) == 1
    assert client.get(f"/api/decks/{deck['id']}").status_code == 404
    with Session(engine) as session:
        assert count(session, Deck) == 0 and count(session, LexicalItem) == 0
        assert len(events(session, "deck.updated")) == 1


def test_delete_deck_with_history(client: TestClient, engine: Engine) -> None:
    item = add(client, "bias")["item"]
    deck_id = client.get("/api/decks").json()[0]["id"]
    with Session(engine) as session:
        add_card(session, session.get(LexicalItem, item["id"]))  # type: ignore[arg-type]
        session.commit()
    response = client.delete(f"/api/decks/{deck_id}")
    assert response.status_code == 409 and code(response) == "deck_has_history"


# --- Triage --------------------------------------------------------------------------------------


def test_triage(client: TestClient, engine: Engine) -> None:
    summary = import_text(client)
    entries = client.get("/api/triage", params={"deck_id": summary["deck_id"]}).json()
    assert [e["term"] for e in entries] == ["heteroskedasticity", "to account for", "shed light on"]
    assert set(entries[0]) == {"item_id", "term", "item_type", "sentence", "decks"}
    first, second, third = (e["item_id"] for e in entries)
    response = client.post(
        "/api/triage",
        json={
            "decisions": [
                {"item_id": first, "decision": "known"},
                {"item_id": second, "decision": "unsure"},
            ]
        },
    )
    assert response.json() == {"known": 1, "unsure": 1, "learn": 0}
    assert [e["item_id"] for e in client.get("/api/triage").json()] == [third]
    response = client.post(
        "/api/triage",
        json={
            "decisions": [
                {"item_id": third, "decision": "learn"},
                {"item_id": first, "decision": "learn"},
            ]
        },
    )
    assert response.status_code == 409 and code(response) == "not_in_triage"
    assert response.json()["detail"]["item_ids"] == [first]
    assert client.get("/api/triage").json()[0]["item_id"] == third  # nothing changed
    response = client.post("/api/triage", json={"decisions": []})
    assert response.status_code == 422
    with Session(engine) as session:
        assert [e["decision"] for e in events(session, "item.triaged")] == ["known", "unsure"]


def test_routes_need_a_database(client: TestClient, tmp_path: Any) -> None:
    from app.db.engine import create_db_engine

    missing = create_db_engine(f"sqlite:///{(tmp_path / 'missing.sqlite3').as_posix()}")
    client.app.dependency_overrides[get_engine] = lambda: missing  # type: ignore[attr-defined]
    try:
        response = client.get("/api/items")
        assert response.status_code == 503 and code(response) == "database_unavailable"
    finally:
        missing.dispose()
