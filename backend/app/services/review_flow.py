"""A review from the user's side (module C): the step to show, grading an attempt, recording the
final rating, revealing a self-graded answer.

`grade` and `reveal` write nothing. `record` grades the answer again on the server (the client's
proposal is never trusted), then calls `record_review`. The prompt never contains the solution
(`app/domain/review_steps.py`); the solution is returned only after an attempt.

Discovery's immediate exercises (module B, step 4) are graded through the same code with a term
instead of a card, since the cards do not exist yet.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models import Card, Enrichment, ExerciseTemplate, LexicalItem
from app.db.settings_store import get_setting
from app.domain import exercises as ex
from app.domain.durations import DurationClass, DurationEstimates, duration_class
from app.domain.enums import CardDirection, ItemStatus, SrsState
from app.domain.exercise_choice import TemplateRef, choose_exercise
from app.domain.fsrs_engine import default_engine_factory
from app.domain.grading import (
    GradeResult,
    check_production,
    comparable,
    grade_choice,
    grade_typed,
)
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.normalize import normalize_term
from app.domain.review_steps import (
    build_prompt,
    build_solution,
    confusion_words,
    option_seed,
    prompt_has_cue,
    sheet_summary,
    shuffled_options,
)
from app.domain.srs import EngineFactory, Rating
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.domain.usage_sheet import UsageSheet, read_sheet
from app.services.durations import observed_estimates
from app.services.library import LibraryError, get_item
from app.services.reviews import ReviewNotAllowed, record_review

# A longer answer time is stored as this: a coffee break must not skew the medians of D-028.
MAX_RESPONSE_TIME_MS = 300_000

# Exercises of a discovery (module B, step 4), graded with the term instead of a card.
DISCOVERY_EXERCISE_TYPES = (ex.TYPED_RECALL, ex.GAP_FILL)


class CardNotFound(LibraryError):
    status, code = 404, "card_not_found"


class CardChanged(LibraryError):
    code = "card_changed"


class ReviewRefused(LibraryError):
    code = "review_not_allowed"


class NotDue(LibraryError):
    code = "not_due"


class ExerciseMismatch(LibraryError):
    status, code = 422, "exercise_mismatch"


# --- Context -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExerciseContext:
    item: LexicalItem
    card: Card | None
    direction: CardDirection
    exercise_type: str
    template: ExerciseTemplate | None
    sheet: UsageSheet | None
    seed: str

    @property
    def content(self) -> dict[str, Any] | None:
        return dict(self.template.content) if self.template is not None else None


def current_sheet_of(session: Session, item_id: int) -> UsageSheet | None:
    content = session.scalar(
        select(Enrichment.content).where(
            Enrichment.lexical_item_id == item_id, Enrichment.is_current
        )
    )
    return read_sheet(dict(content)) if content is not None else None


def templates_of(session: Session, item_id: int) -> list[ExerciseTemplate]:
    return list(
        session.scalars(
            select(ExerciseTemplate)
            .where(ExerciseTemplate.lexical_item_id == item_id)
            .order_by(ExerciseTemplate.id)
        )
    )


def clamp_response_time(response_time_ms: int) -> int:
    return max(0, min(response_time_ms, MAX_RESPONSE_TIME_MS))


def _template(
    session: Session, item: LexicalItem, exercise_type: str, template_id: int | None
) -> ExerciseTemplate | None:
    if exercise_type == ex.SELF_ASSESSMENT:
        if template_id is not None:
            raise ExerciseMismatch("A self-assessment has no exercise template.")
        return None
    if exercise_type not in ex.EXERCISE_TYPES:
        raise ExerciseMismatch(f"Unknown exercise type {exercise_type!r}.")
    if template_id is None:
        raise ExerciseMismatch("This exercise type needs `exercise_template_id`.")
    template = session.get(ExerciseTemplate, template_id)
    if (
        template is None
        or template.lexical_item_id != item.id
        or template.exercise_type != exercise_type
    ):
        raise ExerciseMismatch(
            f"Exercise template {template_id} is not a {exercise_type} of this term."
        )
    return template


def card_context(
    session: Session, card_id: int, exercise_type: str, template_id: int | None
) -> ExerciseContext:
    card = session.get(Card, card_id)
    if card is None:
        raise CardNotFound(f"There is no card {card_id}.")
    item = session.get_one(LexicalItem, card.lexical_item_id)
    direction = CardDirection(card.direction)
    template = _template(session, item, exercise_type, template_id)
    if exercise_type != ex.SELF_ASSESSMENT and ex.EXERCISE_TYPES[exercise_type][0] != direction:
        raise ExerciseMismatch(f"A {exercise_type} exercise does not fit a {direction} card.")
    return ExerciseContext(
        item=item,
        card=card,
        direction=direction,
        exercise_type=exercise_type,
        template=template,
        sheet=current_sheet_of(session, item.id),
        seed=option_seed(card.id, card.reps or 0),
    )


def require_discovering(session: Session, item_id: int) -> LexicalItem:
    """The term, which must be `discovering` to be graded without a card."""
    item = get_item(session, item_id)
    if item.status != ItemStatus.DISCOVERING:
        raise ReviewRefused(
            f"Term {item.id} is {item.status}: only a term being discovered is graded without "
            "a card."
        )
    return item


def discovery_seed(item_id: int) -> str:
    return f"item:{item_id}"


def discovery_context(
    session: Session, item_id: int, exercise_type: str, template_id: int | None
) -> ExerciseContext:
    """An immediate exercise of a discovery (typed recall or gap-fill)."""
    item = require_discovering(session, item_id)
    if exercise_type not in DISCOVERY_EXERCISE_TYPES:
        raise ExerciseMismatch(
            f"A discovery exercise is typed recall or a gap-fill, not {exercise_type}."
        )
    return ExerciseContext(
        item=item,
        card=None,
        direction=CardDirection.PRODUCTIVE,
        exercise_type=exercise_type,
        template=_template(session, item, exercise_type, template_id),
        sheet=current_sheet_of(session, item.id),
        seed=discovery_seed(item.id),
    )


# --- Step ----------------------------------------------------------------------------------------


class ReviewStep(BaseModel):
    """A review as shown before the attempt: never the solution (see review_steps.py)."""

    card_id: int
    lexical_item_id: int
    direction: CardDirection
    srs_state: SrsState
    expected_reps: int
    exercise_type: str
    exercise_template_id: int | None
    input: str  # choice | text | none
    self_graded: bool
    term: str | None  # receptive cards only (and not for listening)
    prompt: dict[str, Any]
    warnings: list[str]


def input_kind(exercise_type: str) -> str:
    if exercise_type in ex.CHOICE_TYPES:
        return "choice"
    if exercise_type in ex.TYPED_TYPES or exercise_type == ex.SENTENCE_PRODUCTION:
        return "text"
    return "none"


def review_step(session: Session, card: Card) -> ReviewStep:
    item = session.get_one(LexicalItem, card.lexical_item_id)
    direction = CardDirection(card.direction)
    templates = templates_of(session, item.id)
    choice = choose_exercise(
        direction,
        SrsState(card.srs_state),
        card.stability,
        card.reps or 0,
        [TemplateRef(t.id, t.exercise_type) for t in templates],
    )
    template = next((t for t in templates if t.id == choice.template_id), None)
    sheet = current_sheet_of(session, item.id)
    prompt = build_prompt(
        choice.exercise_type,
        direction,
        dict(template.content) if template is not None else None,
        term=item.term,
        origin_sentence=item.origin_sentence,
        sheet=sheet,
        seed=option_seed(card.id, card.reps or 0),
    )
    show_term = direction == CardDirection.RECEPTIVE and choice.exercise_type != ex.LISTENING
    return ReviewStep(
        card_id=card.id,
        lexical_item_id=item.id,
        direction=direction,
        srs_state=SrsState(card.srs_state),
        expected_reps=card.reps or 0,
        exercise_type=choice.exercise_type,
        exercise_template_id=choice.template_id,
        input=input_kind(choice.exercise_type),
        self_graded=choice.exercise_type in ex.SELF_GRADED_TYPES,
        term=item.term if show_term else None,
        prompt=prompt,
        warnings=[] if prompt_has_cue(prompt) else ["no_cue"],
    )


# --- Grading -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Graded:
    result: GradeResult
    answer_text: str | None
    solution: dict[str, Any]
    sheet_summary: dict[str, Any] | None


def _estimate(estimates: DurationEstimates, direction: CardDirection, exercise_type: str) -> float:
    cls = duration_class(direction, exercise_type)
    if cls == DurationClass.ORAL:
        return estimates.oral
    return estimates.receptive if cls == DurationClass.RECEPTIVE else estimates.productive_typed


def _answer_forms(session: Session, item_id: int) -> list[str]:
    forms: list[str] = []
    for template in templates_of(session, item_id):
        if template.exercise_type == ex.GAP_FILL:
            forms += [template.content.get("answer", ""), *template.content.get("accepted", [])]
    return [form for form in forms if form]


def _confusions(session: Session, ctx: ExerciseContext, answer: str | None) -> list[str]:
    """The sheet's confusables and pitfalls, and the answer itself when it is another term of
    the library ("affect" typed for "effect" is a confusion, not a typo)."""
    term = ctx.item.term
    words = [comparable(word, term) for word in confusion_words(ctx.sheet)]
    if answer and answer.strip():
        other_term = session.scalar(
            select(
                exists().where(
                    LexicalItem.normalized_form == normalize_term(answer),
                    LexicalItem.id != ctx.item.id,
                )
            )
        )
        if other_term:
            words.append(comparable(answer, term))
    return [word for word in words if word]


def grade(
    session: Session,
    ctx: ExerciseContext,
    *,
    answer: str | None,
    choice_index: int | None,
    response_time_ms: int | None,
    now: datetime,
) -> Graded:
    """Grade an attempt. Writes nothing."""
    estimate = _estimate(observed_estimates(session, now), ctx.direction, ctx.exercise_type)
    content = ctx.content
    answer_text = answer
    if ctx.exercise_type in ex.CHOICE_TYPES:
        assert content is not None  # noqa: S101 (checked by _template)
        options, correct = shuffled_options(content, ctx.seed)
        if choice_index is not None and not 0 <= choice_index < len(options):
            raise ExerciseMismatch(f"`choice_index` must be between 0 and {len(options) - 1}.")
        result = grade_choice(
            options=options,
            correct_index=correct,
            chosen_index=choice_index,
            response_time_ms=response_time_ms,
            estimate_seconds=estimate,
        )
        answer_text = options[choice_index] if choice_index is not None else None
    elif ctx.exercise_type in ex.TYPED_TYPES:
        assert content is not None  # noqa: S101
        result = grade_typed(
            exercise_type=ctx.exercise_type,
            term=ctx.item.term,
            answer=content["answer"],
            accepted=list(content.get("accepted", [])),
            given=answer,
            confusions=_confusions(session, ctx, answer),
            response_time_ms=response_time_ms,
            estimate_seconds=estimate,
        )
    elif ctx.exercise_type == ex.SENTENCE_PRODUCTION:
        result = check_production(ctx.item.term, answer, _answer_forms(session, ctx.item.id))
    else:  # spoken answer, self-assessment: nothing typed to grade
        result = GradeResult(outcome=None, proposed_rating=None, expected=None)
    return Graded(
        result=result,
        answer_text=answer_text,
        solution=_solution(ctx),
        sheet_summary=sheet_summary(ctx.item.term, ctx.sheet),
    )


def _solution(ctx: ExerciseContext) -> dict[str, Any]:
    return build_solution(
        ctx.exercise_type,
        ctx.content,
        term=ctx.item.term,
        origin_sentence=ctx.item.origin_sentence,
        sheet=ctx.sheet,
        seed=ctx.seed,
    )


def reveal(ctx: ExerciseContext) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Solution and sheet summary of a self-graded exercise. Writes nothing."""
    if ctx.exercise_type not in ex.SELF_GRADED_TYPES:
        raise ExerciseMismatch(
            f"A {ctx.exercise_type} exercise is graded, not revealed: use the grading route."
        )
    return _solution(ctx), sheet_summary(ctx.item.term, ctx.sheet)


