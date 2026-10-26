"""Consolidation rules (app/domain/consolidation.py): pure."""

import pytest
import yaml

from app.config import REPO_ROOT
from app.domain.consolidation import (
    DEFAULT_TERMS,
    MAX_TERMS,
    MIN_TERMS,
    Candidate,
    NotReadyReason,
    ProductiveCard,
    TaskStatus,
    TaskType,
    api_status,
    can_transition,
    classify_target,
    clamp_ratio,
    db_status,
    deck_readiness,
    kind_of,
    parse_templates,
    select_terms,
    template_task,
    term_count,
    term_ref,
    type_of,
)
from app.domain.enums import (
    ConsolidationTaskKind,
    ConsolidationTaskStatus,
    DeckKind,
    DeckStatus,
    ItemStatus,
)

DAYS = 7.0


@pytest.fixture
def templates():
    path = REPO_ROOT / "content" / "consolidation_templates.yaml"
    return parse_templates(yaml.safe_load(path.read_text(encoding="utf-8")))


def card(item_id: int, stability: float | None, status: ItemStatus = ItemStatus.CONSOLIDATED):
    return ProductiveCard(item_id, status, stability)


def readiness(cards, *, kind=DeckKind.CUSTOM, status=DeckStatus.ACTIVE, open_task=False, ratio=0.8):
    return deck_readiness(
        kind=kind,
        status=status,
        cards=cards,
        open_task=open_task,
        threshold_ratio=ratio,
        min_stability_days=DAYS,
    )


def consolidated(n: int, stability: float = 10.0) -> list[ProductiveCard]:
    return [card(i, stability) for i in range(1, n + 1)]


def test_a_ready_deck() -> None:
    result = readiness(consolidated(10))
    assert result.ready and result.reason is None
    assert (result.stable_cards, result.productive_cards, result.ratio) == (10, 10, 1.0)
    assert len(result.candidates) == 10


def test_every_reason() -> None:
    cards = consolidated(10)
    assert readiness(cards, kind=DeckKind.ERROR_DRILL).reason is NotReadyReason.EXCLUDED_KIND
    assert readiness(cards, status=DeckStatus.DONE).reason is NotReadyReason.DECK_DONE
    assert readiness(cards, open_task=True).reason is NotReadyReason.TASK_OPEN
    assert readiness([]).reason is NotReadyReason.NO_PRODUCTIVE_CARDS
    low = [*consolidated(7), *[card(20 + i, 1.0, ItemStatus.LEARNING) for i in range(3)]]
    assert readiness(low).reason is NotReadyReason.BELOW_RATIO
    few = consolidated(MIN_TERMS - 1)
    assert readiness(few).reason is NotReadyReason.NOT_ENOUGH_CANDIDATES


def test_reasons_are_checked_in_order() -> None:
    assert (
        readiness([], kind=DeckKind.ERROR_DRILL, status=DeckStatus.DONE, open_task=True).reason
        is NotReadyReason.EXCLUDED_KIND
    )
    assert readiness([], status=DeckStatus.DONE, open_task=True).reason is NotReadyReason.DECK_DONE
    assert readiness([], open_task=True).reason is NotReadyReason.TASK_OPEN


def test_a_paused_deck_is_eligible() -> None:
    assert readiness(consolidated(8), status=DeckStatus.PAUSED).ready


def test_the_ratio_boundary_is_exact() -> None:
    def deck(stable: int, total: int) -> list[ProductiveCard]:
        return [
            *consolidated(stable),
            *[card(100 + i, 1.0, ItemStatus.LEARNING) for i in range(total - stable)],
        ]

    assert readiness(deck(80, 100)).ready  # 80 %
    below = readiness(deck(799, 1000), ratio=0.8)  # 79.9 %
    assert below.reason is NotReadyReason.BELOW_RATIO
    assert readiness(deck(799, 1000), ratio=0.799).ready


def test_the_threshold_is_clamped() -> None:
    assert clamp_ratio(0.1) == 0.5 and clamp_ratio(3.0) == 1.0 and clamp_ratio(0.8) == 0.8
    half = [*consolidated(8), *[card(50 + i, 1.0, ItemStatus.LEARNING) for i in range(8)]]
    assert readiness(half, ratio=0.0).ready  # read as 0.5


def test_candidate_count_boundary() -> None:
    assert readiness(consolidated(MIN_TERMS - 1)).reason is NotReadyReason.NOT_ENOUGH_CANDIDATES
    assert readiness(consolidated(MIN_TERMS)).ready


def test_archived_and_known_terms_leave_the_count() -> None:
    cards = [
        *consolidated(8),
        card(90, 1.0, ItemStatus.ARCHIVED),
        card(91, None, ItemStatus.KNOWN),
    ]
    result = readiness(cards)
    assert result.productive_cards == 8 and result.ready


