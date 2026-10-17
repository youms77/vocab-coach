"""Free-writing topics: the versioned file and the daily pick (app/domain/writing_topics.py)."""

import pytest

from app.domain.writing_topics import TopicsError, TopicTag, WritingTopic, parse_topics, pick_topics
from app.services.writing_topics import load_topics


def _topic(n: int, *tags: TopicTag) -> WritingTopic:
    return WritingTopic(
        id=f"t{n}", en=f"Topic {n}.", fr=f"Sujet {n}.", tags=list(tags) or [TopicTag.EVERYDAY]
    )


TOPICS = [_topic(n) for n in range(1, 8)]


def _ids(topics: list[WritingTopic]) -> list[str]:
    return [topic.id for topic in topics]


def test_the_file_has_about_thirty_topics_with_every_tag() -> None:
    topics = load_topics()
    assert 25 <= len(topics) <= 40
    assert {tag for topic in topics for tag in topic.tags} == set(TopicTag)


def test_the_pick_is_deterministic_and_turns_every_day() -> None:
    assert _ids(pick_topics(TOPICS, day_number=0)) == ["t1", "t2", "t3"]
    assert _ids(pick_topics(TOPICS, day_number=0)) == ["t1", "t2", "t3"]
    assert _ids(pick_topics(TOPICS, day_number=1)) == ["t4", "t5", "t6"]
    assert _ids(pick_topics(TOPICS, day_number=2)) == ["t7", "t1", "t2"]  # wraps around
    assert _ids(pick_topics(TOPICS, day_number=0, count=1)) == ["t1"]


def test_recent_prompts_are_skipped() -> None:
    recent = ["  topic 2. ", "Sujet 3."]  # spaces and case do not matter; French counts too
    assert _ids(pick_topics(TOPICS, day_number=0, recent_prompts=recent)) == ["t1", "t4", "t5"]


def test_when_every_topic_is_recent_they_are_proposed_again() -> None:
    recent = [topic.en for topic in TOPICS]
    assert _ids(pick_topics(TOPICS, day_number=0, recent_prompts=recent)) == ["t1", "t2", "t3"]


def test_a_tag_keeps_its_topics_only() -> None:
    topics = [_topic(1, TopicTag.CAMPUS), _topic(2), _topic(3, TopicTag.CAMPUS, TopicTag.ACADEMIC)]
    assert _ids(pick_topics(topics, day_number=5, tag=TopicTag.CAMPUS)) == ["t3", "t1"]
    assert pick_topics(topics, day_number=5, tag=TopicTag.INTERVIEW) == []


def test_a_malformed_file_is_refused() -> None:
    topic = {"id": "a1", "en": "A.", "fr": "A.", "tags": ["everyday"]}
    with pytest.raises(TopicsError, match="duplicate"):
        parse_topics({"version": 1, "topics": [topic, topic]})
    with pytest.raises(TopicsError):
        parse_topics({"version": 1, "topics": [{**topic, "tags": ["unknown"]}]})
