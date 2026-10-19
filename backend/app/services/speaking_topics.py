"""Free-speaking topics (module F): today's suggestions from `content/speaking_topics.yaml`.

No AI call: the topics are a versioned list, and the pick (`app/domain/topics.py`, shared with the
writing topics) skips the prompts of the spoken productions of the last days.
"""

from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.db.settings_store import get_setting
from app.domain.enums import Modality
from app.domain.speaking_topics import SpeakingTag, SpeakingTopic, parse_speaking_topics
from app.domain.study_day import study_day_of
from app.domain.topics import DEFAULT_COUNT, pick_topics
from app.services.writing_topics import recent_prompts

TOPICS_FILE = REPO_ROOT / "content" / "speaking_topics.yaml"


@cache
def load_topics(path: Path = TOPICS_FILE) -> tuple[SpeakingTopic, ...]:
    with path.open(encoding="utf-8") as file:
        return tuple(parse_speaking_topics(yaml.safe_load(file)))


def todays_topics(
    session: Session, now: datetime, *, count: int = DEFAULT_COUNT, tag: SpeakingTag | None = None
) -> list[SpeakingTopic]:
    tz = ZoneInfo(get_setting(session, "timezone"))
    day = study_day_of(now, tz, get_setting(session, "day_start_hour"))
    return pick_topics(
        load_topics(),
        day_number=day.toordinal(),
        count=count,
        tag=tag,
        recent_prompts=recent_prompts(session, now, modality=Modality.ORAL),
    )
