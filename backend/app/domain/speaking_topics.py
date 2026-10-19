"""Free-speaking topics (module F): the tags of `content/speaking_topics.yaml`. Pure Python.

The same file format and daily pick as the writing topics (`app/domain/topics.py`). `presenting`
covers talks and the presentation of results (SPEC section 1: interviews and presentations).
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field

from app.domain.topics import Topic, parse_topic_file


class SpeakingTag(StrEnum):
    INTERVIEW = "interview"
    PRESENTING = "presenting"
    ACADEMIC = "academic"
    DATA_SCIENCE = "data_science"
    EVERYDAY = "everyday"
    CAMPUS = "campus"


class SpeakingTopic(Topic):
    tags: Annotated[list[SpeakingTag], Field(min_length=1)]  # type: ignore[assignment]


def parse_speaking_topics(data: Any) -> list[SpeakingTopic]:
    return parse_topic_file(data, SpeakingTopic, label="speaking topics")
