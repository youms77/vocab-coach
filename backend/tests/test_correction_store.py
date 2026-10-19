"""The write step shared by written and spoken corrections (`corrections._store`, M6.a2a):
`store_correction` (correction-1) and `store_speaking_correction` (speaking-1), and
`production.corrected` version 2 with the production's kind."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas.production_correction import ProductionCorrectionOutput
from app.ai.schemas.speaking_correction import SpeakingCorrectionOutput, speaking_context
from app.ai.schemas.transcript_analysis import TranscriptAnalysisOutput
from app.db.models import ErrorEvent, EventLog, ProductionAttempt
from app.db.taxonomy import sync_taxonomy
from app.domain.enums import ErrorSource, Modality, ProductionKind
from app.domain.speech_rules import speech_units
from app.domain.transcript_import import UserByLabel
from app.services import corrections, transcripts
from app.services.productions import record_written_production
from tests.correction_support import PARAGRAPH, correction_output
from tests.library_support import events
from tests.speaking_support import CODES, SPEECH, UNITS, speaking_output
from tests.transcript_support import EXAMPLE_TURNS, example_output

RECORDED = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
CORRECTED = RECORDED + timedelta(minutes=5)


def _spoken(session: Session) -> ProductionAttempt:
    attempt = ProductionAttempt(
        kind=ProductionKind.SPEAKING,
        modality=Modality.ORAL,
        prompt_text="Describe where you study and for how long.",
        text=SPEECH,
        audio_path="2026/10/" + "a" * 32 + ".wav",
        audio_seconds=40.0,
        word_count=60,
        created_at=RECORDED,
        updated_at=RECORDED,
    )
    session.add(attempt)
    session.flush()
    return attempt


def _store(session: Session, attempt: ProductionAttempt) -> corrections.Written:
    prepared = corrections.Prepared(
        attempt_id=attempt.id,
        text=attempt.text,
        prompt=attempt.prompt_text or "",
        source=ErrorSource.SPEAKING,
        sentences=speech_units(attempt.text),
        targets=[],
        taxonomy={},
    )
    output = SpeakingCorrectionOutput.model_validate(
        speaking_output(), context=speaking_context(UNITS, CODES, set(), "monologue", SPEECH)
    )
    return corrections.store_speaking_correction(
        session,
        prepared,
        output,
        source=ErrorSource.SPEAKING,
        provenance=("fake", "fake-model", "speaking_correction.v1"),
        ai_call_id=None,
        at=CORRECTED,
    )


def test_a_spoken_correction_has_the_written_keys_and_its_structure(session: Session) -> None:
    sync_taxonomy(session)
    attempt = _spoken(session)
    written = _store(session, attempt)

    feedback = attempt.ai_feedback
    assert feedback is not None
    assert feedback["format"] == "speaking-1"
    assert set(feedback) == {
        "format",
        "prompt_version",
        "provider",
        "model",
        "output",
        "spans",
        "error_event_ids",
        "targets",
    }
    assert feedback["output"]["structure"]["connectors_used"] == ["so", "and"]
    assert feedback["error_event_ids"] == written.error_ids
    # Spans are code points into the transcription, through the units' offsets.
    assert [SPEECH[s["start"] : s["end"]] for s in feedback["spans"]] == [
        "in campus",
        "study here since two years",
        "I never presented",
    ]
    errors = session.scalars(select(ErrorEvent).order_by(ErrorEvent.id)).all()
    assert [e.source for e in errors] == [ErrorSource.SPEAKING] * 3
    assert [e.original_text for e in errors] == [UNITS[1], UNITS[2], UNITS[4]]
    # The errors were made when the learner spoke, not when the AI answered.
    assert {e.occurred_at.replace(tzinfo=UTC) for e in errors} == {RECORDED}
    [corrected] = events(session, "production.corrected")
    assert corrected["kind"] == "speaking" and corrected["sentence_count"] == 4
    assert corrected["word_count"] == 60 and corrected["error_count"] == 3


def test_production_corrected_is_version_2(session: Session) -> None:
    sync_taxonomy(session)
    _store(session, _spoken(session))
    row = session.scalars(
        select(EventLog).where(EventLog.event_type == "production.corrected")
    ).one()
    assert row.payload_version == 2


def test_written_and_transcript_corrections_carry_their_kind(session: Session) -> None:
    sync_taxonomy(session)
    attempt = record_written_production(
        session, text=PARAGRAPH, prompt=None, targets={}, at=RECORDED
    )
    prepared = corrections.prepare(session, attempt.id)
    output = ProductionCorrectionOutput.model_validate(correction_output())
    written = corrections.store_correction(
        session,
        prepared,
        output,
        source=ErrorSource.WRITING,
        provenance=("fake", "fake-model", "production_correction.v1"),
        ai_call_id=None,
        at=CORRECTED,
    )
    assert attempt.ai_feedback is not None and attempt.ai_feedback["format"] == "correction-1"
    # A written error is dated at its correction, as before.
    first = session.get(ErrorEvent, written.error_ids[0])
    assert first is not None and first.occurred_at.replace(tzinfo=UTC) == CORRECTED

    analysed = transcripts.record_transcript(
        session,
        text="\n\n".join(f"You: {turn}\n\nTutor: Okay." for turn in EXAMPLE_TURNS),
        user=UserByLabel(label="You"),
        title=None,
        occurred_on=None,
        study_session_id=None,
        at=RECORDED,
    )
    ready = transcripts.prepare(session, analysed.id, None)
    chunk = transcripts.ChunkResult(
        output=TranscriptAnalysisOutput.model_validate(example_output()),
        provider="fake",
        model="fake-model",
        prompt_version="transcript_analysis.v1",
        call_id=None,
        units=ready.units,
    )
    transcripts.store_analysis(session, ready, [chunk], at=CORRECTED)
    kinds = [payload["kind"] for payload in events(session, "production.corrected")]
    assert kinds == ["writing", "transcript_analysis"]
