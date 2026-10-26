"""Speaking (module F): shadowing (M6.a1), free speaking, today's speaking topics and the spoken
answer of a review (M6.a2a), the transcription and the playback of a recording.

`POST /speech/shadowing`, `POST /speech/speaking` and `POST /speech/review-answer` take the **raw
recording as the request body**
(`Content-Type` = its media type; no multipart, so no `python-multipart`) and everything else as
query parameters (D-170). An
async dependency reads the body and stops at 10 MB (413 from `Content-Length`, else while
streaming); the routes are plain `def` with **no database session in their dependencies**, so none
is open while the provider answers (D-038). A transcription that fails is a result (200/201 with
`status: unavailable` and `reason`), not an HTTP error (D-081): the recording stays and
`POST /productions/{id}/transcribe` runs it again. Errors use the D-063 format.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.error_log import ErrorOut, errors_out
from app.api.errors import require_database
from app.db.engine import get_engine, get_session
from app.db.models import ErrorEvent
from app.domain import pronunciation as pa
from app.domain.speaking_topics import SpeakingTag, SpeakingTopic
from app.domain.speech_compare import Comparison, Op
from app.domain.speech_rules import (
    DURATION_BOUNDS,
    MAX_AUDIO_BYTES,
    MAX_TARGET_CHARS,
    RecordingKind,
)
from app.domain.topics import DEFAULT_COUNT, MAX_COUNT
from app.services import (
    consolidation_attempts,
    productions,
    pronunciation,
    speaking,
    speaking_topics,
    speech,
    spoken_review,
)
from app.speech.audio_store import (
    ACCEPTED_TYPES,
    AudioStore,
    InvalidAudioPath,
    extension_for,
    get_audio_store,
    served_type,
)

router = APIRouter(dependencies=[Depends(require_database)])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]
EngineDep = Annotated[Engine, Depends(get_engine)]
StoreDep = Annotated[AudioStore, Depends(get_audio_store)]
SessionDep = Annotated[Session, Depends(get_session)]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


def audio_url(production_id: int) -> str:
    return f"/api/productions/{production_id}/audio"


# --- Shapes --------------------------------------------------------------------------------------


class StepOut(BaseModel):
    op: Op
    # Words [target_start, target_end) of the target were heard as [heard_start, heard_end).
    target_start: int
    target_end: int
    heard_start: int
    heard_end: int
    target: str | None
    heard: str | None


class UnrecognizedOut(BaseModel):
    position: int  # index of the word in the target
    word: str
    heard: str | None  # what was heard instead; None when nothing was


class ComparisonOut(BaseModel):
    version: str
    word_accuracy: float  # (match + close) / target words, rounded to 4 decimals
    target_word_count: int
    heard_word_count: int
    recognized_count: int
    unrecognized: list[UnrecognizedOut]
    steps: list[StepOut]


def comparison_out(comparison: Comparison) -> ComparisonOut:
    return ComparisonOut(
        version=comparison.version,
        word_accuracy=round(comparison.word_accuracy, 4),
        target_word_count=comparison.target_word_count,
        heard_word_count=comparison.heard_word_count,
        recognized_count=comparison.recognized_count,
        unrecognized=[
            UnrecognizedOut(position=u.position, word=u.word, heard=u.heard)
            for u in comparison.unrecognized
        ],
        steps=[
            StepOut(
                op=step.op,
                target_start=step.target_start,
                target_end=step.target_end,
                heard_start=step.heard_start,
                heard_end=step.heard_end,
                target=step.target,
                heard=step.heard,
            )
            for step in comparison.steps
        ],
    )


class TranscriptionOut(BaseModel):
    status: Literal["ok", "silence", "unavailable"]
    text: str | None  # `ok` only
    reason: str | None  # `unavailable`: no_provider_configured, quota, network... or incomplete


class SpeechOut(BaseModel):
    production_id: int
    audio_url: str
    audio_seconds: float | None
    transcription: TranscriptionOut
    comparison: ComparisonOut | None
    # Pronunciation assessment (M6.c1): the stored `azure-pa-1` scores (see `/productions`), whether
    # the take can be assessed now and, if not, why (`not_shadowing`, `no_target`, `no_audio`,
    # `disabled`, `not_configured`, `already_assessed`, `unsupported_format`, `too_long`).
    pronunciation: dict[str, Any] | None = None
    assessable: bool = False
    assessable_reason: str | None = None


def speech_out(
    result: speech.SpeechResult, view: pronunciation.AssessmentView | None = None
) -> SpeechOut:
    outcome = result.transcription
    return SpeechOut(
        pronunciation=view.scores if view is not None else None,
        assessable=view.assessable if view is not None else False,
        assessable_reason=view.reason if view is not None else None,
        production_id=result.production_id,
        audio_url=audio_url(result.production_id),
        audio_seconds=result.audio_seconds,
        transcription=TranscriptionOut(
            status=outcome.status, text=outcome.text, reason=outcome.reason
        ),
        comparison=comparison_out(outcome.comparison) if outcome.comparison else None,
    )


def _speech_response(engine: Engine, result: speech.SpeechResult) -> SpeechOut:
    """The speech result with the assessment state of its production, read in a short session."""
    with Session(engine) as session:
        attempt = productions.get_production(session, result.production_id)
        view = pronunciation.assessment_view(session, attempt)
        session.rollback()
    return speech_out(result, view)


# --- Upload --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Upload:
    data: bytes
    content_type: str | None


async def read_upload(request: Request) -> Upload:
    """The raw body, refused early: 415 for a media type that is not accepted, 413 from
    `Content-Length` before reading, or as soon as the streamed body passes the limit."""
    content_type = request.headers.get("content-type")
    if extension_for(content_type) is None:
        raise speech.unsupported_audio()
    declared = request.headers.get("content-length", "").strip()
    if declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        raise speech.audio_too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_AUDIO_BYTES:
            raise speech.audio_too_large()
    return Upload(bytes(body), content_type)


_BINARY: dict[str, Any] = {"schema": {"type": "string", "format": "binary"}}
UPLOAD_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "description": (
            f"The recording itself (at most {MAX_AUDIO_BYTES // 1024 // 1024} MB), with its media "
            "type as Content-Type."
        ),
        "content": dict.fromkeys(ACCEPTED_TYPES, _BINARY),
    }
}


# --- Routes --------------------------------------------------------------------------------------


@router.post("/speech/shadowing", status_code=201, tags=["speech"], openapi_extra=UPLOAD_OPENAPI)
def create_shadowing(
    upload: Annotated[Upload, Depends(read_upload)],
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
    target_text: Annotated[
        str, Query(description=f"The sentence repeated (1 to {MAX_TARGET_CHARS} characters).")
    ],
    duration_s: Annotated[
        float,
        Query(allow_inf_nan=False, description="Duration measured by the recorder, in seconds."),
    ],
    item_id: Annotated[int | None, Query(description="The term worked on, if any.")] = None,
    origin: Literal["shadowing", "discovery"] = "shadowing",
    study_session_id: int | None = None,
) -> SpeechOut:
    """A shadowing recording: stored, then transcribed (Groq Whisper) and compared word by word
    with `target_text`. The target is never sent to the recogniser. Takes a few seconds. Without a
    provider the recording is kept: `transcription.status` is `unavailable`."""
    result = speech.record_shadowing(
        _factory(engine),
        gateway,
        store,
        data=upload.data,
        content_type=upload.content_type,
        target_text=target_text,
        duration_s=duration_s,
        item_id=item_id,
        origin=origin,
        study_session_id=study_session_id,
        clock=lambda: now,
    )
    return _speech_response(engine, result)


_SPEAKING = DURATION_BOUNDS[RecordingKind.SPEAKING]


@router.post("/speech/speaking", status_code=201, tags=["speech"], openapi_extra=UPLOAD_OPENAPI)
def create_speaking(
    upload: Annotated[Upload, Depends(read_upload)],
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
    duration_s: Annotated[
        float,
        Query(
            allow_inf_nan=False,
            description=(
                f"Duration measured by the recorder, in seconds ({_SPEAKING.min_s:g} to "
                f"{_SPEAKING.max_s:g})."
            ),
        ),
    ],
    prompt_text: Annotated[
        str | None,
        Query(description=f"The topic (at most {productions.MAX_PROMPT_CHARS} characters)."),
    ] = None,
    target_item_ids: Annotated[
        list[int] | None,
        Query(description=f"Terms to use, repeated (at most {productions.MAX_TARGETS})."),
    ] = None,
    study_session_id: int | None = None,
) -> SpeechOut:
    """Free speaking on a topic: stored, then transcribed (Groq Whisper). Nothing is corrected
    yet: call `POST /productions/{id}/correct` (the AI correction of a spoken production). The
    topic is never sent to the recogniser. Without a provider the recording is kept:
    `transcription.status` is `unavailable` and `/productions/{id}/transcribe` runs it again."""
    result = speaking.record_speaking(
        _factory(engine),
        gateway,
        store,
        data=upload.data,
        content_type=upload.content_type,
        duration_s=duration_s,
        prompt_text=prompt_text,
        target_item_ids=target_item_ids or [],
        study_session_id=study_session_id,
        clock=lambda: now,
    )
    return _speech_response(engine, result)


_CONSOLIDATION = DURATION_BOUNDS[RecordingKind.CONSOLIDATION]


@router.post(
    "/speech/consolidation", status_code=201, tags=["speech"], openapi_extra=UPLOAD_OPENAPI
)
def create_consolidation_talk(
    upload: Annotated[Upload, Depends(read_upload)],
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
    task_id: int,
    duration_s: Annotated[
        float,
        Query(
            allow_inf_nan=False,
            description=(
                f"Duration measured by the recorder, in seconds ({_CONSOLIDATION.min_s:g} to "
                f"{_CONSOLIDATION.max_s:g})."
            ),
        ),
    ],
    study_session_id: int | None = None,
) -> SpeechOut:
    """The recorded talk of a consolidation task: stored, then transcribed (Groq Whisper). Nothing
    is corrected yet: call `POST /productions/{id}/correct` (it also applies the result to the
    terms of the task). The task prompt is never sent to the recogniser. 404 `task_not_found`, 409
    `task_closed`; the first attempt makes a `proposed` task `accepted`."""
    result = consolidation_attempts.record_spoken(
        _factory(engine),
        gateway,
        store,
        task_id,
        data=upload.data,
        content_type=upload.content_type,
        duration_s=duration_s,
        study_session_id=study_session_id,
        clock=lambda: now,
    )
    return _speech_response(engine, result)


_ANSWER = DURATION_BOUNDS[RecordingKind.SPOKEN_ANSWER]


class ReviewAnswerOut(BaseModel):
    production_attempt_id: int
    transcription: TranscriptionOut
    status: Literal["ok", "incomplete", "unavailable"]
    # Why there is no correction: the transcription's reason (`no_provider_configured`, `quota`,
    # `network`..., `incomplete`), `silence`, `text_too_long`, or the correction's reason.
    reason: str | None
    # The stored correction (`speaking-1`, see `/productions`): corrected units, natural version,
    # structure, notes, target check. None unless `status` is `ok`.
    feedback: dict[str, Any] | None
    errors: list[ErrorOut]  # source `review`
    proposed_rating: int | None  # 1 (Again) or 3 (Good); None: rate it yourself
    warnings: list[str]  # `term_not_heard`: the term is not in the transcription, no rating
    solution: dict[str, Any]  # the example answer, shown now that the attempt was made (D-103)
    sheet_summary: dict[str, Any] | None


@router.post("/speech/review-answer", tags=["speech"], openapi_extra=UPLOAD_OPENAPI)
def review_answer(
    upload: Annotated[Upload, Depends(read_upload)],
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
    card_id: int,
    session_id: int,
    exercise_template_id: int,
    duration_s: Annotated[
        float,
        Query(
            allow_inf_nan=False,
            description=(
                f"Duration measured by the recorder, in seconds ({_ANSWER.min_s:g} to "
                f"{_ANSWER.max_s:g})."
            ),
        ),
    ],
    response_time_ms: Annotated[
        int, Query(ge=0, description="Kept for the final `POST /reviews`, which times the card.")
    ],
) -> ReviewAnswerOut:
    """Check the spoken answer of a `spoken_answer` card: the recording is stored, transcribed
    (Groq Whisper) and corrected (`speaking_correction`, `answer` mode), and a rating is proposed.
    Two AI calls: allow up to about a minute and a half. Then send `production_attempt_id` with
    `POST /api/reviews`. Refusals come before anything is stored. A failed transcription keeps the
    recording (`status: unavailable`): rate it yourself."""
    factory = _factory(engine)
    checked = spoken_review.check_spoken_answer(
        factory,
        gateway,
        store,
        card_id=card_id,
        study_session_id=session_id,
        exercise_template_id=exercise_template_id,
        data=upload.data,
        content_type=upload.content_type,
        duration_s=duration_s,
        clock=lambda: now,
    )
    heard = checked.transcription
    with factory() as session:
        attempt = productions.get_production(session, checked.production_id)
        feedback = (
            dict(attempt.ai_feedback)
            if checked.status == "ok" and attempt.ai_feedback is not None
            else None
        )
        ids = checked.correction.error_ids if checked.correction is not None else []
        errors = list(
            session.scalars(
                select(ErrorEvent).where(ErrorEvent.id.in_(ids)).order_by(ErrorEvent.id)
            )
        )
        errors_listed = errors_out(session, errors)
        session.rollback()
    return ReviewAnswerOut(
        production_attempt_id=checked.production_id,
        transcription=TranscriptionOut(status=heard.status, text=heard.text, reason=heard.reason),
        status=checked.status,
        reason=checked.reason,
        feedback=feedback,
        errors=errors_listed,
        proposed_rating=checked.proposed_rating,
        warnings=checked.warnings,
        solution=checked.solution,
        sheet_summary=checked.sheet_summary,
    )


@router.get("/speaking/topics", tags=["speech"])
def topics(
    session: SessionDep,
    now: NowDep,
    count: Annotated[int, Query(ge=1, le=MAX_COUNT)] = DEFAULT_COUNT,
    tag: SpeakingTag | None = None,
) -> list[SpeakingTopic]:
    """Today's speaking topics (`{id, en, fr, tags}`): the same all day, different the next day,
    never a topic used as a spoken prompt in the last 7 days (unless every topic of the tag
    was). No AI call."""
    return speaking_topics.todays_topics(session, now, count=count, tag=tag)


@router.post("/productions/{production_id}/transcribe", tags=["speech"])
def transcribe(
    production_id: int,
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
) -> SpeechOut:
    """Run the transcription again for a recording that has none yet. 409 `already_transcribed`;
    422 `no_audio` for a production without a recording (or whose file is gone)."""
    result = speech.transcribe_production(
        _factory(engine), gateway, store, production_id, clock=lambda: now
    )
    return _speech_response(engine, result)


class PronunciationOut(BaseModel):
    production_id: int
    # `ok` / `silence`: scored; `unavailable` (see `reason`: no_provider_configured, quota, auth,
    # network...) or `incomplete`: nothing stored, the call can be repeated (D-081).
    status: Literal["ok", "silence", "unavailable", "incomplete"]
    reason: str | None
    scores: dict[str, Any] | None  # `azure-pa-1`, see `/productions`


@router.post("/productions/{production_id}/pronunciation", tags=["speech"])
def assess_pronunciation(
    production_id: int,
    engine: EngineDep,
    gateway: GatewayDep,
    store: StoreDep,
    now: NowDep,
) -> PronunciationOut:
    """Score a stored shadowing with Azure (word by word, phoneme by phoneme). The recording is
    sent to Microsoft. Takes a few seconds. Refusals, before any call: 404 `production_not_found`,
    422 `not_assessable`, 404 `no_audio`, 409 `assessment_disabled`, 409 `already_assessed`,
    422 `unsupported_for_assessment` (Azure reads WAV 16 kHz mono or OGG Opus only), 422
    `audio_too_long` (30 s at most). An AI failure is a 200 with `status: unavailable`."""
    outcome = pronunciation.assess(
        _factory(engine), gateway, store, production_id, clock=lambda: now
    )
    return PronunciationOut(
        production_id=production_id,
        status=outcome.status,
        reason=outcome.reason,
        scores=outcome.scores,
    )


class PronunciationUsageOut(BaseModel):
    month: str  # "YYYY-MM", UTC
    audio_seconds: float
    assessments: int
    limit_seconds: int  # the free F0 tier: 5 hours a month
    limit_checked_on: str  # the day the limit was read on Microsoft Learn
    note: str


@router.get("/speech/pronunciation/usage", tags=["speech"])
def pronunciation_usage(engine: EngineDep, now: NowDep) -> PronunciationUsageOut:
    """What this app sent to Azure this calendar month (UTC), from the `pronunciation.assessed`
    events: silence counts, failed requests do not. It is not what Microsoft counts."""
    with Session(engine) as session:
        session.execute(text("PRAGMA query_only = ON"))
        try:
            usage = pronunciation.monthly_usage(session, now)
        finally:
            session.rollback()
            # The connection goes back to the pool: leave it writable for the next request.
            session.execute(text("PRAGMA query_only = OFF"))
            session.rollback()
    return PronunciationUsageOut(
        month=usage.month,
        audio_seconds=usage.audio_seconds,
        assessments=usage.assessments,
        limit_seconds=pa.F0_MONTHLY_AUDIO_SECONDS,
        limit_checked_on=pa.F0_LIMIT_CHECKED_ON,
        note=pronunciation.NOTE,
    )


@router.get(
    "/productions/{production_id}/audio",
    tags=["speech"],
    response_class=FileResponse,
    responses={200: {"content": dict.fromkeys(ACCEPTED_TYPES, _BINARY)}},
)
def get_audio(production_id: int, engine: EngineDep, store: StoreDep) -> FileResponse:
    """The recording, streamed (HTTP `Range` requests are answered, so a player can seek). 404
    `no_audio` when the production has no recording or its file is gone."""
    with Session(engine) as session:
        audio_path = productions.get_production(session, production_id).audio_path
    if not audio_path:
        raise speech.AudioMissing("This production has no recording.")
    try:
        path = store.resolve(audio_path)
    except InvalidAudioPath as exc:
        raise speech.AudioMissing("The recording file is missing.") from exc
    if not path.is_file():
        raise speech.AudioMissing("The recording file is missing.")
    return FileResponse(path, media_type=served_type(audio_path))
