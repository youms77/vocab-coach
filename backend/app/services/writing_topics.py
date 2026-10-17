"""Free-writing topics (module E): today's suggestions from `content/writing_topics.yaml`.

No AI call: the topics are a versioned list, and the pick (`app/domain/writing_topics.py`) skips
the prompts of the productions written in the last days.
"""

from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.db.models import ProductionAttempt
from app.db.settings_store import get_setting
from app.domain.study_day import as_utc, study_day_of
from app.domain.writing_topics import (
    DEFAULT_COUNT,
    RECENT_DAYS,
    TopicTag,
    WritingTopic,
    parse_topics,
    pick_topics,
)

TOPICS_FILE = REPO_ROOT / "content" / "writing_topics.yaml"


@cache
def load_topics(path: Path = TOPICS_FILE) -> tuple[WritingTopic, ...]:
    with path.open(encoding="utf-8") as file:
        return tuple(parse_topics(yaml.safe_load(file)))


def recent_prompts(session: Session, now: datetime, days: int = RECENT_DAYS) -> list[str]:
    since = as_utc(now) - timedelta(days=days)
    rows = session.scalars(
        select(ProductionAttempt.prompt_text).where(
            ProductionAttempt.created_at >= since, ProductionAttempt.prompt_text.is_not(None)
        )
    )
    return [prompt for prompt in rows if prompt]


def todays_topics(
    session: Session, now: datetime, *, count: int = DEFAULT_COUNT, tag: TopicTag | None = None
) -> list[WritingTopic]:
    tz = ZoneInfo(get_setting(session, "timezone"))
    day = study_day_of(now, tz, get_setting(session, "day_start_hour"))
    return pick_topics(
        load_topics(),
        day_number=day.toordinal(),
        count=count,
        tag=tag,
        recent_prompts=recent_prompts(session, now),
    )
