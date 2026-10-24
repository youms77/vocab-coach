"""The generated demo database: coverage, integrity and the plan at the anchor (D-033, D-034).

One full 60-day seed is built per test session and shared (read-only) by these tests.
"""

import os
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.engine import create_db_engine, get_engine, get_session
from app.db.models import (
    AICallLog,
    Card,
    Deck,
    DeckItem,
    Enrichment,
    ErrorCategory,
    ErrorEvent,
    EventLog,
    ExerciseTemplate,
    LexicalItem,
    ProductionAttempt,
    ProductionTarget,
    ReviewLog,
    StudySession,
)
from app.db.taxonomy import load_taxonomy
from app.demo.dataset import load_dataset
from app.demo.seed import seed_demo, sqlite_url
from app.domain.enums import (
    CardDirection,
    ContentOrigin,
    DeckKind,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    ProductionKind,
    SrsState,
)
from app.domain.events import EventType
from app.domain.exercise_choice import TemplateRef, choose_exercise
from app.domain.exercises import (
    GAP_FILL,
    RECOGNITION,
    SELF_ASSESSMENT,
    SELF_GRADED_TYPES,
    SPOKEN_ANSWER,
    TYPED_RECALL,
)
from app.domain.grading import production_rating, production_warnings
from app.domain.planner import BlockKind
from app.domain.speech_compare import compare, words
from app.domain.study_day import study_day_bounds
from app.domain.usage_sheet import is_usable
from app.main import create_app
from app.services import error_cards, speech
from app.services.planning import plan_today
from app.services.study_sessions import SESSION_FORMAT, compute_summary
from app.speech.audio_store import DEMO_AUDIO_DIR, AudioStore
from tests.demo_support import DEMO_ANCHOR, DEMO_SEED