# --- Recording -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Recorded:
    review_log_id: int
    due_after: datetime
    state_after: SrsState
    item_status: ItemStatus
    item_status_changed: bool
    auto_rating: Rating | None


def record(
    session: Session,
    ctx: ExerciseContext,
    *,
    answer: str | None,
    choice_index: int | None,
    response_time_ms: int,
    final_rating: Rating,
    expected_reps: int,
    study_session_id: int,
    now: datetime,
    engine_factory: EngineFactory = default_engine_factory,
) -> Recorded:
    """Record the user's final rating. The proposed rating is computed again here."""
    now = as_utc(now)
    card, item = ctx.card, ctx.item
    assert card is not None  # noqa: S101 (a review is always of a card)
    if (card.reps or 0) != expected_reps:
        raise CardChanged(
            "This card was reviewed meanwhile (another tab, or the answer was sent twice).",
            reps=card.reps or 0,
        )
    if item.status not in REVIEWABLE_STATUSES:
        raise ReviewRefused(f"Term {item.id} is {item.status}: its cards are not reviewed.")
    tz = ZoneInfo(get_setting(session, "timezone"))
    hour = get_setting(session, "day_start_hour")
    _, day_end = study_day_bounds(study_day_of(now, tz, hour), tz, hour)
    if card.due >= day_end:
        raise NotDue(f"Card {card.id} is not due today.", due=card.due.isoformat())

    response_time_ms = clamp_response_time(response_time_ms)
    graded = grade(
        session,
        ctx,
        answer=answer,
        choice_index=choice_index,
        response_time_ms=response_time_ms,
        now=now,
    )
    status_before = ItemStatus(item.status)
    try:
        log = record_review(
            session,
            card,
            final_rating,
            now,
            response_time_ms,
            ctx.exercise_type,
            answer=graded.answer_text,
            auto_rating=graded.result.proposed_rating,
            study_session_id=study_session_id,
            exercise_template_id=ctx.template.id if ctx.template is not None else None,
            engine_factory=engine_factory,
        )
    except ReviewNotAllowed as exc:
        raise ReviewRefused(str(exc)) from exc
    return Recorded(
        review_log_id=log.id,
        due_after=log.due_after,
        state_after=SrsState(log.state_after),
        item_status=ItemStatus(item.status),
        item_status_changed=ItemStatus(item.status) != status_before,
        auto_rating=graded.result.proposed_rating,
    )
