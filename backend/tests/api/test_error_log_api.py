"""Error log endpoints: manual entry, list, filters and facets, edit, delete, categories and the
AI's proposed subcategories (M5.a1)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ErrorCategory, ErrorEvent, EventLog
from app.db.taxonomy import load_taxonomy, sync_taxonomy
from app.domain.enums import ErrorCategoryStatus, ErrorSource
from app.domain.events import parse_event
from app.domain.taxonomy import Category, Taxonomy
from app.services import error_log
from tests.api.conftest import ApiEnv
from tests.api.session_support import code, quick_add


@pytest.fixture(autouse=True)
def taxonomy(env: ApiEnv) -> None:
    with Session(env.engine) as session:
        sync_taxonomy(session)
        session.commit()


def _manual(env: ApiEnv, **changes: Any) -> Any:
    body = {
        "original_text": "I am in campus every day.",
        "erroneous_text": "in campus",
        "correction": "on campus",
        "alternatives": ["at the campus"],
        "category_code": "grammar.preposition.fixed_expression",
        "explanation": "We say 'on campus'.",
        **changes,
    }
    return env.client.post("/api/errors", json=body)


def _events(env: ApiEnv, event_type: str) -> list[dict[str, Any]]:
    with Session(env.engine) as session:
        rows = session.scalars(
            select(EventLog).where(EventLog.event_type == event_type).order_by(EventLog.id)
        )
        return [parse_event(row.event_type, row.payload).model_dump() for row in rows]


def _add_error(
    env: ApiEnv, code_: str, source: ErrorSource, days_ago: int = 0, **fields: Any
) -> int:
    with Session(env.engine) as session:
        error = error_log.record_error(
            session,
            source=source,
            category=error_log.active_category(session, code_),
            erroneous_text=fields.pop("erroneous_text", "wrong"),
            correction=fields.pop("correction", "right"),
            at=env.clock.now() - timedelta(days=days_ago),
            **fields,
        )
        session.commit()
        return error.id


# --- Manual entry --------------------------------------------------------------------------------


def test_manual_error_is_recorded_with_its_event(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    response = _manual(env, lexical_item_id=item_id)
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "manual"
    assert body["category"] == {
        "code": "grammar.preposition.fixed_expression",
        "label_en": "Fixed expression",
        "label_fr": "Expression figée",
        "status": "active",
    }
    assert body["term"] == {"id": item_id, "term": "rule out"}
    assert (body["erroneous_text"], body["correction"], body["alternatives"]) == (
        "in campus",
        "on campus",
        ["at the campus"],
    )
    assert body["explanation_fr"] is None
    assert _events(env, "error.recorded") == [
        {
            "error_event_id": body["id"],
            "category_code": "grammar.preposition.fixed_expression",
            "source": "manual",
            "lexical_item_id": item_id,
        }
    ]


def test_manual_error_without_original_text(env: ApiEnv) -> None:
    response = _manual(env, original_text=None)
    assert response.status_code == 201
    assert response.json()["original_text"] == ""


@pytest.mark.parametrize(
    ("changes", "status", "error_code"),
    [
        ({"original_text": "I am on campus."}, 422, "invalid_error"),
        ({"correction": "in campus"}, 422, "invalid_error"),
        ({"correction": "  "}, 422, "invalid_error"),
        ({"category_code": "grammar.nothing"}, 422, "unknown_category"),
        ({"alternatives": ["a", "b", "c"]}, 422, "invalid_request"),
        ({"lexical_item_id": 999}, 404, "item_not_found"),
        ({"source": "review"}, 422, "invalid_request"),
    ],
)
def test_manual_error_validations(
    env: ApiEnv, changes: dict[str, Any], status: int, error_code: str
) -> None:
    response = _manual(env, **changes)
    assert (response.status_code, code(response)) == (status, error_code)
    with Session(env.engine) as session:
        assert session.scalar(select(ErrorEvent.id)) is None


def test_manual_error_accepts_apostrophe_and_space_differences(env: ApiEnv) -> None:
    response = _manual(
        env, original_text="It’s my  master’s degree.", erroneous_text="master's degree"
    )
    assert response.status_code == 201


def test_a_proposed_category_is_not_usable_by_hand(env: ApiEnv) -> None:
    _propose(env)
    response = _manual(env, category_code="grammar.preposition.fixed_expression.campus")
    assert (response.status_code, code(response)) == (422, "unknown_category")


# --- List, filters, facets ------------------------------------------------------------------------


def test_list_filters_facets_and_pagination(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    a = _add_error(env, "grammar.preposition.fixed_expression", ErrorSource.WRITING, 3)
    b = _add_error(env, "grammar.preposition.time", ErrorSource.REVIEW, 2, lexical_item_id=item_id)
    c = _add_error(env, "grammar.tense.past_simple_vs_present_perfect", ErrorSource.WRITING, 1)
    d = _add_error(
        env, "spelling", ErrorSource.MANUAL, 0, erroneous_text="recieve", correction="receive"
    )

    def ids(**params: Any) -> list[int]:
        response = env.client.get("/api/errors", params=params)
        assert response.status_code == 200
        return [error["id"] for error in response.json()["errors"]]

    assert ids() == [d, c, b, a]  # newest first
    assert ids(category="grammar.preposition") == [b, a]
    assert ids(category="grammar.prep") == []  # a prefix of whole segments
    assert ids(category="grammar") == [c, b, a]
    assert ids(source="writing") == [c, a]
    assert ids(item_id=item_id) == [b]
    assert ids(q="RECIEVE") == [d]
    start = (env.clock.now() - timedelta(days=2, hours=1)).isoformat()
    end = (env.clock.now() - timedelta(hours=12)).isoformat()
    assert ids(occurred_from=start, occurred_to=end) == [c, b]

    page = env.client.get("/api/errors", params={"page": 2, "page_size": 3}).json()
    assert ([e["id"] for e in page["errors"]], page["total"], page["page"]) == ([a], 4, 2)
    assert page["facets"] == [
        {
            "code": "grammar.preposition",
            "label_en": "Prepositions",
            "label_fr": "Prépositions",
            "count": 2,
        },
        {"code": "grammar.tense", "label_en": "Tenses", "label_fr": "Temps verbaux", "count": 1},
        {"code": "spelling", "label_en": "Spelling", "label_fr": "Orthographe", "count": 1},
    ]
    # Facets follow the filter, not the page.
    filtered = env.client.get("/api/errors", params={"source": "writing", "page_size": 1}).json()
    assert [(f["code"], f["count"]) for f in filtered["facets"]] == [
        ("grammar.preposition", 1),
        ("grammar.tense", 1),
    ]
    assert len(filtered["errors"]) == 1 and filtered["total"] == 2


def test_list_refuses_a_page_size_above_the_maximum(env: ApiEnv) -> None:
    response = env.client.get("/api/errors", params={"page_size": 101})
    assert (response.status_code, code(response)) == (422, "invalid_request")


def test_get_one_error(env: ApiEnv) -> None:
    error_id = _manual(env).json()["id"]
    assert env.client.get(f"/api/errors/{error_id}").json()["id"] == error_id
    response = env.client.get("/api/errors/999")
    assert (response.status_code, code(response)) == (404, "error_not_found")


# --- Edit and delete -----------------------------------------------------------------------------


def test_patch_writes_the_changed_fields_and_both_codes(env: ApiEnv) -> None:
    item_id = quick_add(env.client)
    error_id = _manual(env).json()["id"]
    response = env.client.patch(
        f"/api/errors/{error_id}",
        json={
            "category_code": "grammar.preposition.place",
            "explanation": "Place preposition.",
            "lexical_item_id": item_id,
            "correction": "on campus",  # unchanged
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category"]["code"] == "grammar.preposition.place"
    assert body["explanation"] == "Place preposition."
    assert body["term"]["id"] == item_id
    assert _events(env, "error.updated") == [
        {
            "error_event_id": error_id,
            "source": "manual",
            "changed": ["explanation", "category", "lexical_item_id"],
            "old_category_code": "grammar.preposition.fixed_expression",
            "new_category_code": "grammar.preposition.place",
            "old_lexical_item_id": None,
            "new_lexical_item_id": item_id,
            "reason": "edit",
        }
    ]
    # Unlink the term; an unchanged patch writes no event.
    env.client.patch(f"/api/errors/{error_id}", json={"lexical_item_id": None})
    env.client.patch(f"/api/errors/{error_id}", json={"alternatives": ["at the campus"]})
    updates = _events(env, "error.updated")
    assert len(updates) == 2 and updates[1]["changed"] == ["lexical_item_id"]
    assert env.client.get(f"/api/errors/{error_id}").json()["term"] is None


@pytest.mark.parametrize(
    ("body", "status", "error_code"),
    [
        ({"category_code": "grammar.unknown"}, 422, "unknown_category"),
        ({"correction": "in campus"}, 422, "invalid_error"),
        ({"erroneous_text": "x"}, 422, "invalid_request"),
        ({"lexical_item_id": 999}, 404, "item_not_found"),
    ],
)
def test_patch_validations(env: ApiEnv, body: dict[str, Any], status: int, error_code: str) -> None:
    error_id = _manual(env).json()["id"]
    response = env.client.patch(f"/api/errors/{error_id}", json=body)
    assert (response.status_code, code(response)) == (status, error_code)
    assert _events(env, "error.updated") == []


def test_patch_unknown_error(env: ApiEnv) -> None:
    response = env.client.patch("/api/errors/999", json={"explanation": "x"})
    assert (response.status_code, code(response)) == (404, "error_not_found")


def test_delete_removes_the_row_and_keeps_an_event(env: ApiEnv) -> None:
    error_id = _manual(env).json()["id"]
    response = env.client.delete(f"/api/errors/{error_id}")
    assert response.status_code == 204
    assert env.client.get(f"/api/errors/{error_id}").status_code == 404
    assert _events(env, "error.deleted") == [
        {
            "error_event_id": error_id,
            "category_code": "grammar.preposition.fixed_expression",
            "source": "manual",
        }
    ]
    assert len(_events(env, "error.recorded")) == 1  # the log is append-only
    assert env.client.delete(f"/api/errors/{error_id}").status_code == 404


# --- Categories ----------------------------------------------------------------------------------


def _find(nodes: list[dict[str, Any]], code_: str) -> dict[str, Any]:
    for node in nodes:
        if node["code"] == code_:
            return node
        found = _find(node["children"], code_) if node["children"] else None
        if found:
            return found
    return {}


def test_category_tree_with_counts(env: ApiEnv) -> None:
    _add_error(env, "grammar.preposition.fixed_expression", ErrorSource.WRITING, 1)
    _add_error(env, "grammar.preposition.time", ErrorSource.WRITING, 20)
    _add_error(env, "grammar.preposition", ErrorSource.MANUAL, 0)
    tree = env.client.get("/api/error-categories").json()
    assert [node["code"] for node in tree][:2] == ["grammar", "lexis"]
    preposition = _find(tree, "grammar.preposition")
    assert (preposition["count"], preposition["count_recent"]) == (3, 2)
    assert _find(tree, "grammar")["count"] == 3
    fixed = _find(tree, "grammar.preposition.fixed_expression")
    assert fixed == {
        "id": fixed["id"],
        "code": "grammar.preposition.fixed_expression",
        "parent_code": "grammar.preposition",
        "label_en": "Fixed expression",
        "label_fr": "Expression figée",
        "description_en": fixed["description_en"],
        "description_fr": fixed["description_fr"],
        "status": "active",
        "origin": "builtin",
        "count": 1,
        "count_recent": 1,
        "children": [],
    }
    assert _find(tree, "lexis")["count"] == 0


def test_user_category(env: ApiEnv) -> None:
    body = {
        "parent_code": "grammar.preposition",
        "slug": "with_transport",
        "label_en": "Transport",
        "label_fr": "Transports",
    }
    response = env.client.post("/api/error-categories", json=body)
    assert response.status_code == 201
    node = response.json()
    assert (node["code"], node["status"], node["origin"]) == (
        "grammar.preposition.with_transport",
        "active",
        "user",
    )
    assert _events(env, "error_category.created") == [
        {
            "error_category_id": node["id"],
            "code": "grammar.preposition.with_transport",
            "parent_code": "grammar.preposition",
        }
    ]
    # Usable at once.
    assert _manual(env, category_code="grammar.preposition.with_transport").status_code == 201
    again = env.client.post("/api/error-categories", json=body)
    assert (again.status_code, code(again)) == (409, "category_exists")


@pytest.mark.parametrize(
    ("changes", "status", "error_code"),
    [
        ({"slug": "Bad Slug"}, 422, "invalid_error"),
        ({"slug": "x"}, 422, "invalid_error"),
        ({"parent_code": "grammar.nothing"}, 422, "unknown_category"),
    ],
)
def test_user_category_validations(
    env: ApiEnv, changes: dict[str, Any], status: int, error_code: str
) -> None:
    body = {
        "parent_code": "grammar",
        "slug": "ok_slug",
        "label_en": "A",
        "label_fr": "B",
        **changes,
    }
    response = env.client.post("/api/error-categories", json=body)
    assert (response.status_code, code(response)) == (status, error_code)


def test_a_top_level_user_category(env: ApiEnv) -> None:
    body = {"slug": "style", "label_en": "Style", "label_fr": "Style"}
    node = env.client.post("/api/error-categories", json=body).json()
    assert (node["code"], node["parent_code"]) == ("style", None)


# --- Proposed subcategories ----------------------------------------------------------------------

PROPOSAL = error_log.Proposal(
    parent_code="grammar.preposition.fixed_expression",
    slug="campus",
    label_en="Campus expressions",
    label_fr="Expressions du campus",
    description_en="on campus, at university",
)


def _propose(env: ApiEnv, proposal: error_log.Proposal = PROPOSAL) -> error_log.ProposalOutcome:
    with Session(env.engine, expire_on_commit=False) as session:
        outcome = error_log.propose_category(session, proposal, at=env.clock.now())
        session.commit()
        return outcome


def test_a_proposal_is_created_once_and_reused(env: ApiEnv) -> None:
    first = _propose(env)
    second = _propose(env)
    assert first.proposed and not second.proposed
    assert first.category.id == second.category.id
    assert first.category.status == ErrorCategoryStatus.PROPOSED
    assert len(_events(env, "error_category.proposed")) == 1
    node = _find(env.client.get("/api/error-categories").json(), PROPOSAL.parent_code + ".campus")
    assert (node["status"], node["origin"]) == ("proposed", "ai")


def test_a_proposal_of_an_existing_active_code_uses_it(env: ApiEnv) -> None:
    outcome = _propose(
        env,
        error_log.Proposal("grammar.preposition", "time", "Time", "Temps", "at / on / in"),
    )
    assert not outcome.proposed and outcome.category.code == "grammar.preposition.time"
    assert _events(env, "error_category.proposed") == []


def test_accept_a_proposal(env: ApiEnv) -> None:
    category_id = _propose(env).category.id
    response = env.client.post(
        f"/api/error-categories/{category_id}/resolve",
        json={"decision": "accept", "label_en": "On campus"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["category"]["status"], body["category"]["label_en"]) == ("active", "On campus")
    assert body["category"]["label_fr"] == "Expressions du campus"
    assert body["reassigned_error_ids"] == []
    assert _events(env, "error_category.resolved")[0]["decision"] == "accept"
    again = env.client.post(
        f"/api/error-categories/{category_id}/resolve", json={"decision": "reject"}
    )
    assert (again.status_code, code(again)) == (409, "category_not_proposed")


def test_reject_a_proposal_moves_its_errors_to_the_parent(env: ApiEnv) -> None:
    category = _propose(env).category
    with Session(env.engine) as session:
        proposed = session.get_one(ErrorCategory, category.id)
        ids = [
            error_log.record_error(
                session,
                source=ErrorSource.WRITING,
                category=proposed,
                erroneous_text="in campus",
                correction="on campus",
                at=env.clock.now(),
            ).id
            for _ in range(2)
        ]
        session.commit()
    response = env.client.post(
        f"/api/error-categories/{category.id}/resolve", json={"decision": "reject"}
    )
    assert response.status_code == 200
    assert response.json()["reassigned_error_ids"] == ids
    assert response.json()["category"]["status"] == "rejected"
    for error_id in ids:
        error = env.client.get(f"/api/errors/{error_id}").json()
        assert error["category"]["code"] == "grammar.preposition.fixed_expression"
    updates = _events(env, "error.updated")
    assert [u["error_event_id"] for u in updates] == ids
    assert updates[0]["old_category_code"] == "grammar.preposition.fixed_expression.campus"
    assert updates[0]["new_category_code"] == "grammar.preposition.fixed_expression"
    assert updates[0]["reason"] == "category_rejected"
    resolved = _events(env, "error_category.resolved")
    assert resolved[0]["decision"] == "reject" and resolved[0]["reassigned_errors"] == 2
    # A rejected code is not proposed again: the parent is used.
    assert _propose(env).category.code == "grammar.preposition.fixed_expression"
    assert len(_events(env, "error_category.proposed")) == 1


def test_resolve_an_unknown_category(env: ApiEnv) -> None:
    response = env.client.post("/api/error-categories/9999/resolve", json={"decision": "accept"})
    assert (response.status_code, code(response)) == (404, "category_not_found")


def test_sync_taxonomy_never_touches_user_or_ai_categories(env: ApiEnv) -> None:
    proposed = _propose(env).category
    env.client.post(
        "/api/error-categories",
        json={"parent_code": "grammar", "slug": "mine", "label_en": "Mine", "label_fr": "À moi"},
    )
    rejected = _propose(
        env, error_log.Proposal("grammar.tense", "habits", "Habits", "Habitudes", "used to")
    ).category
    env.client.post(f"/api/error-categories/{rejected.id}/resolve", json={"decision": "reject"})

    def snapshot() -> dict[str, tuple[str, str, str, bool]]:
        with Session(env.engine) as session:
            return {
                c.code: (str(c.status), c.label_en, c.description_en, c.is_builtin)
                for c in session.scalars(
                    select(ErrorCategory).where(ErrorCategory.is_builtin.is_(False))
                )
            }

    before = snapshot()
    assert set(before) == {proposed.code, "grammar.mine", rejected.code}
    # Even a taxonomy file that now lists the same codes leaves them alone.
    base = load_taxonomy()
    clashing = [
        Category(code, code.rpartition(".")[0], "Built-in", "Intégré", "new", "", [], 99)
        for code in before
    ]
    with Session(env.engine) as session:
        sync_taxonomy(session)
        sync_taxonomy(session, Taxonomy(base.version, base.categories + clashing))
        session.commit()
    assert snapshot() == before
