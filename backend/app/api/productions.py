"""Productions and their AI correction (module E, M5.a1). Spoken productions are recorded, played
and transcribed through `app/api/speech.py` (M6.a1); they are read here like the others.

`POST /productions/{id}/correct` calls the AI, so it is a plain `def` route with **no database
session in its dependencies**: the service opens short sessions itself and none is open while the
provider answers (D-038). An AI failure is not an HTTP error: the answer is 200 with `status`
(`incomplete` or `unavailable`) and `reason`, and the production stays uncorrected (D-081).
Errors use the D-063 format.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.error_log import ErrorOut, errors_out
from app.api.errors import require_database
from app.api.speech import ComparisonOut, audio_url, comparison_out
from app.db.engine import get_engine, get_session
from app.db.models import ErrorCategory, ErrorEvent, ProductionAttempt
from app.domain.enums import Modality, ProductionKind
from app.domain.events import ProductionOrigin
from app.domain.transcript_import import MAX_PASTED_CHARS, UserByLabel, UserByMode
from app.services import corrections, productions, pronunciation, speaking, speech, transcripts

router = APIRouter(dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


# --- Shapes --------------------------------------------------------------------------------------


class TargetOut(BaseModel):
    lexical_item_id: int
    term: str
    used: bool | None  # contains_term on the text; None until corrected
    used_correctly: bool | None  # from the AI check


class ProductionOut(BaseModel):
    id: int
    kind: ProductionKind
    modality: Modality
    prompt_text: str | None
    text: str
    word_count: int
    corrected: bool
    # `format: "correction-1"`: `output` (the AI's validated answer), `spans` (position of each
    # `wrong` in `text`, Unicode code points), `error_event_ids` (same order as `output.errors`),
    # `targets` (checks and disagreements), `prompt_version`, `provider`, `model`. A transcript
    # has `format: "transcript-1"` with the same keys (units as `sentences`), a spoken production
    # `format: "speaking-1"` with the same keys and `output.structure`; a drill has none here
    # (read it with `/api/drills/{id}`).
    feedback: dict[str, Any] | None
    ai_call_id: int | None
    study_session_id: int | None
    targets: list[TargetOut]
    created_at: datetime
    updated_at: datetime
    # Spoken productions (M6.a1). `audio_url` streams the recording; `transcription_status` is
    # `pending` (to transcribe again), `ok` or `silence`, null without a recording; `comparison`
    # is the word-by-word comparison of a transcribed shadowing, computed again on each read.
    audio_url: str | None = None
    audio_seconds: float | None = None
    transcription_status: Literal["pending", "ok", "silence"] | None = None
    comparison: ComparisonOut | None = None
    # Pronunciation assessment (M6.c1): the stored scores (`format: "azure-pa-1"`: `provider`,
    # `model`, `assessed_at`, `status` ok|silence, `overall` {accuracy, fluency, completeness,
    # pronunciation}, `words` [{word, accuracy, error_type, offset_ms, duration_ms, phonemes
    # [{phoneme, accuracy}]}], `duration_s`); whether the take can be assessed now and, if not,
    # why (`not_shadowing`, `no_target`, `no_audio`, `disabled`, `not_configured`,
    # `already_assessed`, `unsupported_format`, `too_long`).
    pronunciation: dict[str, Any] | None = None
    assessable: bool = False
    assessable_reason: str | None = None


def production_out(session: Session, attempt: ProductionAttempt) -> ProductionOut:
    comparison = speech.comparison_of(session, attempt)
    view = pronunciation.assessment_view(session, attempt)
    return ProductionOut(
        pronunciation=view.scores,
        assessable=view.assessable,
        assessable_reason=view.reason,
        id=attempt.id,
        kind=attempt.kind,
        modality=attempt.modality,
        prompt_text=attempt.prompt_text,
        text=attempt.text,
        word_count=attempt.word_count,
        corrected=attempt.ai_feedback is not None and attempt.kind is not ProductionKind.DRILL,
        # A drill's feedback holds its solutions: it is read through /api/drills (D-103).
        feedback=dict(attempt.ai_feedback)
        if attempt.ai_feedback is not None and attempt.kind is not ProductionKind.DRILL
        else None,
        ai_call_id=attempt.ai_call_id,
        study_session_id=attempt.study_session_id,
        targets=[
            TargetOut(
                lexical_item_id=item.id,
                term=item.term,
                used=target.used,
                used_correctly=target.used_correctly,
            )
            for target, item in productions.targets_of(session, attempt.id)
        ],
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        audio_url=audio_url(attempt.id) if attempt.audio_path else None,
        audio_seconds=attempt.audio_seconds,
        transcription_status=speech.transcription_state(session, attempt),
        comparison=comparison_out(comparison) if comparison is not None else None,
    )


class ProposedCategoryOut(BaseModel):
    id: int
    code: str
    parent_code: str
    label_en: str
    label_fr: str
    description_en: str
    status: str


# --- Create and read -----------------------------------------------------------------------------


class WritingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["writing"] = "writing"
    text: Annotated[str, Field(min_length=1, max_length=productions.MAX_TEXT_CHARS)]
    prompt: Annotated[str, Field(max_length=productions.MAX_PROMPT_CHARS)] | None = None
    target_item_ids: Annotated[list[int], Field(max_length=productions.MAX_TARGETS)] = []
    study_session_id: int | None = None


@router.post("/productions", status_code=201, tags=["productions"])
def create_production(body: WritingRequest, session: SessionDep, now: NowDep) -> ProductionOut:
    """A free-writing paragraph. Nothing is corrected yet: call `/productions/{id}/correct`."""
    attempt = productions.create_writing(
        session,
        text=body.text,
        prompt=body.prompt,
        target_item_ids=body.target_item_ids,
        study_session_id=body.study_session_id,
        at=now,
        origin=ProductionOrigin.WRITING,
    )
    session.commit()
    return production_out(session, attempt)


class ProductionPageOut(BaseModel):
    items: list[ProductionOut]
    total: int
    limit: int
    offset: int


@router.get("/productions", tags=["productions"])
def list_productions(
    session: SessionDep,
    kind: ProductionKind | None = None,
    limit: Annotated[int, Query(ge=1, le=productions.MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductionPageOut:
    """Newest first."""
    page, total = productions.list_productions(session, kind=kind, limit=limit, offset=offset)
    return ProductionPageOut(
        items=[production_out(session, attempt) for attempt in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/productions/{production_id}", tags=["productions"])
def get_production(production_id: int, session: SessionDep) -> ProductionOut:
    return production_out(session, productions.get_production(session, production_id))


# --- Correction ----------------------------------------------------------------------------------


class CorrectionOut(BaseModel):
    status: Literal["ok", "incomplete", "unavailable"]
    reason: str | None  # why the AI was unavailable (no_provider_configured, quota, network...)
    attempt: ProductionOut
    errors: list[ErrorOut]
    proposed_categories: list[ProposedCategoryOut]  # new categories waiting for your decision


def correction_out(session: Session, result: corrections.CorrectionResult) -> CorrectionOut:
    attempt = productions.get_production(session, result.attempt_id)
    errors = list(
        session.scalars(
            select(ErrorEvent).where(ErrorEvent.id.in_(result.error_ids)).order_by(ErrorEvent.id)
        )
    )
    proposed = list(
        session.scalars(
            select(ErrorCategory)
            .where(ErrorCategory.id.in_(result.proposed_category_ids))
            .order_by(ErrorCategory.id)
        )
    )
    parents = {
        c.id: c.code
        for c in session.scalars(
            select(ErrorCategory).where(ErrorCategory.id.in_([c.parent_id for c in proposed]))
        )
    }
    return CorrectionOut(
        status=result.status,
        reason=str(result.reason) if result.reason is not None else None,
        attempt=production_out(session, attempt),
        errors=errors_out(session, errors),
        proposed_categories=[
            ProposedCategoryOut(
                id=c.id,
                code=c.code,
                parent_code=parents.get(c.parent_id, ""),
                label_en=c.label_en,
                label_fr=c.label_fr,
                description_en=c.description_en,
                status=str(c.status),
            )
            for c in proposed
        ],
    )


class TranscriptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=2 * MAX_PASTED_CHARS)]
    user: UserByLabel | UserByMode


class CorrectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A transcript only: the pasted text again, so the AI gets the other speaker's turns as
    # context (they are never stored). Without it, the units are checked without context.
    transcript: TranscriptBody | None = None


@router.post("/productions/{production_id}/correct", tags=["productions"])
def correct(
    production_id: int,
    engine: EngineDep,
    gateway: GatewayDep,
    now: NowDep,
    body: CorrectRequest | None = None,
) -> CorrectionOut:
    """Correct a production with the AI: its errors are classified and logged. Takes a few
    seconds (a long transcript, several calls). A written production uses `production_correction`,
    a transcript `transcript_analysis`, a spoken production `speaking_correction` (409
    `not_transcribed` before its transcription, 422 `nothing_to_correct` for silence); other kinds
    get 422 `not_correctable`. 409 `already_corrected` when it was corrected before; with `status`
    `unavailable` or `incomplete` nothing was written and you can try again."""
    factory = _factory(engine)
    with factory() as session:
        kind = productions.get_production(session, production_id).kind
    transcript = body.transcript if body is not None else None
    if kind is ProductionKind.TRANSCRIPT_ANALYSIS:
        result = transcripts.analyse_transcript(
            factory,
            gateway,
            production_id,
            source=transcripts.TranscriptSource(transcript.text, transcript.user)
            if transcript is not None
            else None,
            clock=lambda: now,
        )
    elif transcript is not None:
        raise transcripts.NotATranscript("Only a transcript takes a transcript body.")
    elif kind is ProductionKind.SPEAKING:
        result = speaking.correct_speaking(factory, gateway, production_id, clock=lambda: now)
    else:
        result = corrections.correct_production(
            factory,
            gateway,
            production_id,
            clock=lambda: now,
        )
    with Session(engine) as session:
        return correction_out(session, result)
