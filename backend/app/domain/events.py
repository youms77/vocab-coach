"""Event catalogue for the shared `event_log` (docs/SPEC.md section 5). Pure Python.

Every business change writes one of these events. Statistics read them, so a payload is a contract:
fields are validated (`extra="forbid"`), and a breaking change bumps `payload_version`.
Later modules add event types here.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    CardDirection,
    DeckKind,
    DeckStatus,
    EnrichmentStatus,
    ErrorSource,
    ItemStatus,
    ItemType,
    Modality,
    ProductionKind,
)
from app.domain.settings_defaults import SETTINGS

Id = Annotated[int, Field(ge=1)]
Rating = Annotated[int, Field(ge=1, le=4)]


class EventType(StrEnum):
    DECK_CREATED = "deck.created"
    DECK_STATUS_CHANGED = "deck.status_changed"
    DECK_REORDERED = "deck.reordered"
    DECK_ITEM_ADDED = "deck.item_added"
    DECK_UPDATED = "deck.updated"
    DECK_DELETED = "deck.deleted"
    DECK_ITEM_REMOVED = "deck.item_removed"
    ITEM_CREATED = "item.created"
    ITEM_STATUS_CHANGED = "item.status_changed"
    ITEM_TRIAGED = "item.triaged"
    ITEM_MERGED = "item.merged"
    ITEM_EDITED = "item.edited"
    ITEM_DELETED = "item.deleted"
    IMPORT_COMPLETED = "import.completed"
    ENRICHMENT_GENERATED = "enrichment.generated"
    ENRICHMENT_EDITED = "enrichment.edited"
    EXERCISE_TEMPLATE_EDITED = "exercise_template.edited"
    LIST_EXTENSION_GENERATED = "list_extension.generated"
    DISCOVERY_COMPLETED = "discovery.completed"
    CARD_CREATED = "card.created"
    CARD_REVIEWED = "card.reviewed"
    PRODUCTION_RECORDED = "production.recorded"
    PRODUCTION_CORRECTED = "production.corrected"
    PRODUCTION_TRANSCRIBED = "production.transcribed"
    PRONUNCIATION_CHECKED = "pronunciation.checked"
    PRONUNCIATION_ASSESSED = "pronunciation.assessed"
    ERROR_RECORDED = "error.recorded"
    ERROR_UPDATED = "error.updated"
    ERROR_DELETED = "error.deleted"
    ERROR_CARD_CREATED = "error.card_created"
    ERROR_SUGGESTION_DISMISSED = "error.suggestion_dismissed"
    ERROR_CATEGORY_CREATED = "error_category.created"
    ERROR_CATEGORY_PROPOSED = "error_category.proposed"
    ERROR_CATEGORY_RESOLVED = "error_category.resolved"
    DRILL_GENERATED = "drill.generated"
    DRILL_ITEM_ANSWERED = "drill.item_answered"
    DRILL_COMPLETED = "drill.completed"
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SETTING_CHANGED = "setting.changed"
    AI_CREDENTIAL_CHANGED = "ai.credential_changed"


class ItemOrigin(StrEnum):
    IMPORT = "import"
    QUICK_ADD = "quick_add"
    EXTENSION = "extension"
    CURRICULUM = "curriculum"
    ERROR = "error"
    DEMO = "demo"


class TriageDecision(StrEnum):
    KNOWN = "known"
    UNSURE = "unsure"
    LEARN = "learn"


class Event(BaseModel):
    """Base class. Subclasses set the class variables; instances are the payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: ClassVar[EventType]
    payload_version: ClassVar[int] = 1
    entity_type: ClassVar[str]
    # Name of the payload field holding the entity id (None: no single entity).
    entity_id_field: ClassVar[str | None] = None

    def entity_id(self) -> int | None:
        return getattr(self, self.entity_id_field) if self.entity_id_field else None


# --- Decks -------------------------------------------------------------------------------------


class DeckCreated(Event):
    event_type = EventType.DECK_CREATED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    kind: DeckKind
    status: DeckStatus


class DeckStatusChanged(Event):
    event_type = EventType.DECK_STATUS_CHANGED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    from_status: DeckStatus
    to_status: DeckStatus


