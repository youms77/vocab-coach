"""Scenario units in the services (app/services/curriculum_units.py, M8.a2) with the fake
provider: generation (D-038), edits, steps, terms, and the progress derived from linked takes."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind
from app.db.models import CurriculumUnit, EventLog, LexicalItem, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from app.domain.enums import ItemStatus, UnitContentStatus, UnitProgress
from app.domain.events import EventType
from app.services import curriculum, curriculum_units, speaking, speech
from app.services.curriculum_units import (
    ContentEdit,
    InvalidContent,
    InvalidStep,
    NotAScenarioTrack,
    NotAScenarioUnit,
    UnitChanged,
    UnitGenerated,
)
from app.services.library import ItemNotFound
from app.speech.audio_store import AudioStore
from tests.curriculum_unit_support import LINES, broken, unit_output
from tests.speaking_support import clean_output
from tests.speech_support import wav_bytes
from tests.test_speaking_service import given

AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
TRACK = "speaking_scenarios"
UNIT = 1  # job_interview_1
WAV = wav_bytes(1.0)


@pytest.fixture
def factory(engine: Engine) -> Callable[[], Session]:
    with Session(engine) as session:
        sync_taxonomy(session)
        curriculum.start_track(session, TRACK, AT)
        session.commit()
    return lambda: Session(engine, expire_on_commit=False)


@pytest.fixture
def store(tmp_path: Path) -> AudioStore:
    return AudioStore(tmp_path / "data" / "audio")


def gateway_for(engine: Engine, provider: FakeProvider) -> Gateway:
    return Gateway(
        {provider.name: provider},
        session_factory=lambda: Session(engine),
        provider_order=lambda: [provider.name],
        sleep=lambda _: None,
    )


def ok_gateway(engine: Engine, content: dict[str, Any] | None = None) -> Gateway:
    return gateway_for(engine, FakeProvider("fake", [Success(content=content or unit_output())]))


def events(session: Session, *types: EventType) -> list[EventLog]:
    return list(
        session.scalars(
            select(EventLog)
            .where(EventLog.event_type.in_([t.value for t in types]))
            .order_by(EventLog.id)
        )
    )


def generated(engine: Engine, factory: Callable[[], Session]) -> int:
    result = curriculum_units.generate_unit(
        factory, ok_gateway(engine), TRACK, UNIT, clock=lambda: AT
    )
    assert result.status == "ok" and result.unit is not None
    return result.unit.id


def test_generation_stores_the_content_and_records_it(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        unit = session.get_one(CurriculumUnit, unit_id)
        assert unit.code == "job_interview_1" and unit.position == UNIT
        assert unit.content_status is UnitContentStatus.GENERATED
        assert unit.progress is UnitProgress.NOT_STARTED
        assert (unit.provider, unit.model, unit.prompt_version) == (
            "fake",
            unit.model,
            "curriculum_unit.v1",
        )
        content = unit.content or {}
        assert content["format"] == "curriculum-unit-1" and content["revision"] == 1
        assert content["edited"] is False and content["level"]
        assert content["shadowing"] == [0, 2, 4, 6, 8]
        assert content["final_task"]["formula_refs"] == [0, 1, 2]
        assert content["formulas"][0]["register"] == "neutral"
        (event,) = events(session, EventType.CURRICULUM_UNIT_GENERATED)
        assert event.payload["formula_count"] == 9 and "text" not in str(event.payload)


def test_an_ai_failure_writes_nothing_and_can_be_retried(engine, factory) -> None:
    failing = gateway_for(engine, FakeProvider("fake", [Failure(ErrorKind.AUTH)]))
    result = curriculum_units.generate_unit(factory, failing, TRACK, UNIT, clock=lambda: AT)
    assert result.status == "unavailable" and result.unit is None and result.reason
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CurriculumUnit)) == 0
        assert not events(session, EventType.CURRICULUM_UNIT_GENERATED)
    assert generated(engine, factory)


def test_a_broken_answer_is_repaired_once_then_incomplete(engine, factory) -> None:
    bad = broken("unknown_ref")
    provider = FakeProvider("fake", [Success(content=bad), Success(content=bad)])
    result = curriculum_units.generate_unit(
        factory, gateway_for(engine, provider), TRACK, UNIT, clock=lambda: AT
    )
    assert (result.status, result.unit) == ("incomplete", None)
    assert provider.calls == 2
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CurriculumUnit)) == 0

    repaired = FakeProvider("fake", [Success(content=bad), Success(content=unit_output())])
    again = curriculum_units.generate_unit(
        factory, gateway_for(engine, repaired), TRACK, UNIT, clock=lambda: AT
    )
    assert again.status == "ok"


def test_a_second_generation_is_refused(engine, factory) -> None:
    generated(engine, factory)
    provider = FakeProvider("fake", [Success(content=unit_output())])
    with pytest.raises(UnitGenerated):
        curriculum_units.generate_unit(factory, gateway_for(engine, provider), TRACK, UNIT)
    assert provider.calls == 0  # refused before any call


def test_another_generation_during_the_call_wins(engine, factory) -> None:
    real = ok_gateway(engine)

    class Racing:
        def generate_json(self, *args: Any, **kwargs: Any) -> Any:
            generated(engine, factory)  # someone else writes while the AI works
            return real.generate_json(*args, **kwargs)

    with pytest.raises(UnitGenerated):
        curriculum_units.generate_unit(factory, Racing(), TRACK, UNIT)  # type: ignore[arg-type]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CurriculumUnit)) == 1


def test_the_request_is_checked_before_the_call(engine, factory) -> None:
    provider = FakeProvider("fake", [Success(content=unit_output())])
    gateway = gateway_for(engine, provider)
    with pytest.raises(NotAScenarioTrack):
        curriculum_units.generate_unit(factory, gateway, "academic", 1)
    with pytest.raises(curriculum.UnitNotFound):
        curriculum_units.generate_unit(factory, gateway, TRACK, 17)
    with pytest.raises(curriculum.TrackNotFound):
        curriculum_units.generate_unit(factory, gateway, "nope", 1)
    assert provider.calls == 0


def test_the_track_must_be_started(engine, tmp_path) -> None:
    other = gateway_for(engine, FakeProvider("fake", [Success(content=unit_output())]))
    with pytest.raises(curriculum.TrackNotStarted):
        curriculum_units.generate_unit(lambda: Session(engine), other, TRACK, UNIT)


def test_the_unit_is_listed_with_its_content(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        out = curriculum.get_unit(session, unit_id)
        scenario = out.scenario
        assert out.content_status is UnitContentStatus.GENERATED and out.state == "opened"
        assert scenario is not None and scenario.revision == 1
        assert len(scenario.formulas) == 9 and scenario.formulas[0].style == "neutral"
        assert [s.text for s in scenario.shadowing] == [LINES[i][1] for i in (0, 2, 4, 6, 8)]
        assert scenario.next_step == "formulas"
        assert scenario.steps == {
            "formulas": False,
            "dialogue": False,
            "shadowing": False,
            "final_task": False,
        }
        row = curriculum.track_detail(session, TRACK, limit=3).units[0]
        assert (row.unit_id, row.content_status) == (unit_id, UnitContentStatus.GENERATED)


def test_marking_a_step_is_idempotent_and_moves_the_progress(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        first = curriculum_units.mark_step(session, unit_id, "formulas", AT)
        again = curriculum_units.mark_step(session, unit_id, "formulas", AT)
        session.commit()
        assert (first.changed, again.changed) == (True, False)
        assert session.get_one(CurriculumUnit, unit_id).progress is UnitProgress.IN_PROGRESS
        assert len(events(session, EventType.CURRICULUM_UNIT_STEP_COMPLETED)) == 1
        with pytest.raises(InvalidStep):
            curriculum_units.mark_step(session, unit_id, "shadowing", AT)
        with pytest.raises(InvalidStep):
            curriculum_units.mark_step(session, unit_id, "nope", AT)
        with pytest.raises(curriculum.UnitNotFound):
            curriculum_units.mark_step(session, 999, "formulas", AT)


def test_a_word_unit_has_no_steps(engine, factory) -> None:
    with factory() as session:
        curriculum.start_track(session, "academic", AT)
        opened = curriculum.open_unit(session, "academic", 1, AT)
        session.commit()
        with pytest.raises(NotAScenarioUnit):
            curriculum_units.mark_step(session, opened.unit.id, "formulas", AT)
        assert opened.unit.scenario is None


def shadow(factory, gateway, store, unit_id: int, text: str, *, heard: str | None = None):
    return speech.record_shadowing(
        factory,
        gateway,
        store,
        data=WAV,
        content_type="audio/wav",
        target_text=text,
        duration_s=None,
        curriculum_unit_id=unit_id,
        transcription=given(heard if heard is not None else text, 3.0),
        clock=lambda: AT,
    )


def speak(factory, gateway, store, unit_id: int, text: str = "I would like this job."):
    return speaking.record_speaking(
        factory,
        gateway,
        store,
        data=WAV,
        content_type="audio/wav",
        duration_s=None,
        prompt_text="Explain why you suit the job.",
        curriculum_unit_id=unit_id,
        transcription=given(text, 30.0),
        clock=lambda: AT,
    )


def test_a_unit_goes_to_done_through_its_four_steps(engine, factory, store) -> None:
    unit_id = generated(engine, factory)
    quiet = ok_gateway(engine)  # transcription is given: the provider is not called
    with factory() as session:
        curriculum_units.mark_step(session, unit_id, "formulas", AT)
        curriculum_units.mark_step(session, unit_id, "dialogue", AT)
        session.commit()
    lines = [LINES[i][1] for i in (0, 2, 4, 6, 8)]
    for text in lines[:-1]:
        shadow(factory, quiet, store, unit_id, text)
    with factory() as session:
        scenario = curriculum.get_unit(session, unit_id).scenario
        assert scenario is not None and scenario.steps["shadowing"] is False
        assert scenario.next_step == "shadowing"
        assert [s.done for s in scenario.shadowing] == [True, True, True, True, False]
    shadow(factory, quiet, store, unit_id, lines[-1], heard="Something else entirely here.")
    spoken = speak(factory, quiet, store, unit_id)
    with factory() as session:
        scenario = curriculum.get_unit(session, unit_id).scenario
        assert scenario is not None
        assert scenario.steps == {
            "formulas": True,
            "dialogue": True,
            "shadowing": True,  # a take counts whatever it heard (no pronunciation judge)
            "final_task": False,  # spoken but not corrected
        }
        assert scenario.final_task.attempt_ids == [spoken.production_id]
        assert session.get_one(CurriculumUnit, unit_id).progress is UnitProgress.IN_PROGRESS
    corrector = gateway_for(
        engine, FakeProvider("fake", [Success(content=clean_output("I would like this job."))])
    )
    assert (
        speaking.correct_speaking(factory, corrector, spoken.production_id, clock=lambda: AT).status
        == "ok"
    )
    with factory() as session:
        unit = session.get_one(CurriculumUnit, unit_id)
        assert unit.progress is UnitProgress.DONE
        assert len(events(session, EventType.CURRICULUM_UNIT_STEP_COMPLETED)) == 4
        assert len(events(session, EventType.CURRICULUM_UNIT_COMPLETED)) == 1
        assert curriculum.get_unit(session, unit_id).scenario.next_step is None  # type: ignore[union-attr]


def test_a_silent_take_does_not_count_and_a_unit_must_exist(engine, factory, store) -> None:
    unit_id = generated(engine, factory)
    quiet = ok_gateway(engine)
    shadow(factory, quiet, store, unit_id, LINES[0][1], heard="")
    with factory() as session:
        shadows = curriculum.get_unit(session, unit_id).scenario.shadowing  # type: ignore[union-attr]
        assert shadows[0].take_count == 0
    with pytest.raises(curriculum.UnitNotFound):
        shadow(factory, quiet, store, 999, LINES[0][1])
    with factory() as session:
        opened_id = (
            curriculum.start_track(session, "academic", AT)
            and curriculum.open_unit(session, "academic", 1, AT)
        ).unit.id
        session.commit()
    with pytest.raises(NotAScenarioUnit):
        shadow(factory, quiet, store, opened_id, LINES[0][1])
    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(ProductionAttempt)
            .where(ProductionAttempt.curriculum_unit_id.is_not(None))
        )
        assert count == 1


def test_editing_replaces_parts_under_a_revision(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        unit = session.get_one(CurriculumUnit, unit_id)
        formulas, _, _ = curriculum_units._parts(unit.content or {})
        new_dialogue = unit_output()["dialogue"]
        new_dialogue["lines"][0]["text"] = "Thank you for having me, I am glad to be here today."
        edit = ContentEdit.model_validate(
            {"expected_revision": 1, "dialogue": new_dialogue, "shadowing": [0, 2, 4, 6, 9]}
        )
        curriculum_units.edit_content(session, unit_id, edit, AT)
        session.commit()
        unit = session.get_one(CurriculumUnit, unit_id)
        assert unit.content_status is UnitContentStatus.EDITED
        assert (unit.content or {})["revision"] == 2 and (unit.content or {})["edited"] is True
        assert (unit.content or {})["shadowing"] == [0, 2, 4, 6, 9]
        (event,) = events(session, EventType.CURRICULUM_UNIT_EDITED)
        assert event.payload["parts"] == ["dialogue", "shadowing"]
        assert len(formulas) == 9
        stale = ContentEdit.model_validate({"expected_revision": 1, "shadowing": [0, 2, 4, 6, 8]})
        with pytest.raises(UnitChanged) as caught:
            curriculum_units.edit_content(session, unit_id, stale, AT)
        assert caught.value.extra["revision"] == 2


def test_an_edit_that_breaks_the_rules_changes_nothing(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        for change in (
            {"shadowing": [0, 1, 2, 3]},  # fewer than 5 lines
            {"shadowing": [0, 2, 4, 6, 40]},  # not a line
            {"formulas": unit_output()["formulas"][:7]},  # fewer than 8
            {"final_task": {**unit_output()["final_task"], "formula_refs": [0, 1, 40]}},
        ):
            if "final_task" in change:
                change["final_task"] = {**change["final_task"], "minutes": 1}
            with pytest.raises(InvalidContent) as caught:
                curriculum_units.edit_content(
                    session,
                    unit_id,
                    ContentEdit.model_validate({"expected_revision": 1, **change}),
                    AT,
                )
            assert caught.value.extra["problems"]
        assert (session.get_one(CurriculumUnit, unit_id).content or {})["revision"] == 1


def test_removing_a_formula_remaps_the_final_task(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        formulas = unit_output()["formulas"]
        kept = formulas[1:]  # drops "Thank you for having me", the first reference
        # The dialogue line 0 used it: the rest of the formulas still cover half of the dialogue.
        edit = ContentEdit.model_validate({"expected_revision": 1, "formulas": kept})
        with pytest.raises(InvalidContent):
            # f1, f2, f3 -> only two survive: refused.
            curriculum_units.edit_content(session, unit_id, edit, AT)
        edit = ContentEdit.model_validate(
            {"expected_revision": 1, "formulas": [*kept[:3], *kept[3:], formulas[0]]}
        )
        curriculum_units.edit_content(session, unit_id, edit, AT)
        refs = (session.get_one(CurriculumUnit, unit_id).content or {})["final_task"]
        assert refs["formula_refs"] == [8, 0, 1]


def test_terms_enter_triage_once(engine, factory) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        first = curriculum_units.add_terms(session, unit_id, [0, 1, 2], AT)
        session.commit()
        assert (first.imported, first.attached, first.skipped) == (3, 0, 0)
        again = curriculum_units.add_terms(session, unit_id, [1, 2, 3], AT)
        assert (again.imported, again.skipped) == (1, 2)
        nothing = curriculum_units.add_terms(session, unit_id, [0], AT)
        assert (nothing.imported, nothing.skipped) == (0, 1)
        session.commit()
        unit = session.get_one(CurriculumUnit, unit_id)
        deck = curriculum.find_deck(session, TRACK)
        assert deck is not None and unit.deck_id == deck.id and deck.name == "Speaking scenarios"
        items = session.scalars(select(LexicalItem).order_by(LexicalItem.id)).all()
        assert [i.term for i in items] == [
            "Thank you for having me",
            "I am particularly interested in",
            "my greatest strength is",
            "work under pressure",
        ]
        assert {i.status for i in items} == {ItemStatus.TRIAGE}
        assert (
            items[0].item_type.value == "spoken_formula"
            and items[3].item_type.value == "collocation"
        )
        scenario = curriculum.get_unit(session, unit_id)
        assert [t.item_id for t in scenario.terms] == [i.id for i in items]
        assert scenario.scenario.formulas[0].item_id == items[0].id  # type: ignore[union-attr]
        assert scenario.scenario.final_task.target_item_ids == [i.id for i in items[:3]]  # type: ignore[union-attr]
        assert len(events(session, EventType.CURRICULUM_UNIT_TERMS_ADDED)) == 2
        with pytest.raises(InvalidContent):
            curriculum_units.add_terms(session, unit_id, [99], AT)
        assert not events(session, EventType.IMPORT_COMPLETED)


def test_a_take_of_the_final_task_aims_at_the_added_terms(engine, factory, store) -> None:
    unit_id = generated(engine, factory)
    with factory() as session:
        curriculum_units.add_terms(session, unit_id, [0, 1, 2], AT)
        session.commit()
        ids = curriculum_units.target_item_ids(session, unit_id)
        prompt = curriculum_units.final_prompt(session, unit_id)
    assert len(ids) == 3 and prompt.startswith("You are in an interview")
    with pytest.raises(ItemNotFound):
        speaking.record_speaking(
            factory,
            ok_gateway(engine),
            store,
            data=WAV,
            content_type="audio/wav",
            duration_s=None,
            target_item_ids=[4242],
            curriculum_unit_id=unit_id,
            transcription=given("Hello there everyone.", 10.0),
        )
