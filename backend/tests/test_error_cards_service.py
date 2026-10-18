"""Cards made from errors and suggestions (app/services/error_cards.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Card, Deck, Enrichment, ErrorEvent, ExerciseTemplate, LexicalItem
from app.db.taxonomy import sync_taxonomy
from app.domain import exercises as ex
from app.domain.enums import (
    CardDirection,
    DeckKind,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    SrsState,
)
from app.domain.grading import ConfusionKind, Outcome
from app.domain.usage_sheet import read_sheet
from app.services import error_cards, error_log, review_flow
from app.services.error_log import ErrorNotFound
from app.services.planning import plan_today
from tests.factories import add_item
from tests.library_support import count, events

PREPOSITION = "grammar.preposition.fixed_expression"
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)  # 10:00 in Africa/Douala, study day 16th


def make_error(
    session: Session,
    wrong: str = "in campus",
    right: str = "on campus",
    original: str = "Most of my friends live in campus this year.",
    *,
    source: ErrorSource = ErrorSource.WRITING,
    days_ago: int = 0,
    code: str = PREPOSITION,
) -> ErrorEvent:
    sync_taxonomy(session)
    return error_log.record_error(
        session,
        source=source,
        category=error_log.active_category(session, code),
        erroneous_text=wrong,
        correction=right,
        original_text=original,
        explanation="With 'campus', English uses 'on'.",
        at=NOW - timedelta(days=days_ago),
    )


def test_a_card_is_made_from_an_error(session: Session) -> None:
    error = make_error(session)
    made = error_cards.create_card_from_error(session, error.id, at=NOW)
    session.commit()

    item = made.item
    assert (item.term, item.status, item.origin_error_event_id) == (
        "on campus",
        ItemStatus.LEARNING,
        error.id,
    )
    assert item.origin_sentence == "Most of my friends live on campus this year."
    assert item.discovered_at is not None

    deck = session.scalars(select(Deck)).one()
    assert (deck.kind, deck.status, deck.name) == (
        DeckKind.ERROR_DRILL,
        DeckStatus.ACTIVE,
        error_cards.DECK_NAME,
    )
    assert [link.lexical_item_id for link in deck.items] == [item.id]

    card = session.scalars(select(Card)).one()  # one productive card, no receptive one
    assert (card.direction, card.srs_state, card.reps) == (
        CardDirection.PRODUCTIVE,
        SrsState.NEW,
        0,
    )
    # Due at the start of the next study day (04:00 in Africa/Douala), like a discovery.
    assert card.due == datetime(2026, 10, 17, 3, 0, tzinfo=UTC)

    templates = session.scalars(select(ExerciseTemplate)).all()
    assert [(t.exercise_type, t.origin) for t in templates] == [(ex.GAP_FILL, "user")]
    assert templates[0].content["answer"] == "on"

    sheet = session.scalars(select(Enrichment)).one()
    assert (sheet.provider, sheet.status, sheet.is_current) == ("error", "complete", True)
    assert read_sheet(dict(sheet.content)).french_speaker_pitfalls[0].wrong == "in campus"


def test_the_events_tell_the_whole_story(session: Session) -> None:
    error = make_error(session)
    make_error(session, days_ago=2)  # the same mistake twice
    made = error_cards.create_card_from_error(session, error.id, at=NOW)
    session.commit()

    (created,) = events(session, "error.card_created")
    assert created == {
        "error_event_id": error.id,
        "lexical_item_id": made.item.id,
        "card_id": made.card.id,
        "deck_id": made.deck.id,
        "category_code": PREPOSITION,
        "source": "writing",
        "recurrence": 2,
    }
    assert events(session, "item.created")[0]["origin"] == "error"
    assert [e["to_status"] for e in events(session, "item.status_changed")] == ["learning"]
    assert [e["direction"] for e in events(session, "card.created")] == ["productive"]
    assert len(events(session, "deck.created")) == 1


def test_the_deck_is_shared_by_the_next_cards(session: Session) -> None:
    first = make_error(session)
    second = make_error(session, "in university", "at university", "She is in university now.")
    error_cards.create_card_from_error(session, first.id, at=NOW)
    error_cards.create_card_from_error(session, second.id, at=NOW)
    session.commit()
    assert count(session, Deck) == 1
    assert count(session, Card) == 2


def test_an_error_gives_one_card(session: Session) -> None:
    error = make_error(session)
    made = error_cards.create_card_from_error(session, error.id, at=NOW)
    with pytest.raises(error_cards.CardExists) as excinfo:
        error_cards.create_card_from_error(session, error.id, at=NOW)
    assert excinfo.value.extra == {"item_id": made.item.id}


def test_a_term_already_in_the_library_is_not_made_again(session: Session) -> None:
    error = make_error(session)
    existing = add_item(session, "on campus")
    existing.normalized_form = "on campus"
    with pytest.raises(error_cards.CardExists) as excinfo:
        error_cards.create_card_from_error(session, error.id, at=NOW)
    assert excinfo.value.extra == {"item_id": existing.id}
    assert count(session, Card) == 0


def test_a_refusal_writes_nothing(session: Session) -> None:
    error = make_error(session, original="")
    with pytest.raises(error_cards.NotCardableError) as excinfo:
        error_cards.create_card_from_error(session, error.id, at=NOW)
    assert excinfo.value.extra == {"reason": "no_context"}
    assert (count(session, Deck), count(session, LexicalItem), count(session, Card)) == (0, 0, 0)


def test_a_sentence_and_a_term_of_the_user(session: Session) -> None:
    error = make_error(session, original="")
    made = error_cards.create_card_from_error(
        session, error.id, at=NOW, sentence="We met on campus.", term="on campus"
    )
    assert made.item.origin_sentence == "We met on campus."


def test_an_unknown_error(session: Session) -> None:
    sync_taxonomy(session)
    with pytest.raises(ErrorNotFound):
        error_cards.create_card_from_error(session, 999, at=NOW)


def test_a_term_the_library_cannot_store_is_refused(session: Session) -> None:
    error = make_error(session, original="")
    with pytest.raises(error_cards.NotCardableError) as excinfo:
        error_cards.create_card_from_error(
            session, error.id, at=NOW, sentence="We met on campus.", term="on | campus"
        )
    assert excinfo.value.extra == {"reason": "invalid_term"}


def test_the_card_comes_back_in_the_next_days_reviews(session: Session) -> None:
    made = error_cards.create_card_from_error(session, make_error(session).id, at=NOW)
    session.commit()
    today = [e for e in plan_today(session, NOW).blocks if e.kind == "reviews"]
    assert not today or all(
        entry.card_id != made.card.id for block in today for entry in block.entries
    )
    tomorrow = plan_today(session, NOW + timedelta(days=1))
    reviews = [e for block in tomorrow.blocks if block.kind == "reviews" for e in block.entries]
    assert [e.card_id for e in reviews] == [made.card.id]


def test_the_review_shows_the_gap_and_the_wrong_form_is_a_mistake(session: Session) -> None:
    made = error_cards.create_card_from_error(session, make_error(session).id, at=NOW)
    session.commit()
    step = review_flow.review_step(session, made.card)
    assert step.exercise_type == ex.GAP_FILL
    assert step.prompt == {"sentence": "Most of my friends live ___ campus this year."}

    ctx = review_flow.card_context(
        session, made.card.id, step.exercise_type, step.exercise_template_id
    )
    for typed, outcome in [("on", Outcome.EXACT), ("in", Outcome.WRONG), ("at", Outcome.WRONG)]:
        graded = review_flow.grade(
            session, ctx, answer=typed, choice_index=None, response_time_ms=3000, now=NOW
        )
        assert graded.result.outcome is outcome
    graded = review_flow.grade(
        session, ctx, answer="in", choice_index=None, response_time_ms=3000, now=NOW
    )
    assert graded.result.confusion is not None
    assert graded.result.confusion.kind is ConfusionKind.PITFALL


def test_falling_back_into_the_error_keeps_its_category(session: Session) -> None:
    made = error_cards.create_card_from_error(session, make_error(session).id, at=NOW)
    ctx = review_flow.card_context(session, made.card.id, ex.GAP_FILL, 1)
    graded = review_flow.grade(
        session, ctx, answer="in", choice_index=None, response_time_ms=3000, now=NOW
    )
    created = review_flow._confusion_error(
        session,
        ctx,
        graded,
        review_log_id=None,
        now=NOW,  # noqa: SLF001
        study_session_id=None,
    )
    assert created is not None
    assert error_log.categories_of(session, [created])[created.category_id].code == PREPOSITION
    assert created.source == ErrorSource.REVIEW
    assert created.lexical_item_id == made.item.id


# --- Suggestions ---------------------------------------------------------------------------------


def seed_recurring(session: Session) -> None:
    make_error(session, days_ago=4)
    make_error(session, days_ago=2)
    make_error(session, days_ago=0)
    make_error(session, "in university", "at university", "She is in university.", days_ago=1)
    make_error(session, "in university", "at university", "He is in university.", days_ago=3)
    make_error(session, "by purpose", "on purpose", "I did it by purpose.")  # once: not recurring


def test_recurring_errors_are_suggested_with_the_error_to_use(session: Session) -> None:
    seed_recurring(session)
    views = error_cards.list_suggestions(session)
    assert [(v.suggestion.key, v.suggestion.count, v.term, v.cardable) for v in views] == [
        ("in campus => on campus", 3, "on campus", True),
        ("in university => at university", 2, "at university", True),
    ]
    latest = session.get_one(ErrorEvent, views[0].error_id)
    assert latest.occurred_at == NOW


def test_a_drill_error_never_recurs(session: Session) -> None:
    for days in (0, 1, 2):
        make_error(session, source=ErrorSource.DRILL, days_ago=days)
    assert error_cards.list_suggestions(session) == []


def test_an_error_without_a_sentence_is_suggested_as_not_cardable(session: Session) -> None:
    make_error(session, original="", days_ago=1)
    make_error(session, original="", days_ago=0)
    (view,) = error_cards.list_suggestions(session)
    assert (view.cardable, view.reason, view.term) == (False, "no_context", None)


def test_the_newest_error_that_can_become_a_card_is_proposed(session: Session) -> None:
    older = make_error(session, days_ago=3)
    make_error(session, original="", days_ago=0)
    (view,) = error_cards.list_suggestions(session)
    assert (view.cardable, view.error_id) == (True, older.id)


def test_a_suggestion_disappears_once_it_has_a_card(session: Session) -> None:
    seed_recurring(session)
    first = error_cards.list_suggestions(session)[0]
    error_cards.create_card_from_error(session, first.error_id, at=NOW)
    assert [v.suggestion.key for v in error_cards.list_suggestions(session)] == [
        "in university => at university"
    ]


def test_a_term_already_in_the_library_is_not_suggested(session: Session) -> None:
    seed_recurring(session)
    existing = add_item(session, "at university")
    existing.normalized_form = "at university"
    assert [v.suggestion.key for v in error_cards.list_suggestions(session)] == [
        "in campus => on campus"
    ]


def test_a_dismissed_suggestion_stays_dismissed(session: Session) -> None:
    seed_recurring(session)
    assert error_cards.dismiss_suggestion(session, "in campus => on campus", at=NOW) is True
    assert error_cards.dismiss_suggestion(session, "in campus => on campus", at=NOW) is False
    assert [v.suggestion.key for v in error_cards.list_suggestions(session)] == [
        "in university => at university"
    ]
    (dismissed,) = events(session, "error.suggestion_dismissed")
    assert (dismissed["key"], dismissed["count"]) == ("in campus => on campus", 3)
    # A new occurrence does not bring it back: the user said no.
    make_error(session, days_ago=0)
    assert [v.suggestion.key for v in error_cards.list_suggestions(session)] == [
        "in university => at university"
    ]


def test_only_a_recurring_error_can_be_dismissed(session: Session) -> None:
    seed_recurring(session)
    for key in ("by purpose => on purpose", "nothing => at all"):
        with pytest.raises(error_cards.SuggestionNotFound):
            error_cards.dismiss_suggestion(session, key, at=NOW)
    assert events(session, "error.suggestion_dismissed") == []


def test_the_limit_and_the_minimum_count(session: Session) -> None:
    seed_recurring(session)
    assert len(error_cards.list_suggestions(session, limit=1)) == 1
    assert len(error_cards.list_suggestions(session, min_count=3)) == 1
    assert len(error_cards.list_suggestions(session, min_count=1)) == 3