class DeckReordered(Event):
    event_type = EventType.DECK_REORDERED
    entity_type = "deck"

    # All decks that are not done, in their new queue order.
    deck_ids: list[Id]


class DeckItemAdded(Event):
    """A term was put in a deck (a `deck_item` row): new, or already in another deck (D-013)."""

    event_type = EventType.DECK_ITEM_ADDED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    lexical_item_id: Id


class DeckItemRemoved(Event):
    """A term left a deck: a list-extension suggestion triaged as known (D-084)."""

    event_type = EventType.DECK_ITEM_REMOVED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    lexical_item_id: Id


class DeckUpdated(Event):
    """Deck fields edited by the user (names only, never the values)."""

    event_type = EventType.DECK_UPDATED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    fields: Annotated[list[str], Field(min_length=1)]


class DeckDeleted(Event):
    """A deck with no history was deleted, with the terms that belonged to no other deck."""

    event_type = EventType.DECK_DELETED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    deleted_item_ids: list[Id]


class ImportCompleted(Event):
    """A Markdown list was imported into `deck_id` (counts over the rows the user validated)."""

    event_type = EventType.IMPORT_COMPLETED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    lines_read: Annotated[int, Field(ge=0)]
    imported: Annotated[int, Field(ge=0)]  # new terms created
    attached: Annotated[int, Field(ge=0)]  # existing terms linked to the deck
    skipped: Annotated[int, Field(ge=0)]  # excluded, `skip`, or already in the deck
    ambiguous: Annotated[int, Field(ge=0)]  # ambiguous in the file (imported only if confirmed)


# --- Items -------------------------------------------------------------------------------------


class ItemCreated(Event):
    event_type = EventType.ITEM_CREATED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    item_type: ItemType
    origin: ItemOrigin
    deck_id: Id | None = None


class ItemStatusChanged(Event):
    event_type = EventType.ITEM_STATUS_CHANGED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    from_status: ItemStatus
    to_status: ItemStatus


class ItemTriaged(Event):
    event_type = EventType.ITEM_TRIAGED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    decision: TriageDecision


class ItemMerged(Event):
    event_type = EventType.ITEM_MERGED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    # The item that is kept; `merged_item_id` is folded into it.
    lexical_item_id: Id
    merged_item_id: Id


class ItemEdited(Event):
    """Term fields edited by the user (names only, never the values)."""

    event_type = EventType.ITEM_EDITED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    fields: Annotated[list[str], Field(min_length=1)]


class ItemDeleted(Event):
    """A term with no history was deleted (terms with history are archived instead)."""

    event_type = EventType.ITEM_DELETED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id


# --- Usage sheets and discovery ----------------------------------------------------------------


class EnrichmentGenerated(Event):
    event_type = EventType.ENRICHMENT_GENERATED
    entity_type = "enrichment"
    entity_id_field = "enrichment_id"

    enrichment_id: Id
    lexical_item_id: Id
    status: EnrichmentStatus
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    # The current sheet this one replaced (a regeneration), if any.
    replaced_enrichment_id: Id | None = None


class EnrichmentEdited(Event):
    """A sheet saved by the user: an edit of `base_enrichment_id`, or typed by hand (None)."""

    event_type = EventType.ENRICHMENT_EDITED
    entity_type = "enrichment"
    entity_id_field = "enrichment_id"

    enrichment_id: Id
    lexical_item_id: Id
    base_enrichment_id: Id | None = None


class ExerciseTemplateEdited(Event):
    event_type = EventType.EXERCISE_TEMPLATE_EDITED
    entity_type = "exercise_template"
    entity_id_field = "exercise_template_id"

    exercise_template_id: Id
    lexical_item_id: Id
    exercise_type: str


class ListExtensionGenerated(Event):
    """Suggestions of the AI for a deck, after duplicates were dropped (counts only, no text)."""

    event_type = EventType.LIST_EXTENSION_GENERATED
    entity_type = "deck"
    entity_id_field = "deck_id"

    deck_id: Id
    requested: Annotated[int, Field(ge=1)]
    suggested: Annotated[int, Field(ge=0)]  # in the AI's answer
    created: Annotated[int, Field(ge=0)]  # new terms waiting for triage
    dropped_existing: Annotated[int, Field(ge=0)]  # exact duplicates of the library
    dropped_in_batch: Annotated[int, Field(ge=0)]  # repeated in the answer, or beyond `requested`


class DiscoveryExerciseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exercise_type: Annotated[str, Field(min_length=1, max_length=64)]
    outcome: Literal["exact", "form", "typo", "wrong", "empty"]


class DiscoveryCompleted(Event):
    """Version 2 (M4) adds the user's guess (step 2) and the results of the immediate exercises
    (step 4). Both are optional, so version 1 payloads still read."""

    event_type = EventType.DISCOVERY_COMPLETED
    payload_version = 2
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    duration_ms: Annotated[int, Field(ge=0)] | None = None
    guess: Annotated[str, Field(max_length=1000)] | None = None
    exercise_results: Annotated[list[DiscoveryExerciseResult], Field(max_length=10)] = []


# --- Reviews, productions, errors --------------------------------------------------------------


class CardCreated(Event):
    event_type = EventType.CARD_CREATED
    entity_type = "card"
    entity_id_field = "card_id"

    card_id: Id
    lexical_item_id: Id
    direction: CardDirection


class CardReviewed(Event):
    event_type = EventType.CARD_REVIEWED
    entity_type = "card"
    entity_id_field = "card_id"

    card_id: Id
    review_log_id: Id
    lexical_item_id: Id
    direction: CardDirection
    exercise_type: str
    auto_rating: Rating | None = None
    final_rating: Rating
    response_time_ms: Annotated[int, Field(ge=0)] | None = None


class ProductionOrigin(StrEnum):
    """Where a production, written or spoken, comes from; for a written one it decides the source
    of its errors (M5)."""

    WRITING = "writing"  # free writing (module E)
    # The personal sentence of a discovery (module B), or its spoken step 4: a shadowing.
    DISCOVERY = "discovery"
    REVIEW = "review"  # a `sentence_production` review checked by the AI (module C)
    TRANSCRIPT = "transcript"  # the user's turns of a pasted conversation transcript (M5.a2)
    SHADOWING = "shadowing"  # a sentence repeated after the speech synthesis (module F, M6.a1)
    SPEAKING = "speaking"  # free speaking on a topic (module F, M6.a2)


class ProductionRecorded(Event):
    """Version 2 (M5) adds `origin`, optional so version 1 payloads still read. Version 3 (M5.a2)
    adds the `transcript` origin and, for a transcript, its turn and word counts and the date of
    the conversation (never any text). Version 4 (M6.a1) adds the `shadowing` origin, and the
    `discovery` origin on a spoken production; `audio_seconds` is the duration the recorder
    measured. Version 5 (M6.a2) adds the `speaking` origin (free speaking); a spoken answer in a
    review is a `speaking` production with the `review` origin."""

    event_type = EventType.PRODUCTION_RECORDED
    payload_version = 5
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    kind: ProductionKind
    modality: Modality
    word_count: Annotated[int, Field(ge=0)]
    audio_seconds: Annotated[float, Field(ge=0)] | None = None
    origin: ProductionOrigin | None = None
    turns_total: Annotated[int, Field(ge=0)] | None = None
    turns_user: Annotated[int, Field(ge=0)] | None = None
    words_user: Annotated[int, Field(ge=0)] | None = None
    occurred_on: date | None = None  # the day of the conversation, when the user gave it


class ProductionCorrected(Event):
    """A production corrected by the AI (written once: a second correction is refused). Version 2
    (M6.a2) adds the production's `kind` (writing, transcript_analysis, speaking), optional so
    version 1 payloads still read."""

    event_type = EventType.PRODUCTION_CORRECTED
    payload_version = 2
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    kind: ProductionKind | None = None
    word_count: Annotated[int, Field(ge=0)]
    sentence_count: Annotated[int, Field(ge=0)]
    error_count: Annotated[int, Field(ge=0)]
    naturalness_note_count: Annotated[int, Field(ge=0)]
    targets: Annotated[int, Field(ge=0)]
    targets_used_correctly: Annotated[int, Field(ge=0)]
    provider: Annotated[str, Field(max_length=50)]
    model: Annotated[str, Field(max_length=200)]
    prompt_version: Annotated[str, Field(max_length=100)]
    ai_call_id: Id | None = None


