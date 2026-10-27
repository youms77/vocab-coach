"""Free-writing topics (module E): the tags of `content/writing_topics.yaml`. Pure Python.

Parsing and the daily pick are shared with the speaking topics (`app/domain/topics.py`).
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field

from app.domain.topics import (
    DEFAULT_COUNT,
    MAX_COUNT,
    RECENT_DAYS,
    Topic,
    TopicsError,
    parse_topic_file,
    pick_topics,
)

__all__ = [
    "DEFAULT_COUNT",
    "MAX_COUNT",
    "RECENT_DAYS",
    "TopicTag",
    "TopicsError",
    "WritingTopic",
    "parse_topics",
    "pick_topics",
]


class TopicTag(StrEnum):
    ACADEMIC = "academic"
    INTERVIEW = "interview"
    DATA_SCIENCE = "data_science"
    EVERYDAY = "everyday"
    CAMPUS = "campus"


class WritingTopic(Topic):
    tags: Annotated[list[TopicTag], Field(min_length=1)]  # type: ignore[assignment]


def parse_topics(data: Any) -> list[WritingTopic]:
    return parse_topic_file(data, WritingTopic, label="writing topics")
