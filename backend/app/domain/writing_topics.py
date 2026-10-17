"""Free-writing topics (module E): parse the versioned list and pick today's topics. Pure Python.

The pick is deterministic: the same study day, tag and recent prompts always give the same topics,
and the list turns by `count` topics a day. Topics used as a prompt in the last days are skipped,
unless that would leave nothing to propose.
"""

from collections.abc import Collection, Sequence
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_COUNT, MAX_COUNT = 3, 10
RECENT_DAYS = 7


class TopicTag(StrEnum):
    ACADEMIC = "academic"
    INTERVIEW = "interview"
    DATA_SCIENCE = "data_science"
    EVERYDAY = "everyday"
    CAMPUS = "campus"


class WritingTopic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")]
    en: Annotated[str, Field(min_length=1, max_length=500)]
    fr: Annotated[str, Field(min_length=1, max_length=500)]
    tags: Annotated[list[TopicTag], Field(min_length=1)]


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    topics: Annotated[list[WritingTopic], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_ids(self) -> "_File":
        ids = [topic.id for topic in self.topics]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate topic ids: {', '.join(duplicates)}")
        return self


class TopicsError(ValueError):
    """The topics file is malformed."""


def parse_topics(data: Any) -> list[WritingTopic]:
    try:
        return _File.model_validate(data).topics
    except ValidationError as exc:
        raise TopicsError(f"invalid writing topics file: {exc}") from exc


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def pick_topics(
    topics: Sequence[WritingTopic],
    *,
    day_number: int,
    count: int = DEFAULT_COUNT,
    tag: TopicTag | None = None,
    recent_prompts: Collection[str] = (),
) -> list[WritingTopic]:
    """`count` topics for the study day `day_number` (any integer that grows by one a day).

    The candidates (the topics of `tag`, in file order) turn by `count` a day; a topic whose
    English or French text was a prompt recently is skipped, unless every candidate was.
    """
    candidates = [topic for topic in topics if tag is None or tag in topic.tags]
    if not candidates:
        return []
    recent = {_key(prompt) for prompt in recent_prompts}
    fresh = [t for t in candidates if _key(t.en) not in recent and _key(t.fr) not in recent]
    pool = fresh or candidates
    start = (day_number * count) % len(candidates)
    rotated = candidates[start:] + candidates[:start]
    return [topic for topic in rotated if topic in pool][:count]
