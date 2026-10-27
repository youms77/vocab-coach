"""Recordings for the speech tests, made in memory: no audio file goes in the repository."""

import io
import math
import struct
import wave

from app.ai.providers.fake import Success
from app.ai.types import SpeechSegment, TranscriptionDetails

TARGET = "We account for regional fixed effects in all specifications."
HEARD = "We account for regional fix effects in all specifications."


def wav_bytes(seconds: float = 1.0, *, rate: int = 8000, tone_hz: float = 440.0) -> bytes:
    """A short mono 16-bit WAV: a sine tone."""
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * tone_hz * i / rate)))
                for i in range(frames)
            )
        )
    return buffer.getvalue()


def heard(
    text: str = HEARD,
    *,
    duration_s: float | None = 3.4,
    segments: tuple[tuple[float, float], ...] = ((0.02, -0.25),),
) -> Success:
    """A Whisper answer as the fake provider plays it: (no_speech_prob, avg_logprob) segments."""
    return Success(
        content=text,
        input_tokens=None,
        output_tokens=None,
        model="whisper-large-v3",
        transcription=TranscriptionDetails(
            duration_s=duration_s,
            segments=tuple(
                SpeechSegment(start=0.0, end=duration_s, no_speech_prob=p, avg_logprob=lp)
                for p, lp in segments
            ),
        ),
    )
