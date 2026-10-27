"""Topic lists of the free productions (writing in module E, speaking in module F). Pure Python.

A topic file is versioned YAML: `{version, topics: [{id, en, fr, tags}]}`. Each module defines its
own tags (`writing_topics.py`, `speaking_topics.py`); the parsing and the daily pick are shared.

The pick is deterministic: the same study day, tag and recent prompts always give the same topics,
and the list turns by `count` topics a day. Topics used as a prompt in the last days are skipped,
unless that would leave nothing to propose.
"""

from collections.abc import Collection, Sequence
from functools import cache
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

DEFAULT_COUNT, MAX_COUNT = 3, 10
RECENT_DAYS = 7


class Topic(BaseModel):
    """A topic; subclasses narrow `tags` to their own enumeration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")]
    en: Annotated[str, Field(min_length=1, max_length=500)]
    fr: Annotated[str, Field(min_length=1, max_length=500)]
    tags: Annotated[list[str], Field(min_length=1)]


class TopicsError(ValueError):
    """A topics file is malformed."""


@cache
def _file_model(model: type[Topic]) -> type[BaseModel]:
    return create_model(
        f"{model.__name__}File",
        __config__=ConfigDict(extra="forbid"),
        version=(int, ...),
        topics=(Annotated[list[model], Field(min_length=1)], ...),  # type: ignore[valid-type]
    )


def parse_topic_file[T: Topic](data: Any, model: type[T], *, label: str) -> list[T]:
    """The topics of a file, validated as `model`. Raises TopicsError (`label` names the file in
    the message)."""
    try:
        topics: list[T] = _file_model(model).model_validate(data).topics  # type: ignore[attr-defined]
    except ValidationError as exc:
        raise TopicsError(f"invalid {label} file: {exc}") from exc
    ids = [topic.id for topic in topics]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TopicsError(f"invalid {label} file: duplicate topic ids: {', '.join(duplicates)}")
    return topics


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def pick_topics[T: Topic](
    topics: Sequence[T],
    *,
    day_number: int,
    count: int = DEFAULT_COUNT,
    tag: str | None = None,
    recent_prompts: Collection[str] = (),
) -> list[T]:
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