class ProductionTranscribed(Event):
    """A recording transcribed by speech recognition (written once: a second one is refused).
    `silence`: no word was heard, or Whisper's segments say silence (nothing is compared then).
    `audio_seconds` is the provider's measure when it gives one, else the recorder's."""

    event_type = EventType.PRODUCTION_TRANSCRIBED
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    kind: ProductionKind
    provider: Annotated[str, Field(max_length=50)]
    model: Annotated[str, Field(max_length=200)]
    ai_call_id: Id | None = None
    status: Literal["ok", "silence"]
    heard_word_count: Annotated[int, Field(ge=0)]
    audio_seconds: Annotated[float, Field(ge=0)] | None = None


class PronunciationChecked(Event):
    """A transcription compared word by word with its target sentence (no text in the payload).
    Speech recognition is not a pronunciation judge: no error is recorded from it."""

    event_type = EventType.PRONUNCIATION_CHECKED
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    target_word_count: Annotated[int, Field(ge=0)]
    recognized_count: Annotated[int, Field(ge=0)]
    unrecognized_count: Annotated[int, Field(ge=0)]
    word_accuracy: Annotated[float, Field(ge=0, le=1)]
    comparator_version: Annotated[str, Field(min_length=1, max_length=50)]
    provider: Annotated[str, Field(max_length=50)]


class PronunciationAssessed(Event):
    """A shadowing take scored by a pronunciation service (Azure, M6.c1). No text in the payload.
    The scores (0-100) are null on `silence`. `audio_seconds` is what the monthly free quota is
    counted on (D-216)."""

    event_type = EventType.PRONUNCIATION_ASSESSED
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    provider: Annotated[str, Field(max_length=50)]
    model: Annotated[str, Field(max_length=200)]
    ai_call_id: Id | None = None
    status: Literal["ok", "silence"]
    audio_seconds: Annotated[float, Field(ge=0)] | None = None
    accuracy: Annotated[float, Field(ge=0, le=100)] | None = None
    fluency: Annotated[float, Field(ge=0, le=100)] | None = None
    completeness: Annotated[float, Field(ge=0, le=100)] | None = None
    pronunciation: Annotated[float, Field(ge=0, le=100)] | None = None
    word_count: Annotated[int, Field(ge=0)] = 0
    mispronounced: Annotated[int, Field(ge=0)] = 0
    omitted: Annotated[int, Field(ge=0)] = 0
    inserted: Annotated[int, Field(ge=0)] = 0


class DrillGenerated(Event):
    """A targeted drill written by the AI and stored (M5.a2)."""

    event_type = EventType.DRILL_GENERATED
    entity_type = "production_attempt"
    entity_id_field = "drill_id"

    drill_id: Id
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    items: Annotated[int, Field(ge=1)]
    provider: Annotated[str, Field(max_length=50)]
    model: Annotated[str, Field(max_length=200)]
    prompt_version: Annotated[str, Field(max_length=100)]
    ai_call_id: Id | None = None


class DrillItemAnswered(Event):
    event_type = EventType.DRILL_ITEM_ANSWERED
    entity_type = "production_attempt"
    entity_id_field = "drill_id"

    drill_id: Id
    index: Annotated[int, Field(ge=0)]
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    outcome: Literal["exact", "wrong", "empty"]
    response_time_ms: Annotated[int, Field(ge=0)]


class DrillCompleted(Event):
    """The last item of a drill was answered."""

    event_type = EventType.DRILL_COMPLETED
    entity_type = "production_attempt"
    entity_id_field = "drill_id"

    drill_id: Id
    category_code: Annotated[str, Field(min_length=1, max_length=200)]
    items: Annotated[int, Field(ge=1)]
    correct: Annotated[int, Field(ge=0)]
    wrong: Annotated[int, Field(ge=0)]
    empty: Annotated[int, Field(ge=0)]


class ErrorRecorded(Event):
    event_type = EventType.ERROR_RECORDED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    category_code: str
    source: ErrorSource
    lexical_item_id: Id | None = None


