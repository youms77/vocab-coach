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

from app.db.models import (
    Card,
    Enrichment,
    ErrorCategory,
    ErrorEvent,
    ExerciseTemplate,
    LexicalItem,
    ProductionAttempt,
    ProductionTarget,
    ReviewLog,
)
from app.db.settings_store import get_setting
from app.domain import exercises as ex
from app.domain.durations import DurationClass, DurationEstimates, duration_class
from app.domain.enums import CardDirection, ErrorSource, ItemStatus, ItemType, SrsState
from app.domain.exercise_choice import TemplateRef, choose_exercise
from app.domain.fsrs_engine import default_engine_factory
from app.domain.grading import (
    Confusion,
    ConfusionKind,
    GradeResult,
    Outcome,
    check_production,
    comparable,
    grade_choice,
    grade_typed,
    normalize_answer,
    production_rating,
)
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.normalize import normalize_term
from app.domain.review_steps import (
    build_prompt,
    build_solution,
    option_seed,
    prompt_has_cue,
    sheet_summary,
    shuffled_options,
)
from app.domain.srs import EngineFactory, Rating
from app.domain.study_day import as_utc, study_day_bounds, study_day_of
from app.domain.usage_sheet import UsageSheet, read_sheet
from app.services import error_log
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


class ProductionMismatch(LibraryError):
    """The production sent with a review is not the one checked for this term in this session,
    or another review already used it."""

    code = "production_mismatch"


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


def _confusions(session: Session, ctx: ExerciseContext, answer: str | None) -> dict[str, Confusion]:
    """The sheet's confusables and pitfalls, and the answer itself when it is another term of
    the library ("affect" typed for "effect" is a confusion, not a typo), keyed by their
    comparable form. When a word is several of these, the sheet's entries win (they explain the
    difference): confusable, then pitfall, then library term."""
    term = ctx.item.term
    found: dict[str, Confusion] = {}
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
            found[comparable(answer, term)] = Confusion(ConfusionKind.LIBRARY_TERM, answer.strip())
    if ctx.sheet is not None:
        for pitfall in ctx.sheet.french_speaker_pitfalls:
            found[comparable(pitfall.wrong, term)] = Confusion(
                ConfusionKind.PITFALL, pitfall.wrong, pitfall.explanation
            )
        for confusable in ctx.sheet.confusables:
            found[comparable(confusable.term, term)] = Confusion(
                ConfusionKind.CONFUSABLE, confusable.term, confusable.difference
            )
    return {key: confusion for key, confusion in found.items() if key}


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


