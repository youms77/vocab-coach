"""`GET /api/writing/topics`: daily rotation, tag, recent prompts skipped."""

from sqlalchemy.orm import Session

from app.services.productions import record_written_production
from tests.api.conftest import ApiEnv
from tests.api.session_support import code


def _ids(env: ApiEnv, **params: object) -> list[str]:
    response = env.client.get("/api/writing/topics", params=params)
    assert response.status_code == 200
    return [topic["id"] for topic in response.json()]


def test_topics_of_the_day(env: ApiEnv) -> None:
    today = _ids(env)
    assert len(today) == 3 and today == _ids(env)
    first = env.client.get("/api/writing/topics").json()[0]
    assert set(first) == {"id", "en", "fr", "tags"}
    env.clock.advance(86_400)
    assert _ids(env) != today
    assert len(_ids(env, count=5)) == 5


def test_tag_filter(env: ApiEnv) -> None:
    for topic in env.client.get("/api/writing/topics", params={"tag": "interview"}).json():
        assert "interview" in topic["tags"]
    response = env.client.get("/api/writing/topics", params={"tag": "poetry"})
    assert (response.status_code, code(response)) == (422, "invalid_request")
    assert env.client.get("/api/writing/topics", params={"count": 11}).status_code == 422


def test_a_topic_written_this_week_is_not_proposed(env: ApiEnv) -> None:
    topics = env.client.get("/api/writing/topics").json()
    with Session(env.engine) as session:
        record_written_production(
            session, text="My answer.", prompt=topics[0]["en"], targets={}, at=env.clock.now()
        )
        session.commit()
    assert topics[0]["id"] not in _ids(env)
    env.clock.advance(8 * 86_400)
    # A week later the production no longer counts (the rotation moved on anyway).
    assert len(_ids(env, count=10)) == 10
