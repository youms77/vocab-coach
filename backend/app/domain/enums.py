"""Closed value sets fixed by the spec (docs/SPEC.md sections 4 and 6).

Pure Python: `db/` imports these to build CHECK constraints; `domain/` never imports `db/`.
Open sets that will grow (exercise type, event type, AI task) are plain strings, not enums.
"""

from enum import StrEnum


class DeckKind(StrEnum):
    CUSTOM = "custom"
    CURRICULUM = "curriculum"
    ERROR_DRILL = "error_drill"


class DeckStatus(StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    PAUSED = "paused"
    DONE = "done"


class ItemType(StrEnum):
    WORD = "word"
    COLLOCATION = "collocation"
    PHRASE = "phrase"
    SPOKEN_FORMULA = "spoken_formula"


class ItemStatus(StrEnum):
    DRAFT = "draft"
    TRIAGE = "triage"
    QUEUED = "queued"
    DISCOVERING = "discovering"
    LEARNING = "learning"
    CONSOLIDATED = "consolidated"
    ACTIVE = "active"
    KNOWN = "known"
    ARCHIVED = "archived"


class EnrichmentStatus(StrEnum):
    COMPLETE = "complete"
    NEEDS_COMPLETION = "needs_completion"


class ContentOrigin(StrEnum):
    AI = "ai"
    USER = "user"
    DEMO = "demo"


class CardDirection(StrEnum):
    RECEPTIVE = "receptive"
    PRODUCTIVE = "productive"


class SrsState(StrEnum):
    # `new` = never reviewed. The fsrs library (6.x) has no New state; the SRS service maps it.
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


class ProductionKind(StrEnum):
    WRITING = "writing"
    SPEAKING = "speaking"
    CONSOLIDATION = "consolidation"
    TRANSCRIPT_ANALYSIS = "transcript_analysis"
    DRILL = "drill"
    SHADOWING = "shadowing"


class Modality(StrEnum):
    WRITTEN = "written"
    ORAL = "oral"


class ConsolidationTaskKind(StrEnum):
    PRESENTATION = "presentation"
    SPEECH = "speech"
    INTERVIEW_ANSWER = "interview_answer"


class ConsolidationTaskStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DONE = "done"
    DISMISSED = "dismissed"


class ErrorCategoryStatus(StrEnum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    REJECTED = "rejected"


class ErrorSource(StrEnum):
    WRITING = "writing"
    SPEAKING = "speaking"
    REVIEW = "review"
    TRANSCRIPT = "transcript"
    MANUAL = "manual"
    DRILL = "drill"
    CONSOLIDATION = "consolidation"


class UnitContentStatus(StrEnum):
    PENDING = "pending"
    GENERATED = "generated"
    EDITED = "edited"


class UnitProgress(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