def solution_and_summary(ctx: ExerciseContext) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The solution and the sheet summary, to give once the user has made an attempt (D-103)."""
    return _solution(ctx), sheet_summary(ctx.item.term, ctx.sheet)


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
    error_event_id: int | None = None


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
    production_attempt_id: int | None = None,
    engine_factory: EngineFactory = default_engine_factory,
) -> Recorded:
    """Record the user's final rating. The proposed rating is computed again here; for a
    `sentence_production` it comes from the AI check of `production_attempt_id` (D-128)."""
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
    auto_rating = graded.result.proposed_rating
    if production_attempt_id is not None:
        attempt = _checked_production(session, ctx, production_attempt_id, study_session_id)
        auto_rating = production_rating(attempt.ai_feedback, item.id)
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
            auto_rating=auto_rating,
            study_session_id=study_session_id,
            exercise_template_id=ctx.template.id if ctx.template is not None else None,
            production_attempt_id=production_attempt_id,
            engine_factory=engine_factory,
        )
    except ReviewNotAllowed as exc:
        raise ReviewRefused(str(exc)) from exc
    error = _confusion_error(session, ctx, graded, log.id, now, study_session_id)
    return Recorded(
        review_log_id=log.id,
        due_after=log.due_after,
        state_after=SrsState(log.state_after),
        item_status=ItemStatus(item.status),
        item_status_changed=ItemStatus(item.status) != status_before,
        auto_rating=auto_rating,
        error_event_id=error.id if error is not None else None,
    )


def _checked_production(
    session: Session, ctx: ExerciseContext, production_attempt_id: int, study_session_id: int
) -> ProductionAttempt:
    """The production a review rated: it must be the one checked for this term, in this session,
    and not already used by another review. Raises ExerciseMismatch, ProductionMismatch."""
    if ctx.exercise_type != ex.SENTENCE_PRODUCTION:
        raise ExerciseMismatch("`production_attempt_id` only goes with a sentence production.")
    attempt = session.get(ProductionAttempt, production_attempt_id)
    if attempt is None:
        raise ProductionMismatch(f"There is no production {production_attempt_id}.")
    if attempt.study_session_id != study_session_id:
        raise ProductionMismatch("This production was written in another study session.")
    is_target = session.scalar(
        select(
            exists().where(
                ProductionTarget.production_attempt_id == attempt.id,
                ProductionTarget.lexical_item_id == ctx.item.id,
            )
        )
    )
    if not is_target:
        raise ProductionMismatch("This production was not written for this term.")
    already = session.scalar(select(exists().where(ReviewLog.production_attempt_id == attempt.id)))
    if already:
        raise ProductionMismatch("This production was already used by another review.")
    return attempt


# --- Errors from reviews -------------------------------------------------------------------------

MULTI_WORD_TYPES = (ItemType.COLLOCATION, ItemType.PHRASE, ItemType.SPOKEN_FORMULA)


def _one_word_apart(given: str, expected: str) -> bool:
    a, b = normalize_answer(given).split(), normalize_answer(expected).split()
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1


def confusion_category(item_type: ItemType | str, given: str, expected: str) -> str:
    """`lexis.collocation` when a multi-word term was answered with one word changed ("make a
    conclusion" for "draw a conclusion"), else `lexis.wrong_word`."""
    if item_type in MULTI_WORD_TYPES and _one_word_apart(given, expected):
        return "lexis.collocation"
    return "lexis.wrong_word"


def _origin_category(
    session: Session, item: LexicalItem, confusion: Confusion
) -> ErrorCategory | None:
    """A card made from an error (M5.a3): its wrong form is a pitfall of the sheet, and falling
    back into it is the same error again, so it keeps the category of the error the card came
    from (a preposition stays a preposition, not a "wrong word")."""
    if confusion.kind != ConfusionKind.PITFALL or item.origin_error_event_id is None:
        return None
    origin = session.get(ErrorEvent, item.origin_error_event_id)
    if origin is None:
        return None
    category = session.get(ErrorCategory, origin.category_id)
    return category if category is not None and category.status == "active" else None


def _confusion_error(
    session: Session,
    ctx: ExerciseContext,
    graded: Graded,
    review_log_id: int,
    now: datetime,
    study_session_id: int,
) -> ErrorEvent | None:
    """One error event for a typed answer that is `wrong` because of a lexical confusion (SPEC
    module C). Nothing for a typo, an empty answer, any other wrong answer, a choice or a
    self-graded exercise."""
    result = graded.result
    if (
        ctx.exercise_type not in ex.TYPED_TYPES
        or result.outcome != Outcome.WRONG
        or result.confusion is None
        or not graded.answer_text
        or ctx.content is None
    ):
        return None
    given = graded.answer_text.strip()
    expected = str(ctx.content["answer"])
    category = _origin_category(session, ctx.item, result.confusion) or error_log.category_by_code(
        session, confusion_category(ctx.item.item_type, given, expected)
    )
    if category is None:  # the taxonomy was never loaded (`db upgrade` syncs it)
        return None
    if ctx.exercise_type == ex.GAP_FILL:
        original = ex.fill_gap(str(ctx.content["sentence"]), given)
    else:
        cues = [ctx.content.get("cue_fr"), ctx.content.get("cue_definition")]
        original = " / ".join(str(cue) for cue in cues if cue)
    explanation = result.confusion.explanation or (
        f'"{given}" is a different word: here the right term is "{expected}".'
    )
    return error_log.record_error(
        session,
        source=ErrorSource.REVIEW,
        category=category,
        erroneous_text=given,
        correction=expected,
        at=now,
        original_text=original,
        explanation=explanation,
        lexical_item_id=ctx.item.id,
        review_log_id=review_log_id,
        study_session_id=study_session_id,
    )
