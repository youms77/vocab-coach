"""Event catalogue for the shared `event_log` (docs/SPEC.md section 5). Pure Python.

Every business change writes one of these events. Statistics read them, so a payload is a contract:
fields are validated (`extra="forbid"`), and a breaking change bumps `payload_version`.
Later modules add event types here.
"""

from enum import StrEnum
from typing import Annotated, Any, ClassVar

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
    ITEM_CREATED = "item.created"
    ITEM_STATUS_CHANGED = "item.status_changed"
    ITEM_TRIAGED = "item.triaged"
    ITEM_MERGED = "item.merged"
    ENRICHMENT_GENERATED = "enrichment.generated"
    ENRICHMENT_EDITED = "enrichment.edited"
    DISCOVERY_COMPLETED = "discovery.completed"
    CARD_CREATED = "card.created"
    CARD_REVIEWED = "card.reviewed"
    PRODUCTION_RECORDED = "production.recorded"
    ERROR_RECORDED = "error.recorded"
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SETTING_CHANGED = "setting.changed"


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


class EnrichmentEdited(Event):
    event_type = EventType.ENRICHMENT_EDITED
    entity_type = "enrichment"
    entity_id_field = "enrichment_id"

    enrichment_id: Id
    lexical_item_id: Id


class DiscoveryCompleted(Event):
    event_type = EventType.DISCOVERY_COMPLETED
    entity_type = "lexical_item"
    entity_id_field = "lexical_item_id"

    lexical_item_id: Id
    duration_ms: Annotated[int, Field(ge=0)] | None = None


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


class ProductionRecorded(Event):
    event_type = EventType.PRODUCTION_RECORDED
    entity_type = "production_attempt"
    entity_id_field = "production_attempt_id"

    production_attempt_id: Id
    kind: ProductionKind
    modality: Modality
    word_count: Annotated[int, Field(ge=0)]
    audio_seconds: Annotated[float, Field(ge=0)] | None = None


class ErrorRecorded(Event):
    event_type = EventType.ERROR_RECORDED
    entity_type = "error_event"
    entity_id_field = "error_event_id"

    error_event_id: Id
    category_code: str
    source: ErrorSource
    lexical_item_id: Id | None = None


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


EVENT_MODELS: dict[EventType, type[Event]] = {
    model.event_type: model for model in Event.__subclasses__()
}


def parse_event(event_type: str, payload: dict[str, Any]) -> Event:
    """Rebuild a typed event from a stored row (raises on unknown type or invalid payload)."""
    return EVENT_MODELS[EventType(event_type)].model_validate(payload)
