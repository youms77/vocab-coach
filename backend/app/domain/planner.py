"""Today's session planner (docs/SPEC.md module D). Pure: same inputs, same plan; writes nothing.

Blocks, in order: due reviews, new terms, targeted practice, consolidation. The number of new terms
is the minimum of the quota (raised up to 2x quota by deadline decks), what the day's budget leaves
after the other blocks, and what next week's forecast load leaves (see D-028 for the formula).
Queued terms without a usable sheet are left out of new terms (D-105) but still count in deadline
paces.
Warnings carry a stable code and parameters; the frontend turns them into text through i18n.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.domain.deck_queue import Candidate, DeckSnapshot, queue_order, queued_candidates
from app.domain.durations import DurationEstimates
from app.domain.enums import CardDirection, DeckStatus, SrsState
from app.domain.forecast import CardSnapshot, forecast_load
from app.domain.study_day import as_utc, study_day_bounds, study_day_of

# Each new term creates about 2 cards x 4 reviews during its first week.
NEW_ITEM_CARDS = 2
NEW_CARD_REVIEWS_FIRST_WEEK = 4
ANTICIPATION_DAYS = 7
# A deck with a deadline may raise the daily quota up to this factor.
DEADLINE_QUOTA_FACTOR = 2
TARGETED_PRACTICE_WINDOW = timedelta(days=14)
TARGETED_PRACTICE_MIN_ERRORS = 2


class PlanLimit(StrEnum):
    """What limited the number of new terms."""

    QUOTA = "quota"
    BUDGET = "budget"
    ANTICIPATION = "anticipation"
    SUPPLY = "supply"  # fewer terms available than the other limits allow
    NOTHING_TO_LEARN = "nothing_to_learn"


class WarningCode(StrEnum):
    REVIEWS_OVER_BUDGET = "reviews_over_budget"
    DEADLINE_UNREALISTIC = "deadline_unrealistic"
    DEADLINE_PASSED = "deadline_passed"
    DEADLINE_TRIAGE_PENDING = "deadline_triage_pending"
    ITEMS_WITHOUT_SHEET = "items_without_sheet"


class BlockKind(StrEnum):
    REVIEWS = "reviews"
    NEW_ITEMS = "new_items"
    TARGETED_PRACTICE = "targeted_practice"
    CONSOLIDATION = "consolidation"


# --- Inputs -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscoveringItem:
    """A term whose discovery was started but not completed."""

    lexical_item_id: int
    since: datetime


@dataclass(frozen=True)
class ErrorSample:
    category_code: str
    occurred_at: datetime


@dataclass(frozen=True)
class PlanInputs:
    now: datetime
    tz: ZoneInfo
    day_start_hour: int
    budget_minutes: int
    new_items_per_day: int
    durations: DurationEstimates = field(default_factory=DurationEstimates)
    cards: Sequence[CardSnapshot] = ()
    decks: Sequence[DeckSnapshot] = ()
    discovering: Sequence[DiscoveringItem] = ()
    recent_errors: Sequence[ErrorSample] = ()
    pending_consolidation_task_ids: Sequence[int] = ()
    # Queued terms with no usable sheet (D-105): never proposed for discovery.
    items_without_sheet: frozenset[int] = frozenset()


# --- Output -----------------------------------------------------------------------------------


class ReviewEntry(BaseModel):
    kind: Literal["review"] = "review"
    card_id: int
    lexical_item_id: int
    direction: CardDirection
    state: SrsState
    due: datetime
    retrievability: float | None
    estimated_seconds: float
    overflow: bool = False


class NewItemEntry(BaseModel):
    kind: Literal["new_item"] = "new_item"
    lexical_item_id: int
    deck_id: int | None
    resumed: bool = False  # discovery started earlier and not completed
    estimated_seconds: float


class TargetedPracticeEntry(BaseModel):
    kind: Literal["targeted_practice"] = "targeted_practice"
    category_code: str
    error_count: int
    estimated_seconds: float
    overflow: bool = False


class ConsolidationEntry(BaseModel):
    kind: Literal["consolidation"] = "consolidation"
    consolidation_task_id: int
    estimated_seconds: float
    overflow: bool = False


PlanEntry = Annotated[
    ReviewEntry | NewItemEntry | TargetedPracticeEntry | ConsolidationEntry,
    Field(discriminator="kind"),
]


class PlanBlock(BaseModel):
    kind: BlockKind
    estimated_seconds: float
    entries: list[PlanEntry]


class NewItemCaps(BaseModel):
    quota: int
    budget: int
    anticipation: int
    available: int


class DeadlinePace(BaseModel):
    deck_id: int
    deadline: date
    remaining: int
    days_left: int
    required_per_day: int


class PlanWarning(BaseModel):
    code: WarningCode
    params: dict[str, Any] = Field(default_factory=dict)


class SessionPlan(BaseModel):
    study_day: date
    generated_at: datetime
    budget_seconds: float
    blocks: list[PlanBlock]
    total_seconds: float
    new_items_allowed: int
    limit: PlanLimit
    caps: NewItemCaps
    decks_to_activate: list[int]
    deadline_paces: list[DeadlinePace]
    warnings: list[PlanWarning]
    observed_durations: list[str]

    def block(self, kind: BlockKind) -> PlanBlock | None:
        return next((b for b in self.blocks if b.kind == kind), None)


# --- Planning ---------------------------------------------------------------------------------


def _spread(cards: Sequence[CardSnapshot], previous_item: int | None) -> list[CardSnapshot]:
    """Keep the order, but avoid putting the two cards of a term side by side when possible."""
    remaining = list(cards)
    result: list[CardSnapshot] = []
    while remaining:
        index = next((i for i, c in enumerate(remaining) if c.lexical_item_id != previous_item), 0)
        card = remaining.pop(index)
        result.append(card)
        previous_item = card.lexical_item_id
    return result


def order_reviews(due: Sequence[CardSnapshot]) -> list[CardSnapshot]:
    """(Re)learning and new cards by due date, then Review cards by increasing retrievability."""
    learning = sorted(
        (c for c in due if c.state != SrsState.REVIEW), key=lambda c: (c.due, c.card_id)
    )
    review = sorted(
        (c for c in due if c.state == SrsState.REVIEW),
        key=lambda c: (
            c.retrievability if c.retrievability is not None else 0.0,
            c.due,
            c.card_id,
        ),
    )
    first = _spread(learning, None)
    return first + _spread(review, first[-1].lexical_item_id if first else None)


def pick_targeted_category(errors: Sequence[ErrorSample], now: datetime) -> tuple[str, int] | None:
    """Most frequent category of the last 14 days (at least 2 errors); ties: most recent."""
    since = now - TARGETED_PRACTICE_WINDOW
    recent = [e for e in errors if since < e.occurred_at <= now]
    counts = Counter(e.category_code for e in recent)
    latest: dict[str, datetime] = {}
    for e in recent:
        latest[e.category_code] = max(latest.get(e.category_code, e.occurred_at), e.occurred_at)
    eligible = [code for code, n in counts.items() if n >= TARGETED_PRACTICE_MIN_ERRORS]
    if not eligible:
        return None
    code = max(eligible, key=lambda c: (counts[c], latest[c]))
    return code, counts[code]


def _deck_of_discovering(
    item_id: int, ordered: Sequence[DeckSnapshot], all_decks: Sequence[DeckSnapshot]
) -> int | None:
    for deck in [*ordered, *all_decks]:
        if any(ref.lexical_item_id == item_id for ref in deck.items):
            return deck.id
    return None


def plan_session(inputs: PlanInputs) -> SessionPlan:
    now = as_utc(inputs.now)
    tz, hour = inputs.tz, inputs.day_start_hour
    durations = inputs.durations
    today = study_day_of(now, tz, hour)
    _, day_end = study_day_bounds(today, tz, hour)
    budget = float(inputs.budget_minutes * 60)
    quota = inputs.new_items_per_day
    warnings: list[PlanWarning] = []

    # 1. Due reviews: due before the end of the current study day.
    due = [c for c in inputs.cards if c.schedulable and c.due < day_end]
    elapsed = 0.0
    review_entries: list[ReviewEntry] = []
    for card in order_reviews(due):
        seconds = durations.for_due_card(card.direction)
        elapsed += seconds
        review_entries.append(
            ReviewEntry(
                card_id=card.card_id,
                lexical_item_id=card.lexical_item_id,
                direction=card.direction,
                state=card.state,
                due=card.due,
                retrievability=card.retrievability,
                estimated_seconds=seconds,
                overflow=elapsed > budget,
            )
        )
    review_seconds = elapsed
    if review_seconds > budget:
        warnings.append(
            PlanWarning(
                code=WarningCode.REVIEWS_OVER_BUDGET,
                params={
                    "review_seconds": review_seconds,
                    "budget_seconds": budget,
                    "overflow_count": sum(1 for e in review_entries if e.overflow),
                },
            )
        )

    # 3 and 4 are reserved before new terms, which get what is left.
    targeted = pick_targeted_category(inputs.recent_errors, now)
    targeted_entry: TargetedPracticeEntry | None = None
    if targeted is not None:
        elapsed += durations.targeted_practice_block
        targeted_entry = TargetedPracticeEntry(
            category_code=targeted[0],
            error_count=targeted[1],
            estimated_seconds=durations.targeted_practice_block,
            overflow=elapsed > budget,
        )
    consolidation_entry: ConsolidationEntry | None = None
    if inputs.pending_consolidation_task_ids:
        elapsed += durations.consolidation_block
        consolidation_entry = ConsolidationEntry(
            consolidation_task_id=inputs.pending_consolidation_task_ids[0],
            estimated_seconds=durations.consolidation_block,
            overflow=elapsed > budget,
        )
    reserved = elapsed

    # Deadlines: required pace, passed deadlines, terms still in triage.
    ordered = queue_order(inputs.decks, today)
    paces: list[DeadlinePace] = []
    for deck in ordered:
        remaining = deck.remaining()
        if deck.deadline is None or remaining == 0:
            continue
        if deck.has_future_deadline(today):
            days_left = (deck.deadline - today).days
            paces.append(
                DeadlinePace(
                    deck_id=deck.id,
                    deadline=deck.deadline,
                    remaining=remaining,
                    days_left=days_left,
                    required_per_day=math.ceil(remaining / days_left),
                )
            )
            if deck.in_triage():
                warnings.append(
                    PlanWarning(
                        code=WarningCode.DEADLINE_TRIAGE_PENDING,
                        params={"deck_id": deck.id, "count": deck.in_triage()},
                    )
                )
        else:
            warnings.append(
                PlanWarning(
                    code=WarningCode.DEADLINE_PASSED,
                    params={
                        "deck_id": deck.id,
                        "deadline": deck.deadline.isoformat(),
                        "remaining": remaining,
                    },
                )
            )

    # 2. New terms allowed = min(quota cap, budget cap, anticipation cap, available).
    required_total = sum(p.required_per_day for p in paces)
    cap_quota = (
        quota if required_total <= quota else min(required_total, DEADLINE_QUOTA_FACTOR * quota)
    )
    cap_budget = max(0, math.floor((budget - reserved) / durations.discovery))
    week = forecast_load(inputs.cards, today, tz, hour, durations, days=1 + ANTICIPATION_DAYS)[1:]
    week_load = sum(day.seconds for day in week) / ANTICIPATION_DAYS
    new_item_weekly_seconds = NEW_ITEM_CARDS * NEW_CARD_REVIEWS_FIRST_WEEK * durations.average_card
    cap_anticipation = max(
        0, math.floor(ANTICIPATION_DAYS * (budget - week_load) / new_item_weekly_seconds)
    )

    candidates, without_sheet = _candidates(inputs, ordered, paces)
    if without_sheet:
        position = {d.id: i for i, d in enumerate(ordered)}
        warnings.append(
            PlanWarning(
                code=WarningCode.ITEMS_WITHOUT_SHEET,
                params={
                    "count": len(without_sheet),
                    "deck_ids": sorted(
                        set(without_sheet.values()),
                        key=lambda d: (position.get(d, len(position)), d),
                    ),
                },
            )
        )
    allowed = min(cap_quota, cap_budget, cap_anticipation, len(candidates))
    limit = _limit(cap_quota, cap_budget, cap_anticipation, len(candidates))

    achievable = min(DEADLINE_QUOTA_FACTOR * quota, cap_budget, cap_anticipation)
    for pace in paces:
        if pace.required_per_day > achievable:
            finish = (
                (today + timedelta(days=math.ceil(pace.remaining / achievable) - 1)).isoformat()
                if achievable > 0
                else None
            )
            warnings.append(
                PlanWarning(
                    code=WarningCode.DEADLINE_UNREALISTIC,
                    params={
                        "deck_id": pace.deck_id,
                        "deadline": pace.deadline.isoformat(),
                        "remaining": pace.remaining,
                        "required_per_day": pace.required_per_day,
                        "achievable_per_day": achievable,
                        "projected_finish": finish,
                    },
                )
            )

    selected = candidates[:allowed]
    new_entries = [
        NewItemEntry(
            lexical_item_id=item_id,
            deck_id=deck_id,
            resumed=resumed,
            estimated_seconds=durations.discovery,
        )
        for item_id, deck_id, resumed in selected
    ]
    queued_decks = {d.id for d in inputs.decks if d.status == DeckStatus.QUEUED}
    decks_to_activate: list[int] = []
    for _, deck_id, _ in selected:
        if deck_id in queued_decks and deck_id not in decks_to_activate:
            decks_to_activate.append(deck_id)

    blocks: list[PlanBlock] = []
    if review_entries:
        blocks.append(
            PlanBlock(
                kind=BlockKind.REVIEWS,
                estimated_seconds=review_seconds,
                entries=list(review_entries),
            )
        )
    if new_entries:
        blocks.append(
            PlanBlock(
                kind=BlockKind.NEW_ITEMS,
                estimated_seconds=sum(e.estimated_seconds for e in new_entries),
                entries=list(new_entries),
            )
        )
    if targeted_entry is not None:
        blocks.append(
            PlanBlock(
                kind=BlockKind.TARGETED_PRACTICE,
                estimated_seconds=targeted_entry.estimated_seconds,
                entries=[targeted_entry],
            )
        )
    if consolidation_entry is not None:
        blocks.append(
            PlanBlock(
                kind=BlockKind.CONSOLIDATION,
                estimated_seconds=consolidation_entry.estimated_seconds,
                entries=[consolidation_entry],
            )
        )

    return SessionPlan(
        study_day=today,
        generated_at=now,
        budget_seconds=budget,
        blocks=blocks,
        total_seconds=sum(b.estimated_seconds for b in blocks),
        new_items_allowed=allowed,
        limit=limit,
        caps=NewItemCaps(
            quota=cap_quota,
            budget=cap_budget,
            anticipation=cap_anticipation,
            available=len(candidates),
        ),
        decks_to_activate=decks_to_activate,
        deadline_paces=paces,
        warnings=warnings,
        observed_durations=sorted(durations.observed),
    )


def _candidates(
    inputs: PlanInputs, ordered: Sequence[DeckSnapshot], paces: Sequence[DeadlinePace]
) -> tuple[list[tuple[int, int | None, bool]], dict[int, int]]:
    """(item id, deck id, resumed) in proposal order, each term once; and the queued terms left
    out for want of a usable sheet (item id -> the deck that would have supplied it).

    An interrupted discovery stays proposed even without a sheet: the term is already started.
    """
    result: list[tuple[int, int | None, bool]] = []
    seen: set[int] = set()
    per_deck: Counter[int | None] = Counter()
    without_sheet: dict[int, int] = {}

    def usable(candidates: list[Candidate]) -> list[Candidate]:
        kept = []
        for candidate in candidates:
            if candidate.lexical_item_id in inputs.items_without_sheet:
                without_sheet.setdefault(candidate.lexical_item_id, candidate.deck_id)
            else:
                kept.append(candidate)
        return kept

    def add(item_id: int, deck_id: int | None, resumed: bool = False) -> None:
        if item_id not in seen:
            seen.add(item_id)
            per_deck[deck_id] += 1
            result.append((item_id, deck_id, resumed))

    # Interrupted discoveries first.
    for item in sorted(inputs.discovering, key=lambda i: (i.since, i.lexical_item_id)):
        add(
            item.lexical_item_id,
            _deck_of_discovering(item.lexical_item_id, ordered, inputs.decks),
            True,
        )
    # Then the pace each deadline deck needs, earliest deadline first.
    decks_by_id = {d.id: d for d in ordered}
    for pace in paces:
        wanted = pace.required_per_day - per_deck[pace.deck_id]
        for candidate in usable(_fresh(queued_candidates([decks_by_id[pace.deck_id]]), seen))[
            : max(0, wanted)
        ]:
            add(candidate.lexical_item_id, candidate.deck_id)
    # Then active decks in queue order, then queued decks (automatic activation).
    active = [d for d in ordered if d.status == DeckStatus.ACTIVE]
    waiting = [d for d in ordered if d.status == DeckStatus.QUEUED]
    for candidate in usable(queued_candidates(active + waiting)):
        add(candidate.lexical_item_id, candidate.deck_id)
    return result, without_sheet


def _fresh(candidates: list[Candidate], seen: set[int]) -> list[Candidate]:
    return [c for c in candidates if c.lexical_item_id not in seen]


def _limit(cap_quota: int, cap_budget: int, cap_anticipation: int, available: int) -> PlanLimit:
    if available == 0:
        return PlanLimit.NOTHING_TO_LEARN
    smallest = min(cap_quota, cap_budget, cap_anticipation)
    if available < smallest:
        return PlanLimit.SUPPLY
    if cap_budget == smallest:
        return PlanLimit.BUDGET
    if cap_anticipation == smallest:
        return PlanLimit.ANTICIPATION
    return PlanLimit.QUOTA
