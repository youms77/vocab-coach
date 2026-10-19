"""Speaking (module F): shadowing (M6.a1), free speaking and today's speaking topics (M6.a2a),
the transcription and the playback of a recording.

`POST /speech/shadowing` and `POST /speech/speaking` take the **raw recording as the request body**
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
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ai import Gateway, get_gateway
from app.api.clock import NowDep
from app.api.errors import require_database
from app.db.engine import get_engine, get_session
from app.domain.speaking_topics import SpeakingTag, SpeakingTopic
from app.domain.speech_compare import Comparison, Op
from app.domain.speech_rules import (
    DURATION_BOUNDS,
    MAX_AUDIO_BYTES,
    MAX_TARGET_CHARS,
    RecordingKind,
)
from app.domain.topics import DEFAULT_COUNT, MAX_COUNT
from app.services import productions, speaking, speaking_topics, speech
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


def speech_out(result: speech.SpeechResult) -> SpeechOut:
    outcome = result.transcription
    return SpeechOut(
        production_id=result.production_id,
        audio_url=audio_url(result.production_id),
        audio_seconds=result.audio_seconds,
        transcription=TranscriptionOut(
            status=outcome.status, text=outcome.text, reason=outcome.reason
        ),
        comparison=comparison_out(outcome.comparison) if outcome.comparison else None,
    )


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
    return speech_out(result)


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
    return speech_out(result)


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
    return speech_out(result)


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