def test_active_terms_count_but_are_not_candidates() -> None:
    cards = [*consolidated(8), card(60, 30.0, ItemStatus.ACTIVE)]
    result = readiness(cards)
    assert (result.stable_cards, result.productive_cards) == (9, 9)
    assert 60 not in {c.item_id for c in result.candidates}


def test_candidates_are_the_most_fragile_first_ties_by_id() -> None:
    cards = [card(5, 9.0), card(3, 8.0), card(4, 8.0), card(1, 20.0)]
    cards += [card(10 + i, 12.0) for i in range(6)]
    result = readiness(cards)
    assert [c.item_id for c in result.candidates[:4]] == [3, 4, 5, 10]
    assert readiness(list(reversed(cards))).candidates == result.candidates


def test_select_terms_bounds() -> None:
    candidates = [Candidate(i, float(i)) for i in range(1, 21)]
    assert select_terms(candidates) == list(range(1, DEFAULT_TERMS + 1))
    assert len(select_terms(candidates, 3)) == MIN_TERMS
    assert len(select_terms(candidates, 99)) == MAX_TERMS
    assert select_terms(candidates[:9], 15) == list(range(1, 10))
    assert select_terms(candidates[:5], 12) == [1, 2, 3, 4, 5]  # never more than there are
    assert select_terms([], 12) == []


def test_select_terms_is_deterministic_and_breaks_ties_by_id() -> None:
    candidates = [Candidate(9, 5.0), Candidate(2, 5.0), Candidate(4, 1.0)] + [
        Candidate(20 + i, 50.0) for i in range(8)
    ]
    assert select_terms(candidates, 8)[:3] == [4, 2, 9]
    assert select_terms(list(reversed(candidates)), 8) == select_terms(candidates, 8)


def test_term_count() -> None:
    assert term_count(None, 20) == DEFAULT_TERMS
    assert term_count(0, 20) == MIN_TERMS and term_count(40, 20) == MAX_TERMS


def test_type_and_status_mappings() -> None:
    assert kind_of(TaskType.TALK) is ConsolidationTaskKind.PRESENTATION
    for task_type in TaskType:
        assert type_of(kind_of(task_type)) is task_type
    assert db_status(TaskStatus.COMPLETED) is ConsolidationTaskStatus.DONE
    for status in TaskStatus:
        assert api_status(db_status(status)) is status


@pytest.mark.parametrize(
    ("source", "target", "allowed"),
    [
        (TaskStatus.PROPOSED, TaskStatus.ACCEPTED, True),
        (TaskStatus.PROPOSED, TaskStatus.DISMISSED, True),
        (TaskStatus.PROPOSED, TaskStatus.COMPLETED, False),
        (TaskStatus.ACCEPTED, TaskStatus.COMPLETED, True),
        (TaskStatus.ACCEPTED, TaskStatus.DISMISSED, True),
        (TaskStatus.ACCEPTED, TaskStatus.PROPOSED, False),
        (TaskStatus.COMPLETED, TaskStatus.DISMISSED, False),
        (TaskStatus.DISMISSED, TaskStatus.ACCEPTED, False),
    ],
)
def test_transitions(source: TaskStatus, target: TaskStatus, allowed: bool) -> None:
    assert can_transition(source, target) is allowed


def test_template_task_spreads_terms_in_turn(templates) -> None:
    refs = [term_ref(i) for i in range(12)]
    task = template_task(
        templates[TaskType.TALK],
        task_type=TaskType.TALK,
        deck_name="Causal inference reading",
        domain="statistics",
        refs=refs,
    )
    sections = task["sections"]
    assert 4 <= len(sections) <= 5
    spread = [ref for section in sections for ref in section["term_refs"]]
    assert sorted(spread, key=lambda r: int(r[1:])) == refs
    assert sections[0]["term_refs"][:2] == ["t1", f"t{len(sections) + 1}"]
    assert "Causal inference reading" in task["title_en"] + task["prompt_en"]
    assert "{deck}" not in str(task) and "{domain}" not in str(task)
    assert task["task_type"] == "talk"


@pytest.mark.parametrize(
    ("used", "correctly", "error", "outcome"),
    [
        (True, True, False, "correct"),
        (True, True, True, "misused"),  # the AI says correct but logged an error on the term
        (True, False, False, "misused"),
        (True, None, False, "unknown"),  # no verdict
        (True, None, True, "misused"),
        (False, False, False, "absent"),
        (False, None, True, "absent"),
        (None, None, False, "unknown"),
    ],
)
def test_classify_target(used, correctly, error, outcome) -> None:
    result = classify_target(used=used, used_correctly=correctly, has_error=error)
    assert result.value == outcome
