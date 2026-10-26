"""Deterministic simulation of a learner's history through the real services (D-034).

One `random.Random(seed)` feeds every other generator, the FSRS engine's included (D-022). No set
is iterated and every query that feeds a decision is ordered, so the same (seed, days, anchor,
dataset_version) always gives the same rows. Every service receives explicit instants: nothing
here reads the clock.

Calendar: study days anchor - days ... anchor - 1. About 85 % of days are worked, with a forced
3-day break around day -25 (to build a review backlog). Sessions run mostly between 18:30 and
23:30 in the `timezone` setting, some in the morning, and about 10 % after midnight (they belong
to the previous study day, D-014). Nothing happens after the start of the anchor study day.

The learner goes through the app's own paths (D-111): sessions from `study_sessions`
(`session-1`, the plan frozen at the start, the summary computed from the logs), exercise types
from `exercise_choice`, discoveries through `begin_discovery` / `finish_discovery` (no initial
ratings, D-104). Each term gets its demo sheet (`content/demo/sheets.yaml`) when it is created.

Module E goes through its services too (D-163): written productions are recorded then corrected,
transcripts are recorded then analysed, drills are stored then answered, errors are recorded by
`error_log`, and cards are made from recurring errors. The "AI" results come from
`app.demo.fictional_ai` (validated by the real output schemas); no AI is called.

Module F too (D-191): free speaking, shadowings and the spoken answers of reviews are recorded by
the speech services in this transaction (`store_speaking`, `store_recording`,
`store_spoken_answer`, D-189), with a short WAV clip (`clips.py`) written into `audio_dir` under a
name drawn from the seed, and a fictional transcription. The last session leaves a silent take and
a free speech not corrected yet. Nothing is written directly any more (D-035 is closed).
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models import Card, Deck, ErrorCategory, ExerciseTemplate, LexicalItem
from app.db.settings_store import get_setting
from app.demo import clips, fictional_ai
from app.demo.dataset import (
    Confusion,
    DemoDataset,
    DemoDeck,
    DemoDrill,
    DemoSheet,
    DemoTerm,
    DemoTermRef,
    ErrorTemplate,
    Fate,
)
from app.demo.learner import Learner, poisson
from app.domain import consolidation as consolidation_rules
from app.domain import drills as drill_rules
from app.domain import exercises as ex
from app.domain.enums import (
    CardDirection,
    ContentOrigin,
    DeckStatus,
    ErrorSource,
    ItemStatus,
    ProductionKind,
    SrsState,
)
from app.domain.events import ItemOrigin, ProductionOrigin, TriageDecision
from app.domain.exercise_choice import ExerciseChoice, TemplateRef, choose_exercise
from app.domain.fsrs_engine import FsrsEngine
from app.domain.item_status import REVIEWABLE_STATUSES
from app.domain.planner import (
    BlockKind,
    NewItemEntry,
    ReviewEntry,
    SessionPlan,
    TargetedPracticeEntry,
)
from app.domain.speech_compare import Unrecognized
from app.domain.srs import Rating, SrsEngine
from app.domain.study_day import study_day_bounds
from app.domain.transcript_import import UserByLabel, chunk_units
from app.services import (
    consolidation,
    corrections,
    drills,
    error_cards,
    error_log,
    library,
    pronunciation,
    review_flow,
    speaking,
    speech,
    spoken_review,
    transcripts,
)
from app.services import productions as production_service
from app.services.decks import change_deck_status, reorder_queue
from app.services.discovery import begin_discovery, finish_discovery
from app.services.enrichment import Provenance, add_templates, save_sheet
from app.services.items import mark_active, transition_item
from app.services.library import LibraryError
from app.services.reviews import card_state, record_review
from app.services.study_sessions import end_session, frozen_plan, start_session
from app.services.triage import apply_triage
from app.speech.audio_store import AudioStore

# Length of history the dataset's day offsets are written for; shorter runs scale them.
REFERENCE_DAYS = 60
WORKED_DAY_SHARE = 0.85
FORCED_BREAK_DAYS = (-25, -24, -23)
AFTER_MIDNIGHT_SHARE = 0.10
MORNING_SHARE = 0.10
EVENING_START, EVENING_MINUTES = time(18, 30), 300
MORNING_START, MORNING_MINUTES = time(7, 0), 90
AFTER_MIDNIGHT_MINUTES = 80
# Some days the learner stops when the plan goes past the time budget.
STOP_AT_BUDGET_SHARE = 0.25
# Some worked days are reviews only.
NO_NEW_TERMS_SHARE = 0.25
# New terms per day for decks without a deadline (deadline decks get their pace): keen at first,
# then busier from day -45 on.
APPETITE_EARLY = ((4, 5, 6), (1, 2, 1))
APPETITE_BUSY = ((0, 1, 2), (1, 2, 1))
BUSY_FROM_DAY = -45
FINAL_SESSION_NEW_TERMS = 3
MARK_ACTIVE_DAY = -5
# The consolidation task (M7.a2): tried from this day on until the deck is ready, never after
# `MARK_ACTIVE_DAY`; it asks for as many terms as the app allows.
CONSOLIDATION_DAY = -10
CONSOLIDATION_DECK = "causal"
CONSOLIDATION_TYPE = consolidation_rules.TaskType.TALK
# The sentence of a term the dataset gives no example for, and the slip of the misused term.
CONSOLIDATION_FALLBACKS = (
    "In this reading, the authors come back to {term} several times.",
    "The seminar spent twenty minutes on {term} last week.",
    "My supervisor asked me to explain {term} to the group.",
)
CONSOLIDATION_SLIP = ("it make", "it makes", "grammar.agreement")
CONSOLIDATION_SLIP_TAIL = ", and it make the argument weaker."
ARCHIVE_DAY = -8
PRODUCTION_EVERY_DAYS = (2, 4)
PRODUCTION_WORDS = (80, 300)
PRODUCTION_KINDS = (
    (ProductionKind.WRITING, ProductionKind.SPEAKING, ProductionKind.TRANSCRIPT_ANALYSIS),
    (5, 3, 2),
)
ERROR_SOURCE = {
    ProductionKind.WRITING: ErrorSource.WRITING,
    ProductionKind.SPEAKING: ErrorSource.SPEAKING,
    ProductionKind.TRANSCRIPT_ANALYSIS: ErrorSource.TRANSCRIPT,
}
# A conversation is the learner's turns of 2 to 4 sentences, one tutor line between two of them.
TURN_SENTENCES = (2, 4)
TRANSCRIPT_LABEL = "You"
TUTOR_LABEL = "Tutor"
# The text of a production has at most this many sentences (`MAX_SENTENCES`).
MAX_PRODUCTION_SENTENCES = 40
# A targeted drill every few worked days; the learner's score rises over the history.
DRILL_EVERY_DAYS = (6, 10)
DRILL_SCORE = (0.5, 0.85)
DRILL_ANSWER_MS = (4000, 14000)
# The last session leaves one drill half done.
UNFINISHED_DRILL_ANSWERS = 3
# Days (relative, scaled) when the learner makes cards from their recurring errors, how many each
# time, and the day they dismiss one suggestion.
ERROR_CARD_DAYS = (-30, -12)
ERROR_CARDS_PER_DAY = 2
DISMISS_DAY = -12
WRITING_WORDS_PER_MINUTE = 15
SPEAKING_WORDS_PER_SECOND = 2.0
# The declared length of a free speech stays inside its bounds (5 to 180 s, D-179).
SPEAKING_SECONDS = (5.0, 178.0)
# A shadowing every few days, on the original sentence of a discovered term; the recogniser
# misses 0 to 2 of its words.
SHADOWING_EVERY_DAYS = (7, 11)
SHADOWING_WORDS_PER_SECOND = 2.5
# The learner asked for a pronunciation score of the last 3 shadowings with missed words, a
# little after the take (D-217).
ASSESSED_SHADOWINGS = 3
ASSESSMENT_DELAY_S = 20
MISHEARD_WORDS = ((0, 1, 2), (1, 2, 2))
SHADOWED_STATUSES = (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED, ItemStatus.ACTIVE)
# A spoken answer lasts its words at this pace, inside its bounds (1 to 90 s).
ANSWER_WORDS_PER_SECOND = 2.0
ANSWER_SECONDS = (1.5, 90.0)
# The last session leaves a silent take and a free speech of a few sentences not corrected yet.
SILENT_TAKE_SECONDS = 6.0
UNCORRECTED_SENTENCES = 4
MAX_REVIEW_ERRORS = 10
MAX_REVIEW_ERRORS_PER_TERM = 2
# Activities stop this long before the end of the study day.
DAY_END_MARGIN = timedelta(minutes=30)
# Provenance of the hand-typed demo sheets and of their exercise templates.
DEMO_SHEET_PROVENANCE = Provenance("demo", None, "demo-sheets-v1")


@dataclass(frozen=True)
class SimulationConfig:
    seed: int
    days: int
    anchor: date


@dataclass
class _State:
    decks: dict[str, Deck] = field(default_factory=dict)
    items: dict[str, LexicalItem] = field(default_factory=dict)  # lowercased term -> item
    terms: dict[int, DemoTerm] = field(default_factory=dict)  # item id -> dataset entry
    review_errors: Counter[int] = field(default_factory=Counter)
    templates: dict[int, list[TemplateRef]] = field(default_factory=dict)  # item id -> templates
    next_production_day: int = 0
    next_drill_day: int = 0
    next_shadowing_day: int = 0
    consolidated: bool = False  # the consolidation task was made
    drills_made: int = 0
    last_drill: str | None = None
    # Shadowings with unrecognised words, in order: (production id, target, unrecognised words,
    # duration, time). The last ones are assessed at the end of the run (D-217).
    assessable: list[tuple[int, str, list[Unrecognized], float, datetime]] = field(
        default_factory=list
    )


class Simulation:
    def __init__(
        self,
        session: Session,
        dataset: DemoDataset,
        config: SimulationConfig,
        *,
        audio_dir: Path,
    ) -> None:
        if config.days < 7:
            raise ValueError("the demo history needs at least 7 days")
        self.session = session
        self.dataset = dataset
        self.config = config
        self.audio_dir = audio_dir
        root = random.Random(config.seed)  # noqa: S311 (simulation, not security)
        # Fixed derivation order: adding a generator at the end keeps the others unchanged.
        self._fsrs_rng = random.Random(root.getrandbits(64))  # noqa: S311
        self.learner = Learner(random.Random(root.getrandbits(64)))  # noqa: S311
        self._calendar = random.Random(root.getrandbits(64))  # noqa: S311
        self._choices = random.Random(root.getrandbits(64))  # noqa: S311
        self._writing = random.Random(root.getrandbits(64))  # noqa: S311
        self._drills = random.Random(root.getrandbits(64))  # noqa: S311
        self._speech = random.Random(root.getrandbits(64))  # noqa: S311
        names = random.Random(root.getrandbits(64))  # noqa: S311
        # Drawn last: the generators above keep their numbers (D-191).
        self._consolidation = random.Random(root.getrandbits(64))  # noqa: S311
        # File names drawn from the seed, so `audio_path` is reproducible (D-187).
        self.audio = AudioStore(audio_dir, names=lambda: f"{names.getrandbits(128):032x}")
        self._engines: dict[float, SrsEngine] = {}
        self.tz = ZoneInfo(get_setting(session, "timezone"))
        self.day_start_hour: int = get_setting(session, "day_start_hour")
        self.state = _State()
        self.categories: dict[str, ErrorCategory] = {
            category.code: category for category in error_log.active_categories(session)
        }
        self._templates_by_code: dict[str, list[ErrorTemplate]] = {}
        for template in dataset.error_templates:
            self._templates_by_code.setdefault(template.code, []).append(template)

    # --- helpers -------------------------------------------------------------------------------

    def engine_factory(self, retention: float) -> SrsEngine:
        """One seeded FSRS engine per retention value, shared by every service call."""
        if retention not in self._engines:
            self._engines[retention] = FsrsEngine(retention, rng=self._fsrs_rng)
        return self._engines[retention]

    def scaled(self, offset: int) -> int:
        """A dataset day offset mapped onto this run's history length."""
        days = self.config.days
        return max(-days, min(-1, round(offset * days / REFERENCE_DAYS)))

    def study_day(self, offset: int) -> date:
        return self.config.anchor + timedelta(days=offset)

    def local(self, day: date, at: time, minutes: float = 0.0) -> datetime:
        return datetime.combine(day, at, tzinfo=self.tz) + timedelta(minutes=minutes)

    def _deadline(self, spec: DemoDeck) -> date | None:
        if spec.deadline_day is None:
            return None
        offset = spec.deadline_day if spec.deadline_day > 0 else self.scaled(spec.deadline_day)
        return self.study_day(offset)

    def _fated(self, fate: Fate) -> list[LexicalItem]:
        return [
            self.state.items[term.term.lower()]
            for term in self.dataset.all_terms()
            if term.fate == fate and term.term.lower() in self.state.items
        ]

    # --- run -----------------------------------------------------------------------------------

    def run(self) -> None:
        days = self.config.days
        breaks = {self.scaled(day) for day in FORCED_BREAK_DAYS}
        self.state.next_production_day = -days + self._writing.randint(1, 3)
        self.state.next_drill_day = -days + 4 + self._drills.randint(*DRILL_EVERY_DAYS)
        self.state.next_shadowing_day = -days + 2 + self._speech.randint(*SHADOWING_EVERY_DAYS)
        for offset in range(-days, 0):
            day = self.study_day(offset)
            final = offset == -1
            worked = final or (offset not in breaks and self._calendar.random() < WORKED_DAY_SHARE)
            start = self._session_start(day) if worked else None
            admin_at = (start or self.local(day, time(20, 0))) - timedelta(minutes=10)
            self._daily_admin(offset, admin_at)
            if start is not None:
                _, day_end = study_day_bounds(day, self.tz, self.day_start_hour)
                self._run_session(offset, start, day_end - DAY_END_MARGIN, final=final)
        self._assess_shadowings()

    def _session_start(self, day: date) -> datetime:
        draw = self._calendar.random()
        if draw < AFTER_MIDNIGHT_SHARE:
            minutes = self._calendar.uniform(0, AFTER_MIDNIGHT_MINUTES)
            return self.local(day + timedelta(days=1), time(0, 0), minutes)
        if draw < AFTER_MIDNIGHT_SHARE + MORNING_SHARE:
            return self.local(day, MORNING_START, self._calendar.uniform(0, MORNING_MINUTES))
        return self.local(day, EVENING_START, self._calendar.uniform(0, EVENING_MINUTES))

    # --- deck and term lifecycle ---------------------------------------------------------------

    def _daily_admin(self, offset: int, at: datetime) -> None:
        for spec in self.dataset.decks:
            if self.scaled(spec.created_day) == offset:
                self._create_deck(spec, at)
            for batch_index, batch in enumerate(spec.triage_batches):
                if self.scaled(batch.day) == offset:
                    self._triage_batch(spec, batch.count, first=batch_index == 0, at=at)
            for event in spec.status_events:
                if self.scaled(event.day) == offset:
                    change_deck_status(self.session, self.state.decks[spec.key], event.to, at)
        if offset in {self.scaled(day) for day in ERROR_CARD_DAYS}:
            self._error_cards(at, dismiss=offset == self.scaled(DISMISS_DAY))
        if offset == self.scaled(ARCHIVE_DAY):
            for item in self._fated(Fate.ARCHIVED):
                transition_item(self.session, item, ItemStatus.ARCHIVED, at)
        if not self.state.consolidated and self.scaled(CONSOLIDATION_DAY) <= offset < self.scaled(
            MARK_ACTIVE_DAY
        ):
            self.state.consolidated = self._consolidate(at)
        if offset == self.scaled(MARK_ACTIVE_DAY):
            # What the consolidation task did not reach (it takes the 15 most fragile terms).
            for item in self._fated(Fate.ACTIVE):
                # A shortened history may not have discovered the term yet.
                if item.status in (ItemStatus.LEARNING, ItemStatus.CONSOLIDATED):
                    mark_active(self.session, item, at)

    def _consolidate(self, at: datetime) -> bool:
        """The learner's consolidation task, through the app's services (M7.a2): a talk on the
        causal deck once it is ready, written then corrected, its result applied, then completed.
        Returns False (nothing written) when the deck is not ready yet."""
        deck = self.state.decks.get(CONSOLIDATION_DECK)
        if deck is None:
            return False
        state = consolidation.deck_state(self.session, deck)
        if not state.readiness.ready:
            return False
        rng = self._consolidation
        item_ids = consolidation_rules.select_terms(
            state.readiness.candidates, consolidation_rules.MAX_TERMS
        )
        refs = [consolidation_rules.term_ref(i) for i in range(len(item_ids))]
        template = consolidation.load_templates()[CONSOLIDATION_TYPE]
        output = fictional_ai.consolidation_task(
            template,
            task_type=CONSOLIDATION_TYPE,
            deck_name=deck.name,
            domain=deck.domain,
            refs=refs,
        )
        task = consolidation.store_task(
            self.session,
            deck_id=deck.id,
            task_type=CONSOLIDATION_TYPE,
            output=output,
            item_ids=item_ids,
            refs=refs,
            source="ai",
            reason=None,
            provenance=fictional_ai.CONSOLIDATION_PROVENANCE,
            at=at,
        )
        # One term is used wrongly and one is forgotten; the terms the dataset wants active are
        # spared so that the task activates them, if it selected them.
        others = [i for i in item_ids if self.state.terms[i].fate != Fate.ACTIVE]
        pool = others if len(others) >= 2 else list(item_ids)
        misused = rng.choice(pool)
        absent = rng.choice([i for i in pool if i != misused])
        sentences: list[str] = []
        for item_id in item_ids:
            if item_id == absent:
                continue
            term = self.state.terms[item_id]
            base = term.sentence or rng.choice(CONSOLIDATION_FALLBACKS).format(term=term.term)
            if item_id == misused:
                base = base.rstrip(".!? ") + CONSOLIDATION_SLIP_TAIL
            sentences.append(base)
        attempt = production_service.record_written_production(
            self.session,
            text=" ".join(sentences),
            prompt=output.prompt_en,
            targets=dict.fromkeys(item_ids),
            at=at,
            kind=ProductionKind.CONSOLIDATION,
            origin=ProductionOrigin.CONSOLIDATION,
            consolidation_task_id=task.id,
        )
        consolidation.note_attempt(self.session, task.id, at)
        prepared = corrections.prepare(
            self.session, attempt.id, kinds=(ProductionKind.CONSOLIDATION,)
        )
        wrong, correction, code = CONSOLIDATION_SLIP
        corrections.store_correction(
            self.session,
            prepared,
            fictional_ai.consolidation_correction(
                prepared,
                misused_ref=item_ids.index(misused),
                wrong=wrong,
                correction=correction,
                category_code=code,
            ),
            source=ErrorSource.CONSOLIDATION,
            provenance=fictional_ai.CORRECTION_PROVENANCE,
            ai_call_id=None,
            at=at,
        )
        consolidation.apply_result(self.session, attempt.id, at)
        consolidation.change_status(
            self.session, task.id, consolidation_rules.TaskStatus.COMPLETED, at=at
        )
        return True

    def _create_deck(self, spec: DemoDeck, at: datetime) -> None:
        others = list(
            self.session.scalars(
                select(Deck)
                .where(Deck.status != DeckStatus.DONE)
                .order_by(Deck.queue_position, Deck.id)
            )
        )
        position = None if spec.queue == "front" else len(others)
        source_id = None
        if spec.source is not None:
            source = library.create_source(
                self.session,
                title=spec.source.title,
                author=spec.source.author,
                domain=spec.domain,
                at=at,
            )
            source_id = source.id
        deck = library.create_deck(
            self.session,
            name=spec.name,
            description=spec.description,
            domain=spec.domain,
            source_id=source_id,
            deadline=self._deadline(spec),
            queue_position=position,
            at=at,
        )
        self.state.decks[spec.key] = deck
        if spec.queue == "front":
            reorder_queue(self.session, [deck.id, *(other.id for other in others)], at)

        for position, entry in enumerate(spec.terms):
            if isinstance(entry, DemoTermRef):
                item = self.state.items[entry.ref.lower()]
                library.add_item_to_deck(self.session, deck, item, at, position=position)
                continue
            item = library.create_item(
                self.session,
                term=entry.term,
                at=at,
                origin=ItemOrigin.DEMO,
                sentence=entry.sentence,
                item_type=entry.type,
                part_of_speech=entry.pos,
                deck_id=deck.id,
            )
            self.state.items[entry.term.lower()] = item
            self.state.terms[item.id] = entry
            library.add_item_to_deck(self.session, deck, item, at, position=position)
            demo_sheet = self.dataset.sheet_of(entry.term)
            if demo_sheet is not None:
                self._add_sheet(item, entry, demo_sheet, at)
            if entry.fate == Fate.DRAFT:
                continue
            target = ItemStatus.TRIAGE if spec.intake == "triage" else ItemStatus.QUEUED
            transition_item(self.session, item, target, at)

    def _add_sheet(self, item: LexicalItem, term: DemoTerm, demo: DemoSheet, at: datetime) -> None:
        """The demo sheet, typed by hand, and its templates (gap-fill first, so that the typed
        recall derived by `save_sheet` gets the accepted forms)."""
        version = DEMO_SHEET_PROVENANCE.prompt_version
        exercises = demo.exercises
        if exercises is not None:
            add_templates(
                self.session,
                item.id,
                [(ex.GAP_FILL, exercises.gap_fill.model_dump())],
                at,
                origin=ContentOrigin.DEMO,
                prompt_version=version,
            )
        sheet = demo.sheet
        if sheet.part_of_speech is None and term.pos is not None:
            sheet = sheet.model_copy(update={"part_of_speech": term.pos})
        save_sheet(self.session, item.id, sheet, at, provenance=DEMO_SHEET_PROVENANCE)
        if exercises is not None:
            recognition = exercises.recognition_in_sentence.model_dump()
            add_templates(
                self.session,
                item.id,
                [
                    (ex.RECOGNITION, recognition),
                    (ex.LISTENING, recognition),
                    (ex.SENTENCE_PRODUCTION, exercises.sentence_production.model_dump()),
                    (ex.SPOKEN_ANSWER, exercises.spoken_answer.model_dump()),
                ],
                at,
                origin=ContentOrigin.DEMO,
                prompt_version=version,
            )
        self._register_templates(item)

    def _register_templates(self, item: LexicalItem) -> None:
        self.state.templates[item.id] = [
            TemplateRef(template_id, kind)
            for template_id, kind in self.session.execute(
                select(ExerciseTemplate.id, ExerciseTemplate.exercise_type)
                .where(ExerciseTemplate.lexical_item_id == item.id)
                .order_by(ExerciseTemplate.id)
            )
        ]

    def _error_cards(self, at: datetime, *, dismiss: bool) -> None:
        """The learner makes cards from their recurring errors (module E, M5.a3) and, once,
        dismisses a suggestion they do not want."""
        views = error_cards.list_suggestions(self.session, limit=10)
        for view in [v for v in views if v.cardable][:ERROR_CARDS_PER_DAY]:
            try:
                made = error_cards.create_card_from_error(
                    self.session, view.error_id, at=at, engine_factory=self.engine_factory
                )
            except LibraryError:
                continue  # the term appeared in the library meanwhile: nothing to learn twice
            self._register_templates(made.item)
        if dismiss:
            left = error_cards.list_suggestions(self.session, limit=10)
            if left:
                error_cards.dismiss_suggestion(self.session, left[-1].suggestion.key, at=at)

    def _triage_batch(self, spec: DemoDeck, count: int, *, first: bool, at: datetime) -> None:
        pending = [
            self.state.items[term.term.lower()]
            for term in spec.own_terms()
            if self.state.items[term.term.lower()].status == ItemStatus.TRIAGE
        ]
        decided = 0
        for item in pending:
            fate = self.state.terms[item.id].fate
            if fate == Fate.TRIAGE:
                continue  # left for later: the deadline warns about it
            if fate == Fate.KNOWN:
                if first:
                    apply_triage(self.session, [(item.id, TriageDecision.KNOWN)], at)
                continue
            if decided < count:
                apply_triage(self.session, [(item.id, TriageDecision.LEARN)], at)
                decided += 1

    # --- sessions ------------------------------------------------------------------------------

    def _run_session(self, offset: int, start: datetime, stop: datetime, *, final: bool) -> None:
        study, created = start_session(self.session, start, self.engine_factory)
        plan = frozen_plan(study)
        if not created or plan is None:
            raise RuntimeError(f"day {offset}: expected a new study session at {start}")
        t = self._reviews(plan, study.id, start, stop)
        if final:
            t = self._ensure_relearning(study.id, t)
        if final or self._choices.random() >= NO_NEW_TERMS_SHARE:
            t = self._new_terms(offset, plan, study.id, t, stop, final=final)
        if offset >= self.state.next_shadowing_day and t < stop:
            t = self._shadowing(study.id, t)
            self.state.next_shadowing_day = offset + self._speech.randint(*SHADOWING_EVERY_DAYS)
        if offset >= self.state.next_production_day and t < stop:
            t = self._production(offset, study.id, t)
            self.state.next_production_day = offset + self._writing.randint(*PRODUCTION_EVERY_DAYS)
        if self.dataset.drills and (final or (offset >= self.state.next_drill_day and t < stop)):
            t = self._drill(offset, plan, study.id, t, unfinished=final)
            self.state.next_drill_day = offset + self._drills.randint(*DRILL_EVERY_DAYS)
        if final:
            t = self._unfinished_speaking(study.id, t)
        end_session(self.session, study, t)
        self.session.flush()

    def _pause(self, t: datetime) -> datetime:
        return t + timedelta(seconds=self._choices.uniform(2, 8))

    def _reviews(self, plan: SessionPlan, study_id: int, t: datetime, stop: datetime) -> datetime:
        block = plan.block(BlockKind.REVIEWS)
        if block is None:
            return t
        stop_at_budget = self._choices.random() < STOP_AT_BUDGET_SHARE
        for entry in block.entries:
            if not isinstance(entry, ReviewEntry):
                continue
            if (stop_at_budget and entry.overflow) or t >= stop:
                break
            card = self.session.get_one(Card, entry.card_id)
            t = self._review(card, study_id, t)
        return t

    def _review(
        self,
        card: Card,
        study_id: int,
        t: datetime,
        *,
        force_again: bool = False,
    ) -> datetime:
        item = self.session.get_one(LexicalItem, card.lexical_item_id)
        if item.status not in REVIEWABLE_STATUSES:
            return t
        direction = CardDirection(card.direction)
        state = card_state(card)
        engine = self.engine_factory(get_setting(self.session, "target_retention"))
        choice = self._choice(card, item.id)
        outcome = self.learner.review(
            item.id, direction, state.state, engine.retrievability(state, t), choice.exercise_type
        )
        final = Rating.AGAIN if force_again else outcome.final_rating
        if choice.exercise_type == ex.SPOKEN_ANSWER and choice.template_id is not None:
            elapsed = outcome.response_time_ms
            self._spoken_answer(card, choice.template_id, final, elapsed, study_id, t)
            return self._pause(t + timedelta(milliseconds=outcome.response_time_ms))
        auto = outcome.auto_rating
        if force_again and auto is not None:
            auto = Rating.AGAIN
        confusion = self._confusion_for(item, direction) if final == Rating.AGAIN else None
        log = record_review(
            self.session,
            card,
            final,
            t,
            outcome.response_time_ms,
            outcome.exercise_type,
            answer=confusion.wrong if confusion else None,
            auto_rating=auto,
            study_session_id=study_id,
            exercise_template_id=choice.template_id,
            engine_factory=self.engine_factory,
        )
        if confusion is not None:
            term = self.state.terms[item.id]
            error_log.record_error(
                self.session,
                source=ErrorSource.REVIEW,
                category=self.categories[confusion.code],
                erroneous_text=confusion.wrong,
                correction=term.sentence or term.term,
                at=t,
                original_text=confusion.prompt,
                explanation=confusion.explanation,
                lexical_item_id=item.id,
                review_log_id=log.id,
                study_session_id=study_id,
            )
            self.state.review_errors[item.id] += 1
        return self._pause(t + timedelta(milliseconds=outcome.response_time_ms))

    def _choice(self, card: Card, item_id: int) -> ExerciseChoice:
        state = card_state(card)
        return choose_exercise(
            CardDirection(card.direction),
            state.state,
            state.stability,
            card.reps or 0,
            self.state.templates.get(item_id, []),
        )

    def _spoken_answer(
        self,
        card: Card,
        template_id: int,
        final: Rating,
        response_time_ms: int,
        study_id: int,
        t: datetime,
    ) -> None:
        """A spoken answer, checked like the app does it (`spoken_review`): recorded, transcribed,
        corrected, then rated with the production. A success says the example answer; a failure
        leaves the term out (not heard: no proposed rating)."""
        template = self.session.get_one(ExerciseTemplate, template_id)
        success = final != Rating.AGAIN
        text = (
            str(template.content["example_answer"])
            if success
            else self._speech.choice(self.dataset.speech.forgotten_answers)
        )
        low, high = ANSWER_SECONDS
        duration = round(min(max(len(text.split()) / ANSWER_WORDS_PER_SECOND, low), high), 1)
        checked = spoken_review.store_spoken_answer(
            self.session,
            self.audio,
            card_id=card.id,
            study_session_id=study_id,
            exercise_template_id=template_id,
            data=clips.tone(),
            content_type=clips.CONTENT_TYPE,
            duration_s=duration,
            transcription=fictional_ai.transcription(text, duration),
            correct=lambda prepared: fictional_ai.speaking_output(prepared, [], term_used=success),
            provenance=fictional_ai.SPEAKING_PROVENANCE,
            at=t,
        )
        ctx = review_flow.card_context(self.session, card.id, ex.SPOKEN_ANSWER, template_id)
        review_flow.record(
            self.session,
            ctx,
            answer=None,
            choice_index=None,
            response_time_ms=response_time_ms,
            final_rating=final,
            expected_reps=card.reps or 0,
            study_session_id=study_id,
            now=t,
            production_attempt_id=checked.production_id,
            engine_factory=self.engine_factory,
        )

    def _confusion_for(self, item: LexicalItem, direction: CardDirection) -> Confusion | None:
        term = self.state.terms.get(item.id)
        if (
            term is None
            or term.confusion is None
            or direction != CardDirection.PRODUCTIVE
            or sum(self.state.review_errors.values()) >= MAX_REVIEW_ERRORS
            or self.state.review_errors[item.id] >= MAX_REVIEW_ERRORS_PER_TERM
        ):
            return None
        return term.confusion

    def _ensure_relearning(self, study_id: int, t: datetime) -> datetime:
        """The last session leaves at least one card in Relearning (a lapse just before the end)."""
        relearning = self.session.scalar(
            select(exists().where(Card.srs_state == SrsState.RELEARNING))
        )
        if relearning:
            return t
        cards = self.session.scalars(
            select(Card)
            .join(LexicalItem, LexicalItem.id == Card.lexical_item_id)
            .where(
                Card.srs_state == SrsState.REVIEW,
                LexicalItem.status.in_(sorted(REVIEWABLE_STATUSES)),
                Card.last_review_at <= t,
            )
            .order_by(Card.id)
        )
        # A card that may not be due: never one whose exercise is a spoken answer, which is only
        # checked when the card is due (D-183).
        spoken = ex.SPOKEN_ANSWER
        card = next(
            (c for c in cards if self._choice(c, c.lexical_item_id).exercise_type != spoken), None
        )
        if card is None:
            return t
        return self._review(card, study_id, t, force_again=True)

    # --- new terms -----------------------------------------------------------------------------

    def _choose_new_terms(self, plan: SessionPlan, offset: int, final: bool) -> list[NewItemEntry]:
        """The plan's new terms the learner takes today, in plan order.

        Deadline decks get exactly their pace; spare energy (an appetite drawn per day, high at
        the start of the history, lower once the "busy" phase begins) goes to decks without a
        deadline. The learner never starts a waiting deck: they stop at the first term of a deck the
        planner lists in `decks_to_activate` (decks are activated on purpose, through the
        dataset's status events). The last session takes at least three terms.
        """
        block = plan.block(BlockKind.NEW_ITEMS)
        if block is None:
            return []
        waiting = set(plan.decks_to_activate)
        pace_left = {pace.deck_id: pace.required_per_day for pace in plan.deadline_paces}
        weights = APPETITE_EARLY if offset < self.scaled(BUSY_FROM_DAY) else APPETITE_BUSY
        spare = self._choices.choices(weights[0], weights=weights[1])[0]
        eligible: list[NewItemEntry] = []
        chosen: list[NewItemEntry] = []
        for entry in block.entries:
            if not isinstance(entry, NewItemEntry):
                continue
            if entry.deck_id in waiting:
                break
            eligible.append(entry)
            if entry.resumed:
                chosen.append(entry)
            elif entry.deck_id in pace_left:
                if pace_left[entry.deck_id] > 0:
                    pace_left[entry.deck_id] -= 1
                    chosen.append(entry)
            elif spare > 0:
                spare -= 1
                chosen.append(entry)
        if final:
            extra = [entry for entry in eligible if entry not in chosen]
            chosen += extra[: max(0, FINAL_SESSION_NEW_TERMS - len(chosen))]
            chosen.sort(key=eligible.index)
        return chosen

    def _new_terms(
        self,
        offset: int,
        plan: SessionPlan,
        study_id: int,
        t: datetime,
        stop: datetime,
        *,
        final: bool,
    ) -> datetime:
        entries = self._choose_new_terms(plan, offset, final)
        for index, entry in enumerate(entries):
            if t >= stop:
                break
            item = self.session.get_one(LexicalItem, entry.lexical_item_id)
            deck = self.session.get(Deck, entry.deck_id) if entry.deck_id is not None else None
            begin_discovery(self.session, item, deck, t, study_session_id=study_id)
            # Last session: the last term is interrupted (left `discovering`).
            if final and index == len(entries) - 1:
                t = self._pause(t + timedelta(seconds=40))
                continue
            duration_ms = self.learner.discovery_ms()
            t += timedelta(milliseconds=duration_ms)
            finish_discovery(
                self.session,
                item,
                t,
                study_session_id=study_id,
                duration_ms=duration_ms,
                guess=None,
                exercise_results=(),
                personal_sentence=None,
                engine_factory=self.engine_factory,
            )
            t = self._pause(t)
        return t

    # --- productions and errors ----------------------------------------------------------------

    def _error_rate(self, code: str, progress: float) -> float:
        start, end = self.dataset.error_rates.get(
            code, (self.dataset.default_error_rate, self.dataset.default_error_rate)
        )
        return start + (end - start) * progress

    def _production(self, offset: int, study_id: int, t: datetime) -> datetime:
        rng = self._writing
        kinds, weights = PRODUCTION_KINDS
        kind = rng.choices(kinds, weights=weights)[0]
        prompt = rng.choice([p.text for p in self.dataset.prompts if p.kind == kind])
        target_words = rng.randint(*PRODUCTION_WORDS)
        progress = (offset + self.config.days) / max(self.config.days - 1, 1)

        made: list[ErrorTemplate] = []
        for code in sorted(self._templates_by_code):
            mean = self._error_rate(code, progress) * target_words / 100
            for _ in range(poisson(rng, mean)):
                template = rng.choice(self._templates_by_code[code])
                # A conversation or a speech leaves spelling out (the AI tasks do too).
                if kind == ProductionKind.WRITING or not template.code.startswith(
                    transcripts.EXCLUDED_CODE_PREFIXES
                ):
                    made.append(template)
        made = made[:MAX_PRODUCTION_SENTENCES]
        sentences = [template.original for template in made]
        words = sum(len(sentence.split()) for sentence in sentences)
        fillers = list(self.dataset.fillers)
        rng.shuffle(fillers)
        for filler in fillers * 3:
            if words >= target_words or len(sentences) >= MAX_PRODUCTION_SENTENCES:
                break
            sentences.append(filler)
            words += len(filler.split())
        rng.shuffle(sentences)

        audio_seconds = round(words / SPEAKING_WORDS_PER_SECOND, 1)
        if kind == ProductionKind.WRITING:
            word_count = self._written(prompt, " ".join(sentences), made, t, study_id)
            duration = timedelta(minutes=word_count / WRITING_WORDS_PER_MINUTE)
        else:
            if kind == ProductionKind.TRANSCRIPT_ANALYSIS:
                self._transcript(prompt, sentences, made, t, study_id)
            else:
                self._spoken(prompt, " ".join(sentences), made, t, audio_seconds, study_id)
            duration = timedelta(seconds=audio_seconds * 2.5)
        return self._pause(t + duration)

    def _written(
        self, prompt: str, text: str, made: list[ErrorTemplate], t: datetime, study_id: int
    ) -> int:
        """A writing exercise, recorded then corrected like the app does it; returns its words."""
        attempt = production_service.record_written_production(
            self.session,
            text=text,
            prompt=prompt,
            targets={},
            at=t,
            kind=ProductionKind.WRITING,
            study_session_id=study_id,
            origin=ProductionOrigin.WRITING,
        )
        prepared = corrections.prepare(self.session, attempt.id)
        corrections.store_correction(
            self.session,
            prepared,
            fictional_ai.correction_output(prepared, made),
            source=ErrorSource.WRITING,
            provenance=fictional_ai.CORRECTION_PROVENANCE,
            ai_call_id=None,
            at=t,
        )
        return attempt.word_count

    def _spoken(
        self,
        prompt: str,
        text: str,
        made: list[ErrorTemplate],
        t: datetime,
        audio_seconds: float,
        study_id: int,
    ) -> None:
        """A free speech, recorded, transcribed and corrected like the app does it (D-182)."""
        low, high = SPEAKING_SECONDS
        duration = min(max(audio_seconds, low), high)
        recorded = speaking.store_speaking(
            self.session,
            self.audio,
            data=clips.tone(),
            content_type=clips.CONTENT_TYPE,
            duration_s=duration,
            transcription=fictional_ai.transcription(text, duration),
            prompt_text=prompt,
            study_session_id=study_id,
            at=t,
        )
        prepared = speaking.prepare_speaking(self.session, recorded.production_id)
        corrections.store_speaking_correction(
            self.session,
            prepared.correction,
            fictional_ai.speaking_output(
                prepared,
                made,
                structure=self._speech.choice(self.dataset.speech.structure),
                connectors=self.dataset.speech.connectors,
            ),
            source=prepared.correction.source,
            provenance=fictional_ai.SPEAKING_PROVENANCE,
            ai_call_id=None,
            at=t,
        )

    def _shadowing(self, study_id: int, t: datetime) -> datetime:
        """The learner repeats the original sentence of a term they know; the recogniser misses 0
        to 2 of its words, which the comparator reports (D-173)."""
        rng = self._speech
        known = [
            (item_id, term.sentence)
            for item_id, term in self.state.terms.items()
            if term.sentence
            and self.session.get_one(LexicalItem, item_id).status in SHADOWED_STATUSES
        ]
        if not known:
            return t
        item_id, sentence = rng.choice(known)
        missed = rng.choices(MISHEARD_WORDS[0], weights=MISHEARD_WORDS[1])[0]
        heard = fictional_ai.misheard(sentence, rng, missed)
        duration = round(min(max(len(sentence.split()) / SHADOWING_WORDS_PER_SECOND, 1.0), 30.0), 1)
        recorded = speech.store_recording(
            self.session,
            self.audio,
            speech.shadowing_recording(sentence, item_id=item_id, study_session_id=study_id),
            data=clips.tone(),
            content_type=clips.CONTENT_TYPE,
            duration_s=duration,
            transcription=fictional_ai.transcription(heard, duration),
            at=t,
        )
        comparison = recorded.transcription.comparison
        if comparison is not None and comparison.unrecognized:
            self.state.assessable.append(
                (recorded.production_id, sentence, list(comparison.unrecognized), duration, t)
            )
        return self._pause(t + timedelta(seconds=duration * 3))

    def _assess_shadowings(self) -> None:
        """The last shadowings that have unrecognised words are scored, as if the learner had asked
        Azure for them. No random draw: the other generators keep their sequence (D-217)."""
        for production_id, sentence, unrecognized, duration, t in self.state.assessable[
            -ASSESSED_SHADOWINGS:
        ]:
            pronunciation.store_assessment(
                self.session,
                production_id,
                fictional_ai.pronunciation_result(sentence, unrecognized, duration),
                at=t + timedelta(seconds=duration + ASSESSMENT_DELAY_S),
            )

    def _unfinished_speaking(self, study_id: int, t: datetime) -> datetime:
        """The last session: a take where nothing was said (silence), then a short free speech
        transcribed but not corrected yet, so the screens have both cases."""
        rng = self._speech
        prompts = [p.text for p in self.dataset.prompts if p.kind == ProductionKind.SPEAKING]
        speaking.store_speaking(
            self.session,
            self.audio,
            data=clips.silence(),
            content_type=clips.CONTENT_TYPE,
            duration_s=SILENT_TAKE_SECONDS,
            transcription=fictional_ai.transcription("", SILENT_TAKE_SECONDS),
            prompt_text=rng.choice(prompts),
            study_session_id=study_id,
            at=t,
        )
        t = self._pause(t + timedelta(seconds=SILENT_TAKE_SECONDS * 2))
        text = " ".join(rng.sample(list(self.dataset.fillers), UNCORRECTED_SENTENCES))
        low, high = SPEAKING_SECONDS
        duration = round(min(max(len(text.split()) / SPEAKING_WORDS_PER_SECOND, low), high), 1)
        speaking.store_speaking(
            self.session,
            self.audio,
            data=clips.tone(),
            content_type=clips.CONTENT_TYPE,
            duration_s=duration,
            transcription=fictional_ai.transcription(text, duration),
            prompt_text=rng.choice(prompts),
            study_session_id=study_id,
            at=t,
        )
        return self._pause(t + timedelta(seconds=duration * 2))

    def _transcript(
        self,
        title: str,
        sentences: list[str],
        made: list[ErrorTemplate],
        t: datetime,
        study_id: int,
    ) -> None:
        """A pasted conversation: its learner turns are recorded, then analysed (like the app)."""
        rng = self._writing
        lines: list[str] = [f"{TUTOR_LABEL}: {rng.choice(self.dataset.tutor_lines)}"]
        remaining = list(sentences)
        while remaining:
            size = rng.randint(*TURN_SENTENCES)
            lines.append(f"{TRANSCRIPT_LABEL}: {' '.join(remaining[:size])}")
            remaining = remaining[size:]
            if remaining:
                lines.append(f"{TUTOR_LABEL}: {rng.choice(self.dataset.tutor_lines)}")
        conversation = "\n".join(lines)
        user = UserByLabel(label=TRANSCRIPT_LABEL)
        attempt = transcripts.record_transcript(
            self.session,
            text=conversation,
            user=user,
            title=title,
            occurred_on=None,
            study_session_id=study_id,
            at=t,
        )
        prepared = transcripts.prepare(
            self.session, attempt.id, transcripts.TranscriptSource(conversation, user)
        )
        results = [
            transcripts.ChunkResult(
                output=fictional_ai.transcript_chunk(prepared, chunk, made),
                provider=fictional_ai.TRANSCRIPT_PROVENANCE[0],
                model=fictional_ai.TRANSCRIPT_PROVENANCE[1],
                prompt_version=fictional_ai.TRANSCRIPT_PROVENANCE[2],
                call_id=None,
                units=chunk,
            )
            for chunk in chunk_units(prepared.units)
        ]
        found = sum(len(result.output.errors) for result in results)
        if found != len(made):
            raise ValueError(f"demo transcript: {len(made)} errors expected, {found} placed")
        transcripts.store_analysis(self.session, prepared, results, at=t)

    # --- targeted drills -----------------------------------------------------------------------

    def _choose_drill(self, plan: SessionPlan) -> DemoDrill:
        """The drill of the plan's targeted category when the dataset has one, else the next one."""
        banks = self.dataset.drills
        block = plan.block(BlockKind.TARGETED_PRACTICE)
        entry = next(
            (e for e in (block.entries if block else []) if isinstance(e, TargetedPracticeEntry)),
            None,
        )
        if entry is not None:
            for bank in banks:
                if (
                    entry.category_code == bank.code
                    or entry.category_code.startswith(bank.code + ".")
                ) and bank.code != self.state.last_drill:
                    return bank
        # Never the same drill twice in a row: the next one in the file.
        following = [bank for bank in banks if bank.code != self.state.last_drill]
        return following[self.state.drills_made % len(following)]

    def _drill(
        self, offset: int, plan: SessionPlan, study_id: int, t: datetime, *, unfinished: bool
    ) -> datetime:
        """A drill, stored then answered item by item like the app does it. The learner's score
        rises over the history; an unfinished drill stops after a few items."""
        bank = self._choose_drill(plan)
        self.state.drills_made += 1
        self.state.last_drill = bank.code
        rng = self._drills
        codes = {c for c in self.categories if c == bank.code or c.startswith(bank.code + ".")}
        attempt = drills.store_drill(
            self.session,
            bank.code,
            fictional_ai.drill_output(bank, codes),
            provenance=fictional_ai.DRILL_PROVENANCE,
            ai_call_id=None,
            study_session_id=study_id,
            at=t,
        )
        progress = (offset + self.config.days) / max(self.config.days - 1, 1)
        score = DRILL_SCORE[0] + (DRILL_SCORE[1] - DRILL_SCORE[0]) * progress
        answered = UNFINISHED_DRILL_ANSWERS if unfinished else len(bank.items)
        for index, item in enumerate(bank.items[:answered]):
            right = rng.random() < score
            elapsed_ms = rng.randint(*DRILL_ANSWER_MS)
            t += timedelta(milliseconds=elapsed_ms)
            answer: str | None = None
            choice: int | None = None
            if item.kind == "gap_fill":
                answer = item.answer if right else item.wrong
            else:
                shown = drill_rules.options_order(attempt.id, index, list(item.options or []))
                wanted = item.answer if right else next(o for o in shown if o != item.answer)
                choice = shown.index(wanted)
            drills.answer_item(
                self.session,
                attempt.id,
                index,
                answer=answer,
                choice_index=choice,
                response_time_ms=elapsed_ms,
                at=t,
            )
            t += timedelta(seconds=rng.uniform(2, 6))
        return t


def simulate(
    session: Session, dataset: DemoDataset, config: SimulationConfig, *, audio_dir: Path
) -> None:
    """Fill `session` with the demo history and `audio_dir` with its recordings; the caller
    commits (and moves the folder into place)."""
    Simulation(session, dataset, config, audio_dir=audio_dir).run()
