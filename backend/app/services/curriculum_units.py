"""Speaking scenario units (module H, M8.a2): generation, storage, edits, steps and terms.

Generation (`generate_unit`, D-038): a short read (the track is started, the unit is in the
syllabus and has no content), the AI call (`curriculum_unit`) with no session open, then one short
write that checks again (409 `unit_generated` if another generation won) and creates the
`curriculum_unit` row with its content. An AI failure is a result: nothing is written and it can
be retried. The row exists only once its content does (D-246).

The content is stored whole in `curriculum_unit.content` (`format: "curriculum-unit-1"`, D-247) and
the coarse `progress` column keeps its closed values. A unit has four steps (D-248): `formulas` and
`dialogue` are marked by the learner; `shadowing` (every chosen line has a transcribed take) and
`final_task` (a free-speaking take linked to the unit was corrected) are derived from the
productions linked to the unit (`production_attempt.curriculum_unit_id`), so a take never needs a
second write. `refresh_progress` stores the result and the dates in `content.progress.steps`, and
`progress` follows: `not_started`, `in_progress`, `done`. It runs after a mark, an edit, a stored
transcription and a stored speaking correction linked to a unit.

Edits replace whole parts under an optimistic `revision` (D-250); the formulas enter the library
only when the learner asks (`add_terms`, D-251), through the triage import core.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.schemas.curriculum_unit import CurriculumUnitOutput
from app.ai.tasks import CURRICULUM_UNIT_MAX_OUTPUT_TOKENS
from app.ai.types import AiStatus
from app.db.base import utcnow
from app.db.event_log import record_event
from app.db.models import (
    CurriculumTrack,
    CurriculumUnit,
    Deck,
    DeckItem,
    LexicalItem,
    ProductionAttempt,
)
from app.domain import curriculum_unit as rules
from app.domain.curriculum import ScenarioUnit, TrackKind
from app.domain.enums import (
    DeckKind,
    ItemType,
    Modality,
    ProductionKind,
    UnitContentStatus,
    UnitProgress,
)
from app.domain.events import (
    CurriculumUnitCompleted,
    CurriculumUnitEdited,
    CurriculumUnitGenerated,
    CurriculumUnitStepCompleted,
    CurriculumUnitTermsAdded,
    ItemOrigin,
)
from app.domain.markdown_import import ImportHeader
from app.domain.normalize import normalize_term
from app.domain.study_day import as_utc
from app.services import curriculum, importing
from app.services.curriculum import (
    FormulaOut,
    ScenarioFinalTask,
    ScenarioOut,
    ShadowingLineOut,
    UnitNotFound,
)
from app.services.library import LibraryError, create_deck, create_source

TASK = "curriculum_unit"
SessionFactory = Callable[[], Session]
Step = rules.Step
STEPS = rules.STEPS
MARKED_STEPS: tuple[Step, ...] = ("formulas", "dialogue")  # the learner marks these
DERIVED_STEPS: tuple[Step, ...] = ("shadowing", "final_task")  # complete by themselves
Part = Literal["formulas", "dialogue", "shadowing", "final_task"]


class NotAScenarioTrack(LibraryError):
    status, code = 422, "not_a_scenario_track"


class NotAScenarioUnit(LibraryError):
    status, code = 422, "not_a_scenario_unit"


class UnitGenerated(LibraryError):
    status, code = 409, "unit_generated"


class UnitChanged(LibraryError):
    status, code = 409, "unit_changed"


class InvalidContent(LibraryError):
    status, code = 422, "invalid_content"


class InvalidStep(LibraryError):
    status, code = 422, "invalid_step"


# --- Shapes --------------------------------------------------------------------------------------


class GenerationResult(BaseModel):
    status: Literal["ok", "incomplete", "unavailable"]
    reason: str | None
    detail: str | None
    unit: curriculum.UnitOut | None


class StepResult(BaseModel):
    changed: bool  # false when the step was already complete: nothing was written
    unit: curriculum.UnitOut


class TermsResult(BaseModel):
    imported: int
    attached: int
    skipped: int
    unit: curriculum.UnitOut


class ContentEdit(BaseModel):
    """What an edit may replace; absent parts stay as they are. Positions are 0-based."""

    expected_revision: int
    formulas: list[rules.Formula] | None = None
    dialogue: rules.Dialogue | None = None
    shadowing: list[int] | None = None
    final_task: rules.FinalTask | None = None


# --- Content -------------------------------------------------------------------------------------


def is_scenario(unit: CurriculumUnit) -> bool:
    return bool(unit.content) and (unit.content or {}).get("format") == rules.UNIT_FORMAT


def build_content(
    output: CurriculumUnitOutput,
    *,
    level: str | None,
    provider: str | None,
    model: str | None,
    prompt_version: str | None,
    ai_call_id: int | None,
) -> dict[str, Any]:
    """The stored content of a freshly generated unit (revision 1, nothing done)."""
    return {
        "format": rules.UNIT_FORMAT,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "ai_call_id": ai_call_id,
        "edited": False,
        "revision": 1,
        "level": level,
        "formulas": [f.model_dump(by_alias=True) for f in output.formulas],
        "dialogue": output.dialogue.model_dump(),
        "shadowing": output.stored_shadowing(),
        "final_task": output.stored_final_task().model_dump(),
        "progress": {"steps": {}},
        "item_ids": [],
        "formula_item_ids": {},
    }


def _parts(content: dict[str, Any]) -> tuple[list[rules.Formula], rules.Dialogue, rules.FinalTask]:
    return (
        [rules.Formula.model_validate(f) for f in content["formulas"]],
        rules.Dialogue.model_validate(content["dialogue"]),
        rules.FinalTask.model_validate(content["final_task"]),
    )


def track_code_of(session: Session, unit: CurriculumUnit) -> str:
    return _track_of(session, unit).code


def _track_of(session: Session, unit: CurriculumUnit) -> CurriculumTrack:
    track = session.get(CurriculumTrack, unit.track_id)
    assert track is not None  # noqa: S101 (foreign key)
    return track


# --- Generation ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Prepared:
    track_code: str
    scenario: ScenarioUnit
    number: int
    inputs: dict[str, str]


def _scenario_of(code: str, number: int) -> tuple[ScenarioUnit, curriculum.SyllabusTrack]:
    track = curriculum.load_syllabus().track(code)
    if track is None:
        raise curriculum.TrackNotFound(f"There is no track '{code}'.", track=code)
    if track.kind != TrackKind.SCENARIOS:
        raise NotAScenarioTrack(
            f"Track '{code}' has no generated units (its units are word lists).", track=code
        )
    if not 1 <= number <= len(track.units):
        raise UnitNotFound(f"Track '{code}' has no unit {number}.", track=code, number=number)
    return track.units[number - 1], track


def _existing(session: Session, track_id: int, scenario: ScenarioUnit) -> CurriculumUnit | None:
    return session.scalars(
        select(CurriculumUnit).where(
            CurriculumUnit.track_id == track_id, CurriculumUnit.code == scenario.code
        )
    ).first()


def _prepare(session: Session, code: str, number: int) -> _Prepared:
    scenario, _ = _scenario_of(code, number)
    row = curriculum._track_row(session, code)
    if row is None:
        raise curriculum.TrackNotStarted(f"Start the track '{code}' first.", track=code)
    existing = _existing(session, row.id, scenario)
    if existing is not None and existing.content_status != UnitContentStatus.PENDING:
        raise UnitGenerated(
            f"Unit {number} of '{code}' already has its content.", track=code, number=number
        )
    return _Prepared(
        track_code=code,
        scenario=scenario,
        number=number,
        inputs={
            "title": scenario.title.en,
            "level": scenario.level,
            "goals": "\n".join(scenario.goals),
            "situations": "\n".join(scenario.situations),
        },
    )


def store_generated(
    session: Session,
    track: CurriculumTrack,
    scenario: ScenarioUnit,
    number: int,
    content: dict[str, Any],
    *,
    at: datetime,
) -> CurriculumUnit:
    """Create the row of a unit with its content, in the caller's transaction (no commit), and
    record `curriculum.unit_generated`. The AI path and the demo come through here."""
    at = as_utc(at)
    unit = CurriculumUnit(
        track_id=track.id,
        code=scenario.code,
        title=scenario.title.en,
        position=number,
        content=content,
        content_status=UnitContentStatus.GENERATED,
        provider=content.get("provider"),
        model=content.get("model"),
        prompt_version=content.get("prompt_version"),
        progress=UnitProgress.NOT_STARTED,
        created_at=at,
        updated_at=at,
    )
    session.add(unit)
    session.flush()
    record_event(
        session,
        CurriculumUnitGenerated(
            track_code=track.code,
            unit_code=unit.code,
            unit_id=unit.id,
            provider=unit.provider,
            model=unit.model,
            prompt_version=unit.prompt_version,
            ai_call_id=content.get("ai_call_id"),
            formula_count=len(content["formulas"]),
        ),
        occurred_at=at,
    )
    return unit


def generate_unit(
    session_factory: SessionFactory,
    gateway: Gateway,
    code: str,
    number: int,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> GenerationResult:
    """Write unit `number` of a scenario track with the AI (see the module docstring). Raises
    TrackNotFound, NotAScenarioTrack, UnitNotFound, TrackNotStarted, UnitGenerated. An AI failure
    is a result (`incomplete` or `unavailable`): nothing is written."""
    with session_factory() as session:
        prepared = _prepare(session, code, number)
        session.rollback()  # nothing stays open during the AI call
    result = gateway.generate_json(
        TASK,
        prepared.inputs,
        CurriculumUnitOutput,
        max_output_tokens=CURRICULUM_UNIT_MAX_OUTPUT_TOKENS,
    )
    if result.status is not AiStatus.OK or result.data is None:
        status: Literal["incomplete", "unavailable"] = (
            "incomplete" if result.status is AiStatus.INCOMPLETE else "unavailable"
        )
        reason = str(result.reason) if result.reason is not None else None
        return GenerationResult(status=status, reason=reason, detail=result.detail, unit=None)
    content = build_content(
        result.data,
        level=prepared.scenario.level,
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        ai_call_id=result.call_id,
    )
    with session_factory() as session:
        _prepare(session, code, number)  # again: another generation may have written meanwhile
        track = curriculum._track_row(session, code)
        assert track is not None  # noqa: S101 (checked by _prepare)
        unit = store_generated(session, track, prepared.scenario, number, content, at=clock())
        out = curriculum._unit_out(session, unit, code)
        session.commit()
    return GenerationResult(status="ok", reason=None, detail=None, unit=out)


# --- Reading -------------------------------------------------------------------------------------


def _text_key(text: str) -> str:
    return " ".join(text.split())


def _takes(session: Session, unit_id: int) -> list[ProductionAttempt]:
    return list(
        session.scalars(
            select(ProductionAttempt)
            .where(ProductionAttempt.curriculum_unit_id == unit_id)
            .order_by(ProductionAttempt.id)
        )
    )


def _derived(content: dict[str, Any], takes: list[ProductionAttempt]) -> dict[str, Any]:
    """Takes per shadowing line, the free-speaking takes and whether each derived step holds."""
    lines = rules.shadowing_lines(content)
    counts = dict.fromkeys(range(len(lines)), 0)
    wanted = {_text_key(text): i for i, text in enumerate(lines)}
    spoken: list[ProductionAttempt] = []
    for take in takes:
        if take.kind is ProductionKind.SHADOWING and take.text.strip():
            position = wanted.get(_text_key(take.prompt_text or ""))
            if position is not None:
                counts[position] += 1
        elif take.kind is ProductionKind.SPEAKING and take.modality is Modality.ORAL:
            spoken.append(take)
    return {
        "counts": counts,
        "spoken": spoken,
        "shadowing": bool(lines) and all(counts[i] > 0 for i in counts),
        "final_task": any(t.ai_feedback is not None for t in spoken),
    }


def _stored_steps(content: dict[str, Any]) -> dict[str, Any]:
    return dict((content.get("progress") or {}).get("steps") or {})


def _step_flags(content: dict[str, Any], derived: dict[str, Any]) -> dict[Step, bool]:
    stored = _stored_steps(content)
    return {
        "formulas": bool(stored.get("formulas", {}).get("done")),
        "dialogue": bool(stored.get("dialogue", {}).get("done")),
        "shadowing": derived["shadowing"],
        "final_task": derived["final_task"],
    }


def _next_step(flags: dict[Step, bool]) -> Step | None:
    return next((step for step in STEPS if not flags[step]), None)


def _formula_item_ids(content: dict[str, Any]) -> dict[int, int]:
    return {int(k): int(v) for k, v in (content.get("formula_item_ids") or {}).items()}


def scenario_out(session: Session, unit: CurriculumUnit) -> ScenarioOut:
    content: dict[str, Any] = unit.content or {}
    formulas, _, final_task = _parts(content)
    derived = _derived(content, _takes(session, unit.id))
    flags = _step_flags(content, derived)
    items = _formula_item_ids(content)
    lines = rules.shadowing_lines(content)
    return ScenarioOut(
        revision=int(content.get("revision", 1)),
        edited=bool(content.get("edited")),
        format=str(content["format"]),
        provider=unit.provider,
        model=unit.model,
        prompt_version=unit.prompt_version,
        level=content.get("level"),
        formulas=[
            FormulaOut(
                index=i,
                text=f.text,
                item_type=f.item_type,
                function_en=f.function_en,
                function_fr=f.function_fr,
                register=f.style,
                item_id=items.get(i),
            )
            for i, f in enumerate(formulas)
        ],
        dialogue=content["dialogue"],
        shadowing=[
            ShadowingLineOut(
                line_index=index,
                text=lines[position],
                take_count=derived["counts"][position],
                done=derived["counts"][position] > 0,
            )
            for position, index in enumerate(content["shadowing"])
            if position < len(lines)
        ],
        final_task=ScenarioFinalTask(
            prompt_en=final_task.prompt_en,
            prompt_fr=final_task.prompt_fr,
            minutes=final_task.minutes,
            formula_refs=final_task.formula_refs,
            target_item_ids=[items[i] for i in final_task.formula_refs if i in items],
            attempt_ids=[t.id for t in derived["spoken"]],
            corrected=derived["final_task"],
        ),
        steps=flags,
        next_step=_next_step(flags),
    )


def target_item_ids(session: Session, unit_id: int) -> list[int]:
    """The library terms the final speaking task asks for (those formulas already added)."""
    unit = get_scenario(session, unit_id)
    _, _, final_task = _parts(unit.content or {})
    items = _formula_item_ids(unit.content or {})
    return [items[i] for i in final_task.formula_refs if i in items]


def final_prompt(session: Session, unit_id: int) -> str:
    """The English prompt of the final task: the topic of the free-speaking take."""
    unit = get_scenario(session, unit_id)
    return _parts(unit.content or {})[2].prompt_en


def get_scenario(session: Session, unit_id: int) -> CurriculumUnit:
    """The unit, which must be a generated scenario unit. Raises UnitNotFound, NotAScenarioUnit."""
    unit = session.get(CurriculumUnit, unit_id)
    if unit is None:
        raise UnitNotFound(f"There is no unit {unit_id}.", unit_id=unit_id)
    if not is_scenario(unit):
        raise NotAScenarioUnit("This unit has no scenario content.", unit_id=unit_id)
    return unit


# --- Progress ------------------------------------------------------------------------------------


def _step_event(unit: CurriculumUnit, track_code: str, step: Step) -> CurriculumUnitStepCompleted:
    return CurriculumUnitStepCompleted(
        track_code=track_code, unit_code=unit.code, unit_id=unit.id, step=step
    )


def refresh_progress(session: Session, unit: CurriculumUnit, at: datetime) -> None:
    """Store which derived steps are complete and move `progress` accordingly, in the caller's
    transaction (no commit). Writes an event the first time a step (or the unit) becomes complete
    and nothing when nothing changed."""
    at = as_utc(at)
    content = dict(unit.content or {})
    flags = _step_flags(content, _derived(content, _takes(session, unit.id)))
    stored = _stored_steps(content)
    track_code = _track_of(session, unit).code
    changed = False
    for step in DERIVED_STEPS:
        was = bool(stored.get(step, {}).get("done"))
        if flags[step] and not was:
            stored[step] = {"done": True, "at": at.isoformat()}
            record_event(session, _step_event(unit, track_code, step), occurred_at=at)
            changed = True
        elif was and not flags[step]:
            stored[step] = {"done": False, "at": None}  # lost by an edit
            changed = True
    if changed:
        content["progress"] = {"steps": stored}
        unit.content = content  # a new dict: nested changes are not tracked (D-020)
    if all(flags.values()):
        progress = UnitProgress.DONE
    elif any(flags.values()):
        progress = UnitProgress.IN_PROGRESS
    else:
        progress = UnitProgress.NOT_STARTED
    if progress != unit.progress:
        if progress is UnitProgress.DONE:
            event = CurriculumUnitCompleted(
                track_code=track_code, unit_code=unit.code, unit_id=unit.id
            )
            record_event(session, event, occurred_at=at)
        unit.progress = progress
        changed = True
    if changed:
        unit.updated_at = at
        session.flush()


def refresh_for_attempt(session: Session, attempt: ProductionAttempt, at: datetime) -> None:
    """Called when a take linked to a unit gets its transcription or its correction."""
    if attempt.curriculum_unit_id is None:
        return
    unit = session.get(CurriculumUnit, attempt.curriculum_unit_id)
    if unit is not None and is_scenario(unit):
        refresh_progress(session, unit, at)


def mark_step(session: Session, unit_id: int, step: str, at: datetime) -> StepResult:
    """The learner marks `formulas` or `dialogue` as done; again changes nothing. Raises
    UnitNotFound, NotAScenarioUnit, InvalidStep (`shadowing` and `final_task` are never marked)."""
    unit = get_scenario(session, unit_id)
    if step not in MARKED_STEPS:
        raise InvalidStep(
            f"The step '{step}' is complete by itself; only {', '.join(MARKED_STEPS)} are marked.",
            step=step,
        )
    at = as_utc(at)
    track_code = _track_of(session, unit).code
    content = dict(unit.content or {})
    stored = _stored_steps(content)
    changed = not stored.get(step, {}).get("done")
    if changed:
        stored[step] = {"done": True, "at": at.isoformat()}
        content["progress"] = {"steps": stored}
        unit.content = content
        record_event(session, _step_event(unit, track_code, step), occurred_at=at)
        refresh_progress(session, unit, at)
    return StepResult(changed=changed, unit=curriculum._unit_out(session, unit, track_code))


# --- Edits ---------------------------------------------------------------------------------------


def _remap_refs(old: list[rules.Formula], new: list[rules.Formula], refs: list[int]) -> list[int]:
    """The formulas of `refs` that survive an edit of the formulas, found again by their text."""
    position = {normalize_term(f.text): i for i, f in enumerate(new)}
    kept = [position.get(normalize_term(old[i].text)) for i in refs if 0 <= i < len(old)]
    return [i for i in kept if i is not None]


def edit_content(session: Session, unit_id: int, edit: ContentEdit, at: datetime) -> CurriculumUnit:
    """Replace whole parts of a unit's content (see the module docstring), in the caller's
    transaction (no commit). Raises UnitNotFound, NotAScenarioUnit, UnitChanged, InvalidContent."""
    unit = get_scenario(session, unit_id)
    at = as_utc(at)
    content = dict(unit.content or {})
    revision = int(content.get("revision", 1))
    if edit.expected_revision != revision:
        raise UnitChanged(
            "The unit changed since you read it: read it again.",
            revision=revision,
            expected=edit.expected_revision,
        )
    if not any((edit.formulas, edit.dialogue, edit.shadowing, edit.final_task)):
        raise InvalidContent("Give at least one part to replace.", problems=["no part given"])
    old_formulas, _, old_final = _parts(content)
    formulas = edit.formulas if edit.formulas is not None else old_formulas
    dialogue = edit.dialogue if edit.dialogue is not None else _parts(content)[1]
    final_task = edit.final_task if edit.final_task is not None else old_final
    shadowing = edit.shadowing if edit.shadowing is not None else list(content["shadowing"])
    problems: list[str] = []
    if edit.formulas is not None and edit.final_task is None:
        refs = _remap_refs(old_formulas, formulas, old_final.formula_refs)
        if len(refs) < rules.FINAL_REFS_MIN:
            problems.append("final_task.formula_refs: fewer than 3 formulas of the task remain")
        else:
            final_task = final_task.model_copy(update={"formula_refs": refs})
    if not rules.FORMULAS_MIN <= len(formulas) <= rules.FORMULAS_MAX:
        problems.append(f"formulas: {rules.FORMULAS_MIN} to {rules.FORMULAS_MAX} are needed")
    if not rules.LINES_MIN <= len(dialogue.lines) <= rules.LINES_MAX:
        problems.append(f"dialogue.lines: {rules.LINES_MIN} to {rules.LINES_MAX} are needed")
    if not rules.SHADOWING_MIN <= len(shadowing) <= rules.SHADOWING_MAX:
        problems.append(
            f"shadowing: {rules.SHADOWING_MIN} to {rules.SHADOWING_MAX} lines are needed"
        )
    if not problems:
        problems = rules.problems(formulas, dialogue, shadowing, final_task)
    if problems:
        raise InvalidContent("The content breaks the rules of a unit.", problems=problems)

    parts: list[Part] = []
    for name in ("formulas", "dialogue", "shadowing", "final_task"):
        if getattr(edit, name) is not None:
            parts.append(name)
    content["formulas"] = [f.model_dump(by_alias=True) for f in formulas]
    content["dialogue"] = dialogue.model_dump()
    content["shadowing"] = shadowing
    content["final_task"] = final_task.model_dump()
    if edit.formulas is not None:  # the library terms follow their formulas
        position = {normalize_term(f.text): i for i, f in enumerate(formulas)}
        content["formula_item_ids"] = {
            str(position[normalize_term(old_formulas[i].text)]): item
            for i, item in _formula_item_ids(content).items()
            if 0 <= i < len(old_formulas) and normalize_term(old_formulas[i].text) in position
        }
    content["revision"] = revision + 1
    content["edited"] = True
    unit.content = content
    unit.content_status = UnitContentStatus.EDITED
    unit.updated_at = at
    record_event(
        session,
        CurriculumUnitEdited(
            track_code=_track_of(session, unit).code,
            unit_code=unit.code,
            unit_id=unit.id,
            revision=revision + 1,
            parts=parts,
        ),
        occurred_at=at,
    )
    session.flush()
    refresh_progress(session, unit, at)  # a new line or prompt may undo a derived step
    return unit


# --- Terms ---------------------------------------------------------------------------------------


def _deck_for(session: Session, track: CurriculumTrack, at: datetime) -> Deck:
    deck = curriculum.find_deck(session, track.code)
    if deck is not None:
        return deck
    source = create_source(session, title=track.title, at=at)
    source.reference = curriculum._reference(track.code)
    return create_deck(
        session,
        name=track.title,
        at=at,
        description=track.description,
        source_id=source.id,
        kind=DeckKind.CURRICULUM,
    )


def add_terms(
    session: Session, unit_id: int, indices: list[int] | None, at: datetime
) -> TermsResult:
    """Put formulas of a unit (all by default) into intake triage, in the track's `curriculum`
    deck (made when missing). A formula already added is skipped, so calling it again writes
    nothing. Raises UnitNotFound, NotAScenarioUnit, InvalidContent (an index out of range)."""
    unit = get_scenario(session, unit_id)
    at = as_utc(at)
    content = dict(unit.content or {})
    formulas, _, _ = _parts(content)
    chosen = list(range(len(formulas))) if indices is None else list(dict.fromkeys(indices))
    bad = [i for i in chosen if not 0 <= i < len(formulas)]
    if bad:
        raise InvalidContent("Some formulas do not exist.", problems=[f"indices: {bad}"])
    mapping = _formula_item_ids(content)
    todo = [i for i in chosen if i not in mapping]
    track = _track_of(session, unit)
    imported = attached = 0
    skipped = len(chosen) - len(todo)
    if todo:
        deck = _deck_for(session, track, at)
        summary = importing.commit(
            session,
            header=ImportHeader(),
            rows=[
                importing.CommitRow(
                    term=formulas[i].text,
                    item_type=ItemType(formulas[i].item_type),
                    confirmed=True,
                )
                for i in todo
            ],
            target=importing.ImportTarget(deck_id=deck.id),
            intake="triage",
            at=at,
            origin=ItemOrigin.CURRICULUM,
            record_completed=False,
        )
        imported, attached, skipped = summary.imported, summary.attached, skipped + summary.skipped
        by_form = {
            normalized: item_id
            for item_id, normalized in session.execute(
                select(LexicalItem.id, LexicalItem.normalized_form)
                .join(DeckItem, DeckItem.lexical_item_id == LexicalItem.id)
                .where(DeckItem.deck_id == deck.id)
            )
        }
        for i in todo:
            item_id = by_form.get(normalize_term(formulas[i].text))
            if item_id is not None:
                mapping[i] = item_id
        content["formula_item_ids"] = {str(i): item for i, item in sorted(mapping.items())}
        content["item_ids"] = sorted(set(mapping.values()))
        unit.content = content
        unit.deck_id = deck.id
        unit.updated_at = at
        record_event(
            session,
            CurriculumUnitTermsAdded(
                track_code=track.code,
                unit_code=unit.code,
                unit_id=unit.id,
                deck_id=deck.id,
                imported=imported,
                attached=attached,
                skipped=summary.skipped,
            ),
            occurred_at=at,
        )
        session.flush()
    return TermsResult(
        imported=imported,
        attached=attached,
        skipped=skipped,
        unit=curriculum._unit_out(session, unit, track.code),
    )
