"""Consolidation tasks in the services (app/services/consolidation.py, M7.a1) with the fake
provider: creation with the AI and from a template, the AI call outside any transaction,
concurrency, statuses and the export."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind
from app.db.models import ConsolidationTask, EventLog, LexicalItem
from app.domain.consolidation import NotReadyReason, TaskStatus, TaskType, term_ref
from app.domain.enums import ConsolidationTaskKind, ConsolidationTaskStatus, ItemStatus
from app.services import consolidation
from app.services.consolidation import InvalidTransition, NotReady, TaskNotFound, TaskOpen
from app.services.library import DeckNotFound
from tests.consolidation_deck_support import ready_deck
from tests.consolidation_support import broken, task_output

AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
def factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


def gateway_for(engine: Engine, provider: FakeProvider) -> Gateway:
    return Gateway(
        {provider.name: provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: [provider.name],
        sleep=lambda _: None,
    )


def failing(engine: Engine) -> Gateway:
    return gateway_for(engine, FakeProvider("fake", [Failure(ErrorKind.AUTH)]))


@pytest.fixture
def deck_id(engine: Engine) -> int:
    with Session(engine) as session:
        deck, _ = ready_deck(session, 10)
        session.commit()
        return deck.id


def make(factory, gateway, deck_id: int, **kwargs):
    task_type = kwargs.pop("task_type", TaskType.TALK)
    return consolidation.create_task(
        factory, gateway, deck_id, task_type, clock=lambda: AT, **kwargs
    )


def refs(count: int) -> list[str]:
    return [term_ref(i) for i in range(count)]


def test_a_task_from_the_ai(engine, factory, deck_id) -> None:
    provider = FakeProvider("fake", [Success(content=task_output(refs(10)))])
    result = make(factory, gateway_for(engine, provider), deck_id, term_count=10)
    assert (result.source, result.reason) == ("ai", None)
    with factory() as session:
        task = consolidation.get_task(session, result.task_id)
        structure = task.suggested_structure
        assert task.status is ConsolidationTaskStatus.PROPOSED
        assert task.task_kind is ConsolidationTaskKind.PRESENTATION
        assert task.topic == structure["title"]["en"]
        assert structure["format"] == "consolidation-task-1"
        assert structure["prompt_version"] == "consolidation_task.v1"
        assert structure["provider"] == "fake" and structure["ai_call_id"] is not None
        ids = consolidation.task_item_ids(session, task.id)
        assert len(ids) == 10
        in_sections = [i for s in structure["sections"] for i in s["item_ids"]]
        assert sorted(in_sections) == sorted(ids)
        events = session.scalars(
            select(EventLog.event_type).where(EventLog.entity_type == "consolidation_task")
        ).all()
        assert events == ["consolidation.task_created"]
    sent = str(provider.requests[0])
    assert "term number 1" in sent and "t10" in sent


def test_terms_are_the_most_fragile_first(engine, factory) -> None:
    with Session(engine) as session:
        deck, items = ready_deck(session, 14, stability=lambda n: 30.0 - n)
        session.commit()
        deck_id, expected = deck.id, [i.id for i in reversed(items)][:9]
    provider = FakeProvider("fake", [Success(content=task_output(refs(9)))])
    result = make(factory, gateway_for(engine, provider), deck_id, term_count=9)
    with factory() as session:
        assert consolidation.task_item_ids(session, result.task_id) == expected


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        ([Failure(ErrorKind.NETWORK)], "all_failed"),
        ([Failure(ErrorKind.AUTH)], "auth"),
        ([Failure(ErrorKind.QUOTA_EXHAUSTED)], "quota"),
        ([Success(content=broken("unknown_ref"))], "incomplete"),
    ],
)
def test_a_template_when_the_ai_fails(engine, factory, deck_id, script, reason) -> None:
    result = make(factory, gateway_for(engine, FakeProvider("fake", script)), deck_id)
    assert result.source == "template"
    assert result.reason is not None
    with factory() as session:
        task = consolidation.get_task(session, result.task_id)
        assert task.suggested_structure["source"] == "template"
        assert task.suggested_structure["reason"] == result.reason
        assert task.suggested_structure["provider"] is None
        assert len(consolidation.task_item_ids(session, task.id)) == 10


def test_the_reason_of_a_template(engine, factory, deck_id) -> None:
    bad = FakeProvider("fake", [Success(content=broken("unknown_ref"))])
    assert make(factory, gateway_for(engine, bad), deck_id).reason == "incomplete"


def test_a_template_without_a_provider(engine, factory, deck_id) -> None:
    gateway = gateway_for(engine, FakeProvider("fake", [Success()], configured=False))
    result = make(factory, gateway, deck_id, task_type=TaskType.INTERVIEW_ANSWER)
    assert (result.source, result.reason) == ("template", "no_provider_configured")
    with factory() as session:
        task = consolidation.get_task(session, result.task_id)
        assert task.task_kind is ConsolidationTaskKind.INTERVIEW_ANSWER


def test_a_repair_is_accepted(engine, factory, deck_id) -> None:
    provider = FakeProvider(
        "fake", [Success(content=broken("wrong_type")), Success(content=task_output(refs(10)))]
    )
    assert make(factory, gateway_for(engine, provider), deck_id).source == "ai"


def test_no_session_is_open_during_the_ai_call(engine, factory, deck_id, db_url) -> None:
    path = db_url.removeprefix("sqlite:///")
    probes: list[str] = []

    class Probing(FakeProvider):
        def generate_json(self, request):
            with sqlite3.connect(path, timeout=0.5) as other:
                other.execute("BEGIN IMMEDIATE")  # raises 'database is locked' if a writer is open
                other.rollback()
            probes.append("free")
            return super().generate_json(request)

    provider = Probing("fake", [Success(content=task_output(refs(10)))])
    make(factory, gateway_for(engine, provider), deck_id, term_count=10)
    assert probes == ["free"]


def test_a_task_created_meanwhile_gives_task_open(engine, factory, deck_id) -> None:
    class Racing(FakeProvider):
        def generate_json(self, request):
            make(factory, failing(engine), deck_id)
            return super().generate_json(request)

    provider = Racing("fake", [Success(content=task_output(refs(10)))])
    with pytest.raises(TaskOpen) as caught:
        make(factory, gateway_for(engine, provider), deck_id, term_count=10)
    assert caught.value.extra["task_id"] is not None
    with factory() as session:
        assert len(session.scalars(select(ConsolidationTask)).all()) == 1


def test_an_open_task_blocks_a_second(engine, factory, deck_id) -> None:
    first = make(factory, failing(engine), deck_id)
    with pytest.raises(TaskOpen) as caught:
        make(factory, failing(engine), deck_id)
    assert caught.value.extra["task_id"] == first.task_id


def test_not_ready_and_unknown_deck(engine, factory) -> None:
    with Session(engine) as session:
        deck, _ = ready_deck(session, 7)
        session.commit()
        deck_id = deck.id
    with pytest.raises(NotReady) as caught:
        make(factory, failing(engine), deck_id)
    assert caught.value.extra["reason"] == NotReadyReason.NOT_ENOUGH_CANDIDATES.value
    with pytest.raises(DeckNotFound):
        make(factory, failing(engine), 999)


def test_a_term_that_leaves_meanwhile_gives_not_ready(engine, factory) -> None:
    with Session(engine) as session:
        deck, items = ready_deck(session, 9)
        session.commit()
        deck_id, first = deck.id, items[0].id

    class Archiving(FakeProvider):
        def generate_json(self, request):
            with Session(engine) as other:
                other.get(LexicalItem, first).status = ItemStatus.ARCHIVED
                other.commit()
            return super().generate_json(request)

    provider = Archiving("fake", [Success(content=task_output(refs(9)))])
    with pytest.raises(NotReady):
        make(factory, gateway_for(engine, provider), deck_id, term_count=9)
    with factory() as session:
        assert session.scalars(select(ConsolidationTask)).all() == []


def test_the_overview(engine, factory, deck_id) -> None:
    with Session(engine) as session:
        states = consolidation.deck_overview(session)
        assert [s.readiness.ready for s in states] == [True]
        assert states[0].threshold_ratio == 0.8 and states[0].min_stability_days == 7
    make(factory, failing(engine), deck_id)
    with Session(engine) as session:
        (state,) = consolidation.deck_overview(session)
        assert state.readiness.reason is NotReadyReason.TASK_OPEN
        assert state.open_task_id is not None


def test_statuses(engine, factory, deck_id) -> None:
    task_id = make(factory, failing(engine), deck_id).task_id
    with factory() as session:
        with pytest.raises(InvalidTransition):
            consolidation.change_status(session, task_id, TaskStatus.COMPLETED, at=AT)
        consolidation.change_status(session, task_id, TaskStatus.ACCEPTED, at=AT)
        task = consolidation.change_status(session, task_id, TaskStatus.COMPLETED, at=AT)
        assert task.status is ConsolidationTaskStatus.DONE and task.completed_at is not None
        with pytest.raises(InvalidTransition):
            consolidation.change_status(session, task_id, TaskStatus.DISMISSED, at=AT)
        session.commit()
        events = session.scalars(
            select(EventLog.payload).where(
                EventLog.event_type == "consolidation.task_status_changed"
            )
        ).all()
        assert [(e["from_status"], e["to_status"]) for e in events] == [
            ("proposed", "accepted"),
            ("accepted", "completed"),
        ]
        with pytest.raises(TaskNotFound):
            consolidation.change_status(session, 999, TaskStatus.ACCEPTED, at=AT)


def test_a_closed_task_frees_the_deck(engine, factory, deck_id) -> None:
    first = make(factory, failing(engine), deck_id).task_id
    with factory() as session:
        consolidation.change_status(session, first, TaskStatus.DISMISSED, at=AT)
        session.commit()
    assert make(factory, failing(engine), deck_id).task_id != first


def test_listing(engine, factory, deck_id) -> None:
    first = make(factory, failing(engine), deck_id).task_id
    with factory() as session:
        consolidation.change_status(session, first, TaskStatus.DISMISSED, at=AT)
        session.commit()
    second = make(factory, failing(engine), deck_id).task_id
    with factory() as session:
        page, total = consolidation.list_tasks(session)
        assert [t.id for t in page] == [second, first] and total == 2
        page, total = consolidation.list_tasks(session, status=TaskStatus.DISMISSED)
        assert [t.id for t in page] == [first] and total == 1
        assert consolidation.list_tasks(session, deck_id=999) == ([], 0)


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_the_export(engine, factory, deck_id, lang) -> None:
    provider = FakeProvider("fake", [Success(content=task_output(refs(10)))])
    task_id = make(factory, gateway_for(engine, provider), deck_id, term_count=10).task_id
    with factory() as session:
        task = consolidation.get_task(session, task_id)
        text = consolidation.export_markdown(session, task, lang)
        assert text.startswith("# ")
        assert all(f"**term number {n}**" in text for n in range(1, 11))
        if lang == "fr":
            assert "Présentez" in text and "Écoute tout mon exposé" in text
        else:
            assert "Present the main ideas" in text and "3 follow-up questions" in text
