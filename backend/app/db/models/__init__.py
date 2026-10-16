"""All models, imported here so `Base.metadata` is complete (Alembic, tests)."""

from app.db.models.curriculum import CurriculumTrack, CurriculumUnit
from app.db.models.errors import ErrorCategory, ErrorEvent
from app.db.models.library import (
    Deck,
    DeckItem,
    Enrichment,
    ExerciseTemplate,
    LexicalItem,
    Source,
)
from app.db.models.production import (
    ConsolidationTask,
    ConsolidationTaskItem,
    ProductionAttempt,
    ProductionTarget,
    PronunciationResult,
)
from app.db.models.srs import Card, ReviewLog
from app.db.models.system import AICallLog, EventLog, Setting, StudySession

__all__ = [
    "AICallLog",
    "Card",
    "ConsolidationTask",
    "ConsolidationTaskItem",
    "CurriculumTrack",
    "CurriculumUnit",
    "Deck",
    "DeckItem",
    "Enrichment",
    "ErrorCategory",
    "ErrorEvent",
    "EventLog",
    "ExerciseTemplate",
    "LexicalItem",
    "ProductionAttempt",
    "ProductionTarget",
    "PronunciationResult",
    "ReviewLog",
    "Setting",
    "Source",
    "StudySession",
]
