"""Short WAV clips for the demo's recordings, made with `wave` (D-190).

No audio file is in the repository: the demo writes these clips into `audio-demo/` when it is
seeded. Each lasts about one second, whatever the duration the production declares (a free speech
of 90 s plays a one-second tone): the demo shows that playback works, not what was said.
"""

import io
import math
import struct
import wave
from functools import cache

RATE = 8000
SECONDS = 1.0
CONTENT_TYPE = "audio/wav"
_TONE_HZ = 330.0
_AMPLITUDE = 3000
_FADE_S = 0.1


def _wav(samples: list[int]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(RATE)
        clip.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buffer.getvalue()


@cache
def tone() -> bytes:
    """About one second of a soft tone, faded in and out (a recording with speech)."""
    frames = int(SECONDS * RATE)
    fade = int(_FADE_S * RATE)
    samples = []
    for i in range(frames):
        envelope = min(1.0, i / fade, (frames - 1 - i) / fade)
        samples.append(round(_AMPLITUDE * envelope * math.sin(2 * math.pi * _TONE_HZ * i / RATE)))
    return _wav(samples)


@cache
def silence() -> bytes:
    """About one second of silence (a take where nothing was said)."""
    return _wav([0] * int(SECONDS * RATE))
