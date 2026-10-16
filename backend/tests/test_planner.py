"""Session planner (planner criteria). Pure tests: inputs are built by hand."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.deck_queue import DeckItemRef, DeckSnapshot
from app.domain.durations import DurationEstimates
from app.domain.enums import CardDirection, DeckStatus, ItemStatus, SrsState
from app.domain.forecast import CardSnapshot
from app.domain.planner import (
    BlockKind,
    DiscoveringItem,
    ErrorSample,
    NewItemEntry,
    PlanInputs,
    PlanLimit,
    ReviewEntry,
    SessionPlan,
    WarningCode,
    plan_session,
)

DOUALA = ZoneInfo("Africa/Douala")
NOW = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)  # 09:00 in Douala, study day 2026-11-01
TODAY = date(2026, 11, 1)
BASE = PlanInputs(now=NOW, tz=DOUALA, day_start_hour=4, budget_minutes=45, new_items_per_day=12)

_next_id = iter(range(1000, 10**6))


def due_cards(
    count: int,
    due: datetime = NOW,
    direction: CardDirection = CardDirection.RECEPTIVE,
    state: SrsState = SrsState.REVIEW,
) -> list[CardSnapshot]:
    result = []
    for _ in range(count):
        card_id = next(_next_id)
        result.append(
            CardSnapshot(card_id, card_id, direction, state, due, ItemStatus.LEARNING, False, 0.8)
        )
    return result


def deck(
    deck_id: int,
    queued: int,
    status: DeckStatus = DeckStatus.ACTIVE,
    deadline: date | None = None,
    position: int | None = None,
    first_item: int | None = None,
    extra: tuple[DeckItemRef, ...] = (),
) -> DeckSnapshot:
    start = first_item if first_item is not None else deck_id * 100
    refs = tuple(DeckItemRef(start + i, ItemStatus.QUEUED, i) for i in range(queued))
    return DeckSnapshot(deck_id, status, deadline, position, refs + extra)


def plan(**changes: object) -> SessionPlan:
    return plan_session(replace(BASE, **changes))  # type: ignore[arg-type]


def new_items(result: SessionPlan) -> list[NewItemEntry]:
    block = result.block(BlockKind.NEW_ITEMS)
    return [e for e in block.entries if isinstance(e, NewItemEntry)] if block else []


def reviews(result: SessionPlan) -> list[ReviewEntry]:
    block = result.block(BlockKind.REVIEWS)
    return [e for e in block.entries if isinstance(e, ReviewEntry)] if block else []


def codes(result: SessionPlan) -> list[WarningCode]:
    return [w.code for w in result.warnings]


def test_planner_empty_plan() -> None:
    result = plan()
    assert result.blocks == []
    assert result.budget_seconds == 45 * 60
    assert result.new_items_allowed == 0
    assert result.limit == PlanLimit.NOTHING_TO_LEARN
    assert result.total_seconds == 0
    json.loads(result.model_dump_json())  # serialisable


def test_planner_reviews_come_before_new_terms() -> None:
    result = plan(cards=due_cards(3), decks=[deck(1, queued=5)])
    assert [b.kind for b in result.blocks] == [BlockKind.REVIEWS, BlockKind.NEW_ITEMS]
    assert len(reviews(result)) == 3
    assert len(new_items(result)) == 5
    assert result.limit == PlanLimit.SUPPLY


def snap(
    card_id: int,
    state: SrsState,
    due: datetime,
    retrievability: float | None = None,
    item_id: int | None = None,
) -> CardSnapshot:
    return CardSnapshot(
        card_id,
        item_id if item_id is not None else card_id,
        CardDirection.RECEPTIVE,
        state,
        due,
        ItemStatus.LEARNING,
        False,
        retrievability,
    )


def test_planner_review_order_learning_by_due_then_review_by_retrievability() -> None:
    learning_late = snap(1, SrsState.LEARNING, NOW + timedelta(minutes=10))
    new_card = snap(2, SrsState.NEW, NOW - timedelta(hours=1))
    weak = snap(3, SrsState.REVIEW, NOW - timedelta(days=3), 0.70)
    strong = snap(4, SrsState.REVIEW, NOW - timedelta(days=9), 0.85)
    tomorrow = snap(5, SrsState.REVIEW, NOW + timedelta(days=1), 0.95)
    result = plan(cards=[strong, learning_late, tomorrow, weak, new_card])
    assert [e.card_id for e in reviews(result)] == [2, 1, 3, 4]


def test_planner_two_cards_of_a_term_are_not_side_by_side() -> None:
    cards = [
        snap(1, SrsState.REVIEW, NOW, 0.70, item_id=7),
        snap(2, SrsState.REVIEW, NOW, 0.71, item_id=7),
        snap(3, SrsState.REVIEW, NOW, 0.90, item_id=8),
    ]
    assert [e.card_id for e in reviews(plan(cards=cards))] == [1, 3, 2]


def test_planner_card_due_later_today_is_planned_but_not_tomorrow() -> None:
    tonight = datetime(2026, 11, 2, 2, 30, tzinfo=DOUALA)  # still study day 2026-11-01
    tomorrow = datetime(2026, 11, 2, 4, 30, tzinfo=DOUALA)
    result = plan(cards=due_cards(1, tonight) + due_cards(1, tomorrow))
    assert len(reviews(result)) == 1


def test_planner_quota_is_respected() -> None:
    result = plan(decks=[deck(1, queued=40)])
    assert result.new_items_allowed == 12
    assert len(new_items(result)) == 12
    assert result.limit == PlanLimit.QUOTA


def test_planner_budget_reduces_new_terms() -> None:
    # 100 receptive cards x 15 s = 1500 s; 1200 s left / 150 s per discovery = 8 new terms.
    result = plan(cards=due_cards(100), decks=[deck(1, queued=40)])
    assert result.caps.budget == 8
    assert result.new_items_allowed == 8
    assert result.limit == PlanLimit.BUDGET


def test_planner_reviews_over_budget_overflow_and_no_new_terms() -> None:
    # 200 x 15 s = 3000 s > 2700 s: the first 180 cards fit, the last 20 overflow.
    result = plan(cards=due_cards(200), decks=[deck(1, queued=40)])
    entries = reviews(result)
    assert len(entries) == 200
    assert [e.overflow for e in entries] == [False] * 180 + [True] * 20
    assert result.new_items_allowed == 0
    assert result.block(BlockKind.NEW_ITEMS) is None
    assert result.limit == PlanLimit.BUDGET
    [warning] = result.warnings
    assert warning.code == WarningCode.REVIEWS_OVER_BUDGET
    assert warning.params == {
        "review_seconds": 3000.0,
        "budget_seconds": 2700.0,
        "overflow_count": 20,
    }


def test_planner_seven_day_anticipation_reduces_new_terms() -> None:
    # 170 receptive cards due on each of the next 7 days: 2550 s/day forecast.
    # cap = floor(7 x (2700 - 2550) / (2 x 4 x 20 s)) = floor(1050 / 160) = 6.
    future = [card for day in range(1, 8) for card in due_cards(170, NOW + timedelta(days=day))]
    result = plan(cards=future, decks=[deck(1, queued=40)])
    assert result.caps.anticipation == 6
    assert result.new_items_allowed == 6
    assert result.limit == PlanLimit.ANTICIPATION
    assert reviews(result) == []


def test_planner_deadline_pace_thirty_terms_ten_days_is_three_per_day() -> None:
    talk = deck(1, queued=30, deadline=TODAY + timedelta(days=10))
    result = plan(decks=[talk], new_items_per_day=2)
    [pace] = result.deadline_paces
    assert (pace.remaining, pace.days_left, pace.required_per_day) == (30, 10, 3)
    # The deadline raises the quota from 2 to the 3 needed (at most 2 x quota).
    assert result.caps.quota == 3
    assert result.new_items_allowed == 3
    assert WarningCode.DEADLINE_UNREALISTIC not in codes(result)


def test_planner_unrealistic_deadline_gives_achievable_pace_and_finish_date() -> None:
    talk = deck(1, queued=60, deadline=TODAY + timedelta(days=10))
    result = plan(decks=[talk], new_items_per_day=2)
    assert result.caps.quota == 4  # capped at 2 x quota
    [warning] = [w for w in result.warnings if w.code == WarningCode.DEADLINE_UNREALISTIC]
    assert warning.params == {
        "deck_id": 1,
        "deadline": "2026-11-11",
        "remaining": 60,
        "required_per_day": 6,
        "achievable_per_day": 4,
        "projected_finish": "2026-11-15",  # 15 days at 4 per day, today included
    }


def test_planner_deadline_deck_comes_before_queue_position() -> None:
    first_in_queue = deck(1, queued=10, position=0)
    talk = deck(2, queued=10, position=5, deadline=TODAY + timedelta(days=20))
    result = plan(decks=[first_in_queue, talk], new_items_per_day=4)
    assert [e.deck_id for e in new_items(result)] == [2, 2, 2, 2]


def test_planner_past_deadline_warns_and_keeps_normal_priority() -> None:
    late = deck(1, queued=5, position=1, deadline=TODAY - timedelta(days=1))
    first = deck(2, queued=2, position=0)
    result = plan(decks=[late, first])
    assert [e.deck_id for e in new_items(result)] == [2, 2, 1, 1, 1, 1, 1]
    [warning] = result.warnings
    assert warning.code == WarningCode.DEADLINE_PASSED
    assert warning.params == {"deck_id": 1, "deadline": "2026-10-31", "remaining": 5}
    assert result.deadline_paces == []


def test_planner_terms_in_triage_get_a_separate_warning() -> None:
    triage = (DeckItemRef(999, ItemStatus.TRIAGE, 50),)
    talk = deck(1, queued=4, deadline=TODAY + timedelta(days=4), extra=triage)
    result = plan(decks=[talk])
    assert result.deadline_paces[0].remaining == 4
    assert result.warnings[0].code == WarningCode.DEADLINE_TRIAGE_PENDING
    assert result.warnings[0].params == {"deck_id": 1, "count": 1}


def test_planner_interrupted_discovery_is_proposed_first() -> None:
    started = DeckItemRef(500, ItemStatus.DISCOVERING, 9)
    result = plan(
        decks=[deck(1, queued=3, extra=(started,))],
        discovering=[DiscoveringItem(500, NOW - timedelta(days=1))],
    )
    entries = new_items(result)
    assert (entries[0].lexical_item_id, entries[0].resumed, entries[0].deck_id) == (500, True, 1)
    assert [e.resumed for e in entries[1:]] == [False, False, False]


def test_planner_targeted_practice_present_with_two_errors_absent_otherwise() -> None:
    two = [
        ErrorSample("grammar.preposition.place", NOW - timedelta(days=1)),
        ErrorSample("grammar.preposition.place", NOW - timedelta(days=2)),
        ErrorSample("grammar.tense", NOW - timedelta(hours=1)),
    ]
    block = plan(recent_errors=two).block(BlockKind.TARGETED_PRACTICE)
    assert block is not None
    assert block.entries[0].category_code == "grammar.preposition.place"  # type: ignore[union-attr]
    assert block.estimated_seconds == 300

    old = [ErrorSample("grammar.tense", NOW - timedelta(days=15))] * 3
    assert plan(recent_errors=two[2:] + old).block(BlockKind.TARGETED_PRACTICE) is None


def test_planner_targeted_practice_tie_goes_to_most_recent() -> None:
    errors = [
        ErrorSample("a", NOW - timedelta(days=3)),
        ErrorSample("a", NOW - timedelta(days=2)),
        ErrorSample("b", NOW - timedelta(days=4)),
        ErrorSample("b", NOW - timedelta(hours=2)),
    ]
    block = plan(recent_errors=errors).block(BlockKind.TARGETED_PRACTICE)
    assert block is not None and block.entries[0].category_code == "b"  # type: ignore[union-attr]


def test_planner_targeted_practice_and_consolidation_take_budget_from_new_terms() -> None:
    errors = [ErrorSample("lexis.collocation", NOW)] * 2
    result = plan(recent_errors=errors, pending_consolidation_task_ids=[3], decks=[deck(1, 40)])
    # 2700 - 300 - 600 = 1800 s → 12 discoveries; quota 12 too: budget wins the tie.
    assert result.caps.budget == 12
    assert [b.kind for b in result.blocks] == [
        BlockKind.NEW_ITEMS,
        BlockKind.TARGETED_PRACTICE,
        BlockKind.CONSOLIDATION,
    ]
    assert result.total_seconds == 12 * 150 + 300 + 600


def test_planner_durations_default_then_observed_medians() -> None:
    cards = due_cards(10, direction=CardDirection.PRODUCTIVE)
    with_defaults = plan(cards=cards)
    assert with_defaults.block(BlockKind.REVIEWS).estimated_seconds == 250  # type: ignore[union-attr]
    assert with_defaults.observed_durations == []
    observed = DurationEstimates(productive_typed=12.0, observed=frozenset({"productive_typed"}))
    with_data = plan(cards=cards, durations=observed)
    assert with_data.block(BlockKind.REVIEWS).estimated_seconds == 120  # type: ignore[union-attr]
    assert with_data.observed_durations == ["productive_typed"]
