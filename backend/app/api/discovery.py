"""Discovery endpoints (module B, M4.a): start, immediate exercises, complete.

1. `start` puts the term in `discovering` and returns the first sentence (never the sheet);
2. the guess is sent with `complete`;
3. the sheet is read with `GET /api/items/{id}/sheet`, which the interface calls after the guess;
4. the immediate exercises come from `GET .../exercises` (prompts only) and are graded by
   `POST /api/reviews/grade` with `item_id`; spoken repetition runs in the browser;
5. `complete` creates both cards without initial ratings (due at the start of the next study day)
   and records the personal sentence. One short transaction; a second call gets 409.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_session
from app.domain.enums import CardDirection, ItemStatus, ItemType
from app.domain.events import DiscoveryExerciseResult
from app.domain.review_steps import build_prompt
from app.services import discovery, library, review_flow, study_sessions

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    deck_id: int | None = None


class SentenceOut(BaseModel):
    text: str
    source: str  # origin | example


class StartOut(BaseModel):
    item_id: int
    term: str
    item_type: ItemType
    status: ItemStatus
    resumed: bool
    sentence: SentenceOut | None


@router.post("/discovery/{item_id}/start", tags=["discovery"])
def start(item_id: int, body: StartRequest, session: SessionDep, now: NowDep) -> StartOut:
    study = study_sessions.require_open(session, body.session_id)
    item = library.get_item(session, item_id)
    deck = library.get_deck(session, body.deck_id) if body.deck_id is not None else None
    started = discovery.begin_discovery(session, item, deck, now, study_session_id=study.id)
    session.commit()
    sentence = started.sentence
    return StartOut(
        item_id=item.id,
        term=item.term,
        item_type=ItemType(item.item_type),
        status=ItemStatus(item.status),
        resumed=started.resumed,
        sentence=SentenceOut(text=sentence.text, source=sentence.source) if sentence else None,
    )


class ExercisePrompt(BaseModel):
    exercise_type: str
    exercise_template_id: int
    prompt: dict[str, Any]


@router.get("/discovery/{item_id}/exercises", tags=["discovery"])
def exercises(item_id: int, session: SessionDep) -> list[ExercisePrompt]:
    """The immediate exercises of step 4 (French -> English recall, gap-fill): one of each type
    the term has, prompts only. Grade them with `POST /api/reviews/grade` and `item_id`."""
    item = review_flow.require_discovering(session, item_id)
    sheet = review_flow.current_sheet_of(session, item.id)
    templates = review_flow.templates_of(session, item.id)
    result = []
    for exercise_type in review_flow.DISCOVERY_EXERCISE_TYPES:
        template = next((t for t in templates if t.exercise_type == exercise_type), None)
        if template is None:
            continue
        result.append(
            ExercisePrompt(
                exercise_type=exercise_type,
                exercise_template_id=template.id,
                prompt=build_prompt(
                    exercise_type,
                    CardDirection.PRODUCTIVE,
                    dict(template.content),
                    term=item.term,
                    origin_sentence=item.origin_sentence,
                    sheet=sheet,
                    seed=review_flow.discovery_seed(item.id),
                ),
            )
        )
    return result


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    duration_ms: Annotated[int, Field(ge=0, le=24 * 3600 * 1000)] | None = None
    guess: Annotated[str, Field(max_length=1000)] | None = None
    exercise_results: Annotated[list[DiscoveryExerciseResult], Field(max_length=10)] = []
    personal_sentence: Annotated[str, Field(max_length=1000)] | None = None


class CardOut(BaseModel):
    card_id: int
    direction: CardDirection
    due: datetime


class CompleteOut(BaseModel):
    item_id: int
    status: ItemStatus
    cards: list[CardOut]
    production_attempt_id: int | None
    warnings: list[str]


@router.post("/discovery/{item_id}/complete", tags=["discovery"])
def complete(item_id: int, body: CompleteRequest, session: SessionDep, now: NowDep) -> CompleteOut:
    study = study_sessions.require_open(session, body.session_id)
    item = library.get_item(session, item_id)
    guess = body.guess.strip() if body.guess and body.guess.strip() else None
    ended = discovery.finish_discovery(
        session,
        item,
        now,
        study_session_id=study.id,
        duration_ms=body.duration_ms,
        guess=guess,
        exercise_results=body.exercise_results,
        personal_sentence=body.personal_sentence,
    )
    session.commit()
    return CompleteOut(
        item_id=item.id,
        status=ItemStatus(item.status),
        cards=[
            CardOut(card_id=card.id, direction=CardDirection(card.direction), due=card.due)
            for card in ended.cards
        ],
        production_attempt_id=ended.production_attempt_id,
        warnings=ended.warnings,
    )
