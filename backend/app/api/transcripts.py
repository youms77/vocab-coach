"""Pasted conversation transcripts (module E, M5.a2).

`POST /transcripts/preview` parses and writes nothing (it does not even open a session).
`POST /transcripts` stores the user's turns only, as a `transcript_analysis` production; the
analysis is `POST /productions/{id}/correct` (see `app/api/productions.py`). Errors use the D-063
format.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.clock import NowDep
from app.api.errors import require_database
from app.api.productions import ProductionOut, production_out
from app.db.engine import get_session
from app.domain.transcript_import import (
    MAX_PASTED_CHARS,
    LabelCount,
    TranscriptProblem,
    Turn,
    UserByLabel,
    UserByMode,
    parse_transcript,
)
from app.services import transcripts

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
# A hard cap on the request; the parser refuses more than MAX_PASTED_CHARS with `too_large`.
PastedText = Annotated[str, Field(min_length=1, max_length=2 * MAX_PASTED_CHARS)]


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PastedText
    user: UserByLabel | UserByMode | None = None  # default: the suggested label


class UserSpeechOut(BaseModel):
    turns: int
    words: int
    chars: int


class PreviewOut(BaseModel):
    turns: list[Turn]  # `is_user` is null when no user could be designated
    labels: list[LabelCount]  # turns, words and characters per label
    labelled: bool
    suggested_user_label: str | None
    designation: UserByLabel | UserByMode | None  # what was applied
    user: UserSpeechOut | None
    problems: list[TranscriptProblem]


@router.post("/transcripts/preview", tags=["transcripts"])
def preview(body: PreviewRequest) -> PreviewOut:
    """Show the turns, the labels and the problems of a pasted transcript. Writes nothing."""
    parsed = parse_transcript(body.text, body.user)
    return PreviewOut(
        turns=parsed.turns,
        labels=parsed.labels,
        labelled=parsed.labelled,
        suggested_user_label=parsed.suggested_user_label,
        designation=parsed.designation,
        user=UserSpeechOut(
            turns=len(parsed.user_turns), words=parsed.user_words, chars=parsed.user_chars
        )
        if parsed.designation is not None
        else None,
        problems=parsed.problems,
    )


class TranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PastedText
    user: UserByLabel | UserByMode
    title: Annotated[str, Field(max_length=transcripts.MAX_TITLE_CHARS)] | None = None
    occurred_on: date | None = None  # the day of the conversation (default: today)
    study_session_id: int | None = None


@router.post(
    "/transcripts",
    status_code=201,
    tags=["transcripts"],
    dependencies=[Depends(require_database)],
)
def create_transcript(body: TranscriptRequest, session: SessionDep, now: NowDep) -> ProductionOut:
    """Store your turns of a transcript (only them). Nothing is analysed yet: call
    `/productions/{id}/correct`, sending the transcript again to give the AI the context."""
    attempt = transcripts.record_transcript(
        session,
        text=body.text,
        user=body.user,
        title=body.title,
        occurred_on=body.occurred_on,
        study_session_id=body.study_session_id,
        at=now,
    )
    session.commit()
    return production_out(session, attempt)