DOUALA = ZoneInfo("Africa/Douala")
ANCHOR_START, _ = study_day_bounds(DEMO_ANCHOR, DOUALA, 4)
PRODUCTION_SOURCES = (ErrorSource.WRITING, ErrorSource.SPEAKING, ErrorSource.TRANSCRIPT)
WAITING_STATUSES = (ItemStatus.QUEUED, ItemStatus.TRIAGE, ItemStatus.DISCOVERING)


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The folder of the seeded demo: `vocab-coach-demo.sqlite3` and `audio-demo/`."""
    folder = tmp_path_factory.mktemp("demo")
    seed_demo(folder / "vocab-coach-demo.sqlite3", seed=DEMO_SEED, days=60, anchor=DEMO_ANCHOR)
    return folder


@pytest.fixture(scope="module")
def demo_engine(demo_dir: Path) -> Iterator[Engine]:
    engine = create_db_engine(sqlite_url(demo_dir / "vocab-coach-demo.sqlite3"))
    yield engine
    engine.dispose()


@pytest.fixture
def db(demo_engine: Engine) -> Iterator[Session]:
    with Session(demo_engine) as session:
        yield session
        session.rollback()


def _events(db: Session, event_type: EventType) -> list[EventLog]:
    return list(db.scalars(select(EventLog).where(EventLog.event_type == event_type)))


# --- coverage --------------------------------------------------------------------------------


def test_every_deck_status_and_item_status_is_present(db: Session) -> None:
    assert set(db.scalars(select(Deck.status))) == set(DeckStatus)
    assert set(db.scalars(select(LexicalItem.status))) == set(ItemStatus)


def test_new_learning_review_and_relearning_cards_are_present(db: Session) -> None:
    assert set(db.scalars(select(Card.srs_state))) == set(SrsState)


def test_decks_tell_the_planned_story(db: Session) -> None:
    decks = {deck.name: deck for deck in db.scalars(select(Deck))}
    statuses = defaultdict(Counter)
    for deck_id, status in db.execute(
        select(DeckItem.deck_id, LexicalItem.status).join(
            LexicalItem, LexicalItem.id == DeckItem.lexical_item_id
        )
    ):
        statuses[deck_id][status] += 1

    causal = statuses[decks["Causal inference reading"].id]
    assert causal[ItemStatus.QUEUED] == 0 and causal[ItemStatus.ACTIVE] in range(4, 7)
    assert statuses[decks["Thesis defence"].id][ItemStatus.QUEUED] == 0
    assert decks["Thesis defence"].status == DeckStatus.DONE
    campus = statuses[decks["Campus life"].id]
    assert decks["Campus life"].status == DeckStatus.PAUSED
    assert (
        campus[ItemStatus.QUEUED] > 0
        and campus[ItemStatus.LEARNING] + campus[ItemStatus.CONSOLIDATED] > 0
    )
    interview = decks["ML interview prep"]
    assert interview.status == DeckStatus.ACTIVE
    assert (interview.deadline - DEMO_ANCHOR).days == 18
    assert statuses[interview.id][ItemStatus.TRIAGE] > 0
    assert decks["Presenting results"].status == DeckStatus.QUEUED


def test_terms_shared_between_decks(db: Session) -> None:
    shared = db.scalars(
        select(DeckItem.lexical_item_id).group_by(DeckItem.lexical_item_id).having(func.count() > 1)
    ).all()
    assert 2 <= len(shared) <= 3


def test_one_interrupted_discovery_and_new_cards_from_the_last_session_only(db: Session) -> None:
    """Discoveries create cards without initial ratings (D-104): the only `new` cards left are
    those of the terms discovered in the last session, due the next study day."""
    assert db.scalar(select(func.count()).where(LexicalItem.status == ItemStatus.DISCOVERING)) == 1
    last = db.scalars(select(StudySession).order_by(StudySession.started_at.desc())).first()
    assert last is not None
    discovered_last = {
        event.entity_id
        for event in _events(db, EventType.DISCOVERY_COMPLETED)
        if event.study_session_id == last.id
    }
    new_cards = db.scalars(select(Card).where(Card.srs_state == SrsState.NEW)).all()
    assert len(discovered_last) >= 2
    assert {card.lexical_item_id for card in new_cards} == discovered_last
    assert len(new_cards) == 2 * len(discovered_last)
    assert all(card.due >= ANCHOR_START for card in new_cards)
    first_reviews = db.scalar(
        select(func.count()).select_from(ReviewLog).where(ReviewLog.exercise_type == "discovery")
    )
    assert first_reviews == 0


def test_at_least_ten_error_codes_with_prepositions_and_tenses_on_top(db: Session) -> None:
    codes = list(
        db.scalars(
            select(ErrorCategory.code).join(ErrorEvent, ErrorEvent.category_id == ErrorCategory.id)
        )
    )
    assert len(set(codes)) >= 10
    by_category = Counter(".".join(code.split(".")[:2]) for code in codes)
    top_two = {category for category, _ in by_category.most_common(2)}
    assert top_two == {"grammar.preposition", "grammar.tense"}


def test_fixed_expression_errors_decline_per_100_words(db: Session) -> None:
    """Rate over the last 30 days < rate over the first 30, from the event log only."""
    middle = DEMO_ANCHOR.toordinal() - 30
    words = Counter()
    errors = Counter()
    for event in _events(db, EventType.PRODUCTION_RECORDED):
        half = event.occurred_at.astimezone(DOUALA).date().toordinal() >= middle
        words[half] += event.payload["word_count"]
    for event in _events(db, EventType.ERROR_RECORDED):
        if event.payload["category_code"] != "grammar.preposition.fixed_expression":
            continue
        half = event.occurred_at.astimezone(DOUALA).date().toordinal() >= middle
        errors[half] += 1
    first, last = errors[False] / words[False] * 100, errors[True] / words[True] * 100
    assert last < first


def test_productions_have_word_counts_in_range(db: Session) -> None:
    attempts = db.scalars(
        select(ProductionAttempt).where(ProductionAttempt.kind != ProductionKind.DRILL)
    ).all()
    assert len(attempts) >= 10
    for attempt in attempts:
        if attempt.kind == ProductionKind.SHADOWING:  # a repeated sentence (D-175)
            assert attempt.word_count == 0
            continue
        if attempt.kind == ProductionKind.SPEAKING:  # the words heard (D-182)
            assert attempt.word_count == len(words(attempt.text))
        else:
            assert attempt.word_count == len(attempt.text.split())
        # Spoken answers, the silent take and the last speech (not corrected) are short.
        if attempt.kind != ProductionKind.SPEAKING or _origin(db, attempt.id) == "speaking":
            assert attempt.word_count >= 80 or attempt.ai_feedback is None


def test_lexical_errors_from_failed_reviews(db: Session) -> None:
    errors = db.scalars(select(ErrorEvent).where(ErrorEvent.source == ErrorSource.REVIEW)).all()
    assert 5 <= len(errors) <= 10
    for error in errors:
        review = db.get_one(ReviewLog, error.review_log_id)
        card = db.get_one(Card, review.card_id)
        assert review.final_rating == 1
        assert card.lexical_item_id == error.lexical_item_id
        assert card.direction == CardDirection.PRODUCTIVE


def test_most_causal_inference_productive_cards_are_stable(db: Session) -> None:
    deck_id = db.scalar(select(Deck.id).where(Deck.name == "Causal inference reading"))
    stabilities = db.scalars(
        select(Card.stability)
        .join(DeckItem, DeckItem.lexical_item_id == Card.lexical_item_id)
        .where(DeckItem.deck_id == deck_id, Card.direction == CardDirection.PRODUCTIVE)
    ).all()
    assert len(stabilities) >= 25
    assert sum((s or 0) >= 7 for s in stabilities) / len(stabilities) >= 0.8


def test_sessions_use_the_session_service_format_and_summary(db: Session) -> None:
    for study in db.scalars(select(StudySession)):
        assert study.planned["format"] == SESSION_FORMAT
        assert study.summary == compute_summary(db, study, study.ended_at)


def test_review_exercise_types_follow_the_exercise_choice(db: Session) -> None:
    templates: dict[int, list[TemplateRef]] = defaultdict(list)
    for template_id, item_id, kind in db.execute(
        select(
            ExerciseTemplate.id, ExerciseTemplate.lexical_item_id, ExerciseTemplate.exercise_type
        )
    ):
        templates[item_id].append(TemplateRef(template_id, kind))
    reps: Counter[int] = Counter()
    used: Counter[str] = Counter()
    for log, card in db.execute(
        select(ReviewLog, Card).join(Card, Card.id == ReviewLog.card_id).order_by(ReviewLog.id)
    ):
        choice = choose_exercise(
            CardDirection(card.direction),
            SrsState(log.state_before),
            log.stability_before,
            reps[card.id],
            templates[card.lexical_item_id],
        )
        assert (log.exercise_type, log.exercise_template_id) == (
            choice.exercise_type,
            choice.template_id,
        )
        # A spoken answer's proposed rating comes from its spoken check (see below).
        if log.exercise_type != SPOKEN_ANSWER:
            assert (log.auto_rating is None) == (log.exercise_type in SELF_GRADED_TYPES)
        reps[card.id] += 1
        used[log.exercise_type] += 1
    assert {SELF_ASSESSMENT, TYPED_RECALL, GAP_FILL, RECOGNITION} <= set(used)


def test_full_sheets_cover_the_terms_still_to_learn(db: Session) -> None:
    full = set(
        db.scalars(
            select(ExerciseTemplate.lexical_item_id).where(
                ExerciseTemplate.exercise_type == GAP_FILL
            )
        )
    )
    statuses = {i: s for i, s in db.execute(select(LexicalItem.id, LexicalItem.status))}
    waiting = [i for i, s in statuses.items() if s in WAITING_STATUSES]
    assert waiting and all(item_id in full for item_id in waiting)
    learned = [
        i for i, s in statuses.items() if s in (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED)
    ]
    assert sum(item_id in full for item_id in learned) >= 25
    sheets = db.scalars(select(Enrichment).where(Enrichment.is_current)).all()
    # "error": the small sheets of the cards made from errors (M5.a3).
    assert {sheet.provider for sheet in sheets} == {"demo", "error"}
    for sheet in sheets:
        assert is_usable(sheet.status, dict(sheet.content))
    assert set(db.scalars(select(ExerciseTemplate.origin).distinct())) == {
        ContentOrigin.DEMO,
        ContentOrigin.USER,  # typed recall derived from the hand-typed sheet (D-082)
    }


def test_sessions_follow_the_calendar(db: Session) -> None:
    sessions = db.scalars(select(StudySession)).all()
    assert 40 <= len(sessions) <= 56  # about 85 % of 60 days, minus a 3-day break
    local_hours = Counter(s.started_at.astimezone(DOUALA).hour for s in sessions)
    assert sum(n for hour, n in local_hours.items() if hour < 4) >= 1  # after midnight
    assert all(s.ended_at is not None and s.ended_at >= s.started_at for s in sessions)
    assert all(s.planned["plan"]["blocks"] is not None for s in sessions)


# --- integrity -------------------------------------------------------------------------------


def test_no_review_before_its_term_was_discovered(db: Session) -> None:
    early = db.scalar(
        select(func.count())
        .select_from(ReviewLog)
        .join(Card, Card.id == ReviewLog.card_id)
        .join(LexicalItem, LexicalItem.id == Card.lexical_item_id)
        .where(ReviewLog.reviewed_at < LexicalItem.discovered_at)
    )
    assert early == 0


def test_review_log_is_increasing_per_card(db: Session) -> None:
    last: dict[int, datetime] = {}
    for card_id, reviewed_at in db.execute(
        select(ReviewLog.card_id, ReviewLog.reviewed_at).order_by(ReviewLog.id)
    ):
        assert reviewed_at >= last.get(card_id, reviewed_at)
        last[card_id] = reviewed_at


def test_nothing_happens_after_the_start_of_the_anchor_day(db: Session) -> None:
    for column in (
        EventLog.occurred_at,
        ReviewLog.reviewed_at,
        ErrorEvent.occurred_at,
        StudySession.ended_at,
    ):
        assert db.scalar(select(func.max(column))) < ANCHOR_START


def test_every_business_row_has_its_event(db: Session) -> None:
    def entity_ids(event_type: EventType) -> set[int]:
        return {event.entity_id for event in _events(db, event_type)}

    assert set(db.scalars(select(Deck.id))) <= entity_ids(EventType.DECK_CREATED)
    assert set(db.scalars(select(LexicalItem.id))) <= entity_ids(EventType.ITEM_CREATED)
    assert set(db.scalars(select(Card.id))) <= entity_ids(EventType.CARD_CREATED)
    reviewed = {e.payload["review_log_id"] for e in _events(db, EventType.CARD_REVIEWED)}
    assert set(db.scalars(select(ReviewLog.id))) == reviewed
    # A drill is not "recorded": it is generated (and answered item by item).
    assert set(db.scalars(select(ProductionAttempt.id))) <= entity_ids(
        EventType.PRODUCTION_RECORDED
    ) | entity_ids(EventType.DRILL_GENERATED)
    assert set(db.scalars(select(ErrorEvent.id))) <= entity_ids(EventType.ERROR_RECORDED)
    sessions = set(db.scalars(select(StudySession.id)))
    assert sessions <= entity_ids(EventType.SESSION_STARTED)
    assert sessions <= entity_ids(EventType.SESSION_ENDED)
    links = {
        (e.payload["deck_id"], e.payload["lexical_item_id"])
        for e in _events(db, EventType.DECK_ITEM_ADDED)
    }
    rows = db.execute(select(DeckItem.deck_id, DeckItem.lexical_item_id))
    assert {tuple(row) for row in rows} == links


def test_status_history_matches_current_statuses(db: Session) -> None:
    latest: dict[int, str] = {}
    for event in db.scalars(
        select(EventLog)
        .where(EventLog.event_type == EventType.ITEM_STATUS_CHANGED)
        .order_by(EventLog.occurred_at, EventLog.id)
    ):
        latest[event.entity_id] = event.payload["to_status"]
    for item in db.scalars(select(LexicalItem)):
        assert latest.get(item.id, ItemStatus.DRAFT) == item.status


def test_bank_codes_exist_in_the_taxonomy() -> None:
    load_dataset().check_codes(category.code for category in load_taxonomy().categories)


def test_no_duplicate_term_in_a_deck(db: Session) -> None:
    rows = db.execute(
        select(DeckItem.deck_id, LexicalItem.normalized_form).join(
            LexicalItem, LexicalItem.id == DeckItem.lexical_item_id
        )
    ).all()
    assert len(rows) == len(set(rows))


# --- plan at the anchor ----------------------------------------------------------------------


def test_plan_at_the_anchor_has_reviews_new_terms_and_the_deadline_pace(db: Session) -> None:
    now = datetime.combine(DEMO_ANCHOR, time(19, 0), tzinfo=DOUALA)
    plan = plan_today(db, now)
    reviews = plan.block(BlockKind.REVIEWS)
    new_items = plan.block(BlockKind.NEW_ITEMS)
    assert reviews is not None and reviews.entries
    assert new_items is not None and new_items.entries
    interview_id = db.scalar(select(Deck.id).where(Deck.name == "ML interview prep"))
    assert [pace.deck_id for pace in plan.deadline_paces] == [interview_id]
    codes = {warning.code for warning in plan.warnings}
    assert "deadline_triage_pending" in codes
    assert "items_without_sheet" not in codes


# --- module E through the services (M5.a3, D-163) ---------------------------------------------


def test_written_productions_were_corrected_by_the_correction_service(db: Session) -> None:
    writings = db.scalars(
        select(ProductionAttempt).where(ProductionAttempt.kind == ProductionKind.WRITING)
    ).all()
    assert len(writings) >= 5
    for attempt in writings:
        feedback = attempt.ai_feedback
        assert feedback is not None and feedback["format"] == "correction-1"
        assert (feedback["provider"], feedback["prompt_version"]) == ("demo", "demo-correction-v1")
        ids = feedback["error_event_ids"]
        errors = db.scalars(select(ErrorEvent).where(ErrorEvent.id.in_(ids))).all()
        assert len(errors) == len(ids) == len(feedback["output"]["errors"])
        assert {e.source for e in errors} <= {ErrorSource.WRITING}
        for span, error_id in zip(feedback["spans"], ids, strict=True):
            error = db.get_one(ErrorEvent, error_id)
            assert error.production_attempt_id == attempt.id
            assert attempt.text[span["start"] : span["end"]] == error.erroneous_text
    assert len(_events(db, EventType.PRODUCTION_CORRECTED)) == db.scalar(
        select(func.count())
        .select_from(ProductionAttempt)
        .where(
            ProductionAttempt.ai_feedback.is_not(None),
            ProductionAttempt.kind != ProductionKind.DRILL,
        )
    )


def test_transcripts_were_analysed_and_only_the_learner_is_stored(db: Session) -> None:
    transcripts_ = db.scalars(
        select(ProductionAttempt).where(
            ProductionAttempt.kind == ProductionKind.TRANSCRIPT_ANALYSIS
        )
    ).all()
    assert len(transcripts_) >= 2
    for attempt in transcripts_:
        feedback = attempt.ai_feedback
        assert feedback is not None and feedback["format"] == "transcript-1"
        assert "Tutor" not in attempt.text and "You:" not in attempt.text
        assert feedback["context_sent"] is True
        errors = db.scalars(
            select(ErrorEvent).where(ErrorEvent.production_attempt_id == attempt.id)
        ).all()
        assert len(errors) == len(feedback["error_event_ids"])
        assert {e.source for e in errors} == {ErrorSource.TRANSCRIPT}
        assert not any(e.original_text.startswith(("Hi!", "Interesting")) for e in errors)


def test_drills_were_stored_and_answered_by_the_drill_service(db: Session) -> None:
    drills_ = db.scalars(
        select(ProductionAttempt).where(ProductionAttempt.kind == ProductionKind.DRILL)
    ).all()
    assert len(drills_) >= 5
    assert len({d.ai_feedback["category_code"] for d in drills_}) >= 3
    finished = [d for d in drills_ if len(d.ai_feedback["answers"]) == len(d.ai_feedback["items"])]
    open_ = [d for d in drills_ if d not in finished]
    assert finished and len(open_) == 1  # the last session leaves one drill half done
    assert len(_events(db, EventType.DRILL_COMPLETED)) == len(finished)
    wrong_answers = [
        a for d in drills_ for a in d.ai_feedback["answers"] if a["outcome"] == "wrong"
    ]
    assert wrong_answers
    drill_errors = db.scalars(
        select(ErrorEvent).where(ErrorEvent.source == ErrorSource.DRILL)
    ).all()
    assert {e.id for e in drill_errors} == {a["error_event_id"] for a in wrong_answers}
    drill_ids = {d.id for d in drills_}
    assert {e.production_attempt_id for e in drill_errors} <= drill_ids
    assert all(e.explanation for e in drill_errors)


def test_cards_were_made_from_recurring_errors(db: Session) -> None:
    items = db.scalars(
        select(LexicalItem).where(LexicalItem.origin_error_event_id.is_not(None))
    ).all()
    assert len(items) >= 2
    deck = db.scalars(select(Deck).where(Deck.kind == DeckKind.ERROR_DRILL)).one()
    assert deck.status == DeckStatus.ACTIVE
    for item in items:
        assert item.status in (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED)
        card = db.scalars(select(Card).where(Card.lexical_item_id == item.id)).one()
        assert card.direction == CardDirection.PRODUCTIVE  # one card per error
        assert db.scalar(
            select(func.count()).select_from(ReviewLog).where(ReviewLog.card_id == card.id)
        )
        origin = db.get_one(ErrorEvent, item.origin_error_event_id)
        assert origin.correction.casefold().startswith(item.term.casefold()[:3])
    created = _events(db, EventType.ERROR_CARD_CREATED)
    assert {e.payload["lexical_item_id"] for e in created} == {i.id for i in items}
    assert all(e.payload["recurrence"] >= 2 for e in created)
    assert len(_events(db, EventType.ERROR_SUGGESTION_DISMISSED)) == 1


def test_carded_and_dismissed_errors_are_no_longer_suggested(db: Session) -> None:
    carded = {
        error_cards.rules.pair_key(e.erroneous_text, e.correction)
        for e in db.scalars(
            select(ErrorEvent).join(LexicalItem, LexicalItem.origin_error_event_id == ErrorEvent.id)
        )
    }
    dismissed = {e.payload["key"] for e in _events(db, EventType.ERROR_SUGGESTION_DISMISSED)}
    suggested = {v.suggestion.key for v in error_cards.list_suggestions(db, limit=50)}
    assert not suggested & (carded | dismissed)


def test_the_demo_still_has_no_receptive_card_for_an_error_card(db: Session) -> None:
    item_ids = select(LexicalItem.id).where(LexicalItem.origin_error_event_id.is_not(None))
    assert not db.scalar(
        select(func.count())
        .select_from(Card)
        .where(Card.lexical_item_id.in_(item_ids), Card.direction == CardDirection.RECEPTIVE)
    )


# --- speaking (module F, M6.a2b) --------------------------------------------------------------


def _origin(db: Session, attempt_id: int) -> str | None:
    payload = db.scalar(
        select(EventLog.payload).where(
            EventLog.event_type == EventType.PRODUCTION_RECORDED,
            EventLog.entity_id == attempt_id,
        )
    )
    return payload.get("origin") if payload is not None else None


def _oral(db: Session, kind: ProductionKind) -> list[ProductionAttempt]:
    return list(
        db.scalars(
            select(ProductionAttempt)
            .where(ProductionAttempt.kind == kind)
            .order_by(ProductionAttempt.id)
        )
    )


def test_every_recording_has_its_file_and_only_recordings_have_one(
    db: Session, demo_dir: Path
) -> None:
    store = AudioStore(demo_dir / DEMO_AUDIO_DIR)
    recorded = (ProductionKind.SPEAKING, ProductionKind.SHADOWING)
    paths = []
    for attempt in db.scalars(select(ProductionAttempt)):
        if attempt.kind in recorded:
            assert attempt.audio_path is not None and store.exists(attempt.audio_path)
            assert attempt.modality == "oral"
            paths.append(attempt.audio_path)
        else:  # a pasted transcript is `oral` but has no recording
            assert attempt.audio_path is None
    files = sorted(p.relative_to(store.root).as_posix() for p in store.root.rglob("*.wav"))
    assert files == sorted(paths) and len(paths) == len(set(paths))
    assert [p.name for p in demo_dir.iterdir() if ".tmp-" in p.name or ".old-" in p.name] == []


def test_free_speeches_were_transcribed_then_corrected_by_the_speech_services(
    db: Session,
) -> None:
    speeches = [a for a in _oral(db, ProductionKind.SPEAKING) if _origin(db, a.id) == "speaking"]
    corrected = [a for a in speeches if a.ai_feedback is not None]
    assert len(corrected) >= 3
    states = Counter(speech.transcription_state(db, a) for a in speeches)
    assert states["silence"] == 1 and states["pending"] == 0
    # The last session leaves a silent take and a speech not corrected yet (screens of M6.b).
    uncorrected = [a for a in speeches if a.ai_feedback is None]
    assert sorted(speech.transcription_state(db, a) for a in uncorrected) == ["ok", "silence"]
    for attempt in corrected:
        feedback = attempt.ai_feedback
        assert feedback is not None and feedback["format"] == "speaking-1"
        assert (feedback["provider"], feedback["prompt_version"]) == ("demo", "demo-speaking-v1")
        assert feedback["output"]["structure"] is not None
        assert 5 <= (attempt.audio_seconds or 0) <= 180
        ids = feedback["error_event_ids"]
        errors = db.scalars(select(ErrorEvent).where(ErrorEvent.id.in_(ids))).all()
        assert len(errors) == len(ids) == len(feedback["output"]["errors"])
        assert {e.source for e in errors} <= {ErrorSource.SPEAKING}
        assert all(e.production_attempt_id == attempt.id for e in errors)
        assert not any(c.startswith(("spelling", "pronunciation")) for c in _codes(db, errors))
    transcribed = _events(db, EventType.PRODUCTION_TRANSCRIBED)
    assert {(e.payload["provider"], e.payload["model"]) for e in transcribed} == {
        ("demo", "demo-transcription-v1")
    }
    spoken_errors = db.scalars(select(ErrorEvent).where(ErrorEvent.source == ErrorSource.SPEAKING))
    assert all(e.production_attempt_id is not None for e in spoken_errors)


def _codes(db: Session, errors: list[ErrorEvent]) -> list[str]:
    return [db.get_one(ErrorCategory, e.category_id).code for e in errors]


def test_shadowings_compare_the_sentence_of_a_term(db: Session) -> None:
    shadowings = _oral(db, ProductionKind.SHADOWING)
    assert 4 <= len(shadowings) <= 8
    sentences = {t.sentence for t in load_dataset().all_terms() if t.sentence}
    missed = 0
    for attempt in shadowings:
        assert attempt.prompt_text in sentences
        result = speech.pronunciation_of(db, attempt.id)
        assert result is not None and result.target_text == attempt.prompt_text
        assert result.transcript == attempt.text and result.provider == "demo"
        assert len(result.unrecognized_words) <= 2
        assert result.unrecognized_words == [
            {"position": u.position, "word": u.word, "heard": u.heard}
            for u in compare(attempt.prompt_text, attempt.text).unrecognized
        ]
        missed += len(result.unrecognized_words)
        targets = db.scalars(
            select(ProductionTarget).where(ProductionTarget.production_attempt_id == attempt.id)
        ).all()
        assert len(targets) == 1
    assert missed >= 1
    assert len(_events(db, EventType.PRONUNCIATION_CHECKED)) == len(shadowings)


def test_every_spoken_answer_review_is_linked_to_its_recording(db: Session) -> None:
    logs = db.scalars(select(ReviewLog).where(ReviewLog.exercise_type == SPOKEN_ANSWER)).all()
    assert logs
    for log in logs:
        assert log.production_attempt_id is not None
        attempt = db.get_one(ProductionAttempt, log.production_attempt_id)
        assert (attempt.kind, _origin(db, attempt.id)) == ("speaking", "review")
        assert attempt.study_session_id == log.study_session_id
        assert log.audio_path == attempt.audio_path is not None
        card = db.get_one(Card, log.card_id)
        assert production_rating(attempt.ai_feedback, card.lexical_item_id) == log.auto_rating
        if log.final_rating == 1:
            assert production_warnings(attempt.ai_feedback, card.lexical_item_id) == [
                "term_not_heard"
            ]
    answers = [a for a in _oral(db, ProductionKind.SPEAKING) if _origin(db, a.id) == "review"]
    assert len(answers) == len(logs)


def test_the_demo_recordings_play_through_the_api(
    demo_dir: Path, demo_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", demo_dir / "no.env")
    for name in [name for name in os.environ if name.upper().startswith("VOCAB_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("VOCAB_DEMO", "1")
    monkeypatch.setenv("VOCAB_DATA_DIR", str(demo_dir))
    get_settings.cache_clear()
    try:
        app = create_app()

        def demo_session() -> Iterator[Session]:
            with Session(demo_engine) as session:
                yield session

        app.dependency_overrides[get_session] = demo_session
        app.dependency_overrides[get_engine] = lambda: demo_engine
        base = f"http://127.0.0.1:{get_settings().port}"
        with TestClient(app, base_url=base) as client:
            for kind in ("speaking", "shadowing"):
                listed = client.get("/api/productions", params={"kind": kind})
                assert listed.status_code == 200, listed.text
                items = listed.json()["items"]
                assert items and all(item["audio_url"] for item in items)
                for item in items:
                    played = client.get(item["audio_url"])
                    assert played.status_code == 200
                    assert played.headers["content-type"] == "audio/wav"
                    assert played.content[:4] == b"RIFF"
    finally:
        get_settings.cache_clear()


def test_a_few_shadowings_carry_pronunciation_scores(db: Session) -> None:
    """The last 2 or 3 shadowings with missed words are scored (D-217), through the same service
    as a real assessment, with the demo's provenance and no `ai_call_log` row."""
    shadowings = _oral(db, ProductionKind.SHADOWING)
    scored = [a for a in shadowings if speech.pronunciation_of(db, a.id).scores is not None]
    assert 2 <= len(scored) <= 3
    for attempt in scored:
        result = speech.pronunciation_of(db, attempt.id)
        assert result.unrecognized_words  # the take had missed words
        doc = result.scores
        assert (doc["format"], doc["provider"], doc["model"]) == (
            "azure-pa-1",
            "demo",
            "demo-pa-v1",
        )
        assert doc["status"] == "ok" and doc["words"]
        assert result.transcript == attempt.text  # the comparison is untouched
    kinds = {
        w["error_type"] for a in scored for w in speech.pronunciation_of(db, a.id).scores["words"]
    }
    assert "Mispronunciation" in kinds and "None" in kinds
    events = _events(db, EventType.PRONUNCIATION_ASSESSED)
    assert len(events) == len(scored)
    assert {(e.payload["provider"], e.payload["model"]) for e in events} == {("demo", "demo-pa-v1")}
    assert all(e.payload["ai_call_id"] is None for e in events)
    assert {e.payload["status"] for e in events} == {"ok"}
    assert any(e.payload["mispronounced"] + e.payload["omitted"] for e in events)
    assert (
        db.scalar(
            select(func.count())
            .select_from(AICallLog)
            .where(AICallLog.task == "pronunciation_assessment")
        )
        == 0
    )
