"""Free-writing endpoints (module E, M5.a1): today's suggested topics. No AI call."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.domain.writing_topics import DEFAULT_COUNT, MAX_COUNT, TopicTag, WritingTopic
from app.services.writing_topics import todays_topics

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/writing/topics", tags=["writing"])
def topics(
    session: SessionDep,
    now: NowDep,
    count: Annotated[int, Query(ge=1, le=MAX_COUNT)] = DEFAULT_COUNT,
    tag: TopicTag | None = None,
) -> list[WritingTopic]:
    """Today's topics (`{id, en, fr, tags}`): the same all day, different the next day, never a
    topic used as a prompt in the last 7 days (unless every topic of the tag was)."""
    return todays_topics(session, now, count=count, tag=tag)