class ErrorUpdated(Event):
    """An error edited by the user, or moved to its parent category when a proposed category is
    rejected. The old and new codes are always given, so the history of each error's category
    can be rebuilt (M9)."""

    event_type = EventType.ERROR_UPDATED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    source: ErrorSource
    changed: Annotated[list[str], Field(min_length=1)]
    old_category_code: str
    new_category_code: str
    old_lexical_item_id: Id | None = None
    new_lexical_item_id: Id | None = None
    reason: Literal["edit", "category_rejected"] = "edit"


class ErrorDeleted(Event):
    event_type = EventType.ERROR_DELETED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    category_code: str
    source: ErrorSource


class ErrorCardCreated(Event):
    """A term and its card made from an error of the log (M5.a3). `recurrence` is the number of
    identical errors (same wrong form, same correction) the log held at that moment."""

    event_type = EventType.ERROR_CARD_CREATED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    lexical_item_id: Id
    card_id: Id
    deck_id: Id
    category_code: str
    source: ErrorSource
    recurrence: Annotated[int, Field(ge=1)]


class ErrorSuggestionDismissed(Event):
    """The user does not want a card for a recurring error: `key` identifies the pair (see
    `domain/error_cards.pair_key`), `error_event_id` is its latest occurrence at that moment."""

    event_type = EventType.ERROR_SUGGESTION_DISMISSED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    key: Annotated[str, Field(min_length=1, max_length=700)]
    count: Annotated[int, Field(ge=1)]


class ErrorCategoryCreated(Event):
    """A category added by the user (the taxonomy is extensible); it is active at once."""

    event_type = EventType.ERROR_CATEGORY_CREATED
    entity_type = "error_category"
    entity_id_field = "error_category_id"

    error_category_id: Id
    code: str
    parent_code: str | None


class ErrorCategoryProposed(Event):
    """A subcategory proposed by the AI while correcting a production; it waits for the user."""

    event_type = EventType.ERROR_CATEGORY_PROPOSED
    entity_type = "error_category"
    entity_id_field = "error_category_id"

    error_category_id: Id
    code: str
    parent_code: str
    production_attempt_id: Id | None = None


class ErrorCategoryResolved(Event):
    """The user accepted or rejected a proposed category; a rejection moves its errors to the
    parent (one `error.updated` each)."""

    event_type = EventType.ERROR_CATEGORY_RESOLVED
    entity_type = "error_category"
    entity_id_field = "error_category_id"

    error_category_id: Id
    code: str
    parent_code: str
    decision: Literal["accept", "reject"]
    reassigned_errors: Annotated[int, Field(ge=0)]


# --- Sessions and settings ---------------------------------------------------------------------


class SessionStarted(Event):
    event_type = EventType.SESSION_STARTED
    entity_type = "study_session"
    entity_id_field = "study_session_id"

    study_session_id: Id


class SessionEnded(Event):
    event_type = EventType.SESSION_ENDED
    entity_type = "study_session"
    entity_id_field = "study_session_id"

    study_session_id: Id
    duration_seconds: Annotated[float, Field(ge=0)]


class SettingChanged(Event):
    """Only registry keys are accepted, and the registry holds no secret."""

    event_type = EventType.SETTING_CHANGED
    entity_type = "setting"

    key: str
    old_value: Any
    new_value: Any

    @field_validator("key")
    @classmethod
    def key_must_be_a_known_setting(cls, value: str) -> str:
        if value not in SETTINGS:
            raise ValueError(f"unknown setting {value!r} (secrets never go to the event log)")
        return value


class AiCredentialChanged(Event):
    """An API key, the Ollama address or the Azure key and region were saved or removed in `.env`
    (never the value itself)."""

    event_type = EventType.AI_CREDENTIAL_CHANGED
    entity_type = "ai_provider"

    provider: Literal["gemini", "groq", "ollama", "azure"]
    action: Literal["set", "removed"]


EVENT_MODELS: dict[EventType, type[Event]] = {
    model.event_type: model for model in Event.__subclasses__()
}


def parse_event(event_type: str, payload: dict[str, Any]) -> Event:
    """Rebuild a typed event from a stored row (raises on unknown type or invalid payload)."""
    return EVENT_MODELS[EventType(event_type)].model_validate(payload)
