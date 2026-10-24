"""Pronunciation assessment, pure parts (module F, optional Azure tier). No I/O.

Azure AI Speech scores a recording against its reference text, word by word and phoneme by
phoneme. This module holds what does not need the network: the check that a clip is in a format
Azure reads, the dated limits, the summary counters and the stored `azure-pa-1` document.

Facts read on Microsoft Learn on 2026-10-24 (sources in D-211): the short-audio REST API takes only
WAV PCM 16 kHz mono and OGG Opus (webm, m4a and mp3 are refused); 30 s at most when pronunciation
assessment is on; the free F0 tier gives 5 audio hours a month and one concurrent request.
"""

import struct
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

FORMAT = "azure-pa-1"
UNSUPPORTED_FOR_ASSESSMENT = "unsupported_for_assessment"

MAX_ASSESSMENT_SECONDS = 30.0
F0_MONTHLY_AUDIO_SECONDS = 18_000  # 5 hours
F0_LIMIT_CHECKED_ON = "2026-10-24"

WAV_SAMPLE_RATE = 16_000
_OPUS_RATE = 48_000  # Ogg Opus granule positions always count 48 kHz samples
_WAVE_FORMAT_PCM = 1

# Error types Azure documents for a word; any other value is stored as is and counted nowhere.
MISPRONUNCIATION = "Mispronunciation"
OMISSION = "Omission"
INSERTION = "Insertion"


def audio_kind(data: bytes, extension: str = "") -> str | None:
    """`"wav"` or `"ogg"` when `data` is a clip Azure reads, else None. The content decides; the
    extension only has to agree (a `.wav` that holds webm is refused, a `.webm` that holds WAV is
    read as WAV by Azure anyway, but the stored name would mislead, so it is refused too)."""
    kind = _wav_kind(data) or _ogg_kind(data)
    if kind is None:
        return None
    ext = extension.lower().lstrip(".")
    if ext and ext != kind and not (kind == "ogg" and ext in ("opus", "oga")):
        return None
    return kind


def audio_problem(data: bytes, extension: str = "") -> str | None:
    """None when Azure can read the clip, else `unsupported_for_assessment`."""
    return None if audio_kind(data, extension) is not None else UNSUPPORTED_FOR_ASSESSMENT


def audio_duration_s(data: bytes) -> float | None:
    """Duration of a WAV or Ogg Opus clip from its headers, or None when it cannot be told."""
    if _wav_kind(data):
        audio_bytes = _wav_info(data)
        return None if audio_bytes is None else audio_bytes / (WAV_SAMPLE_RATE * 2)
    if _ogg_kind(data):
        return _ogg_duration(data)
    return None


def _chunks(data: bytes) -> Sequence[tuple[bytes, int, int]]:
    """RIFF chunks as (id, start of body, declared size), read until the data runs out."""
    found = []
    position = 12
    while position + 8 <= len(data):
        chunk_id = data[position : position + 4]
        (size,) = struct.unpack_from("<I", data, position + 4)
        found.append((chunk_id, position + 8, size))
        if chunk_id == b"data":
            break
        position += 8 + size + (size & 1)
    return found


def _wav_info(data: bytes) -> int | None:
    """Bytes of audio of a PCM 16 kHz mono 16-bit WAV, else None."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    fmt_ok = False
    for chunk_id, start, size in _chunks(data):
        if chunk_id == b"fmt " and size >= 16 and start + 16 <= len(data):
            tag, channels, rate, _byte_rate, _align, bits = struct.unpack_from(
                "<HHIIHH", data, start
            )
            fmt_ok = (
                tag == _WAVE_FORMAT_PCM and channels == 1 and rate == WAV_SAMPLE_RATE and bits == 16
            )
        elif chunk_id == b"data":
            if not fmt_ok:
                return None
            # A streamed file may declare 0 or 0xFFFFFFFF: trust what is really there.
            available = len(data) - start
            return min(size, available) if 0 < size < 0xFFFFFFFF else available
    return None


def _wav_kind(data: bytes) -> str | None:
    return "wav" if _wav_info(data) is not None else None


def _opus_head(data: bytes) -> tuple[int, int] | None:
    """(channels, pre-skip) from the OpusHead packet of the first Ogg page, or None."""
    if data[:4] != b"OggS":
        return None
    index = data.find(b"OpusHead", 0, 512)
    if index < 0 or index + 12 > len(data):
        return None
    channels = data[index + 9]
    (pre_skip,) = struct.unpack_from("<H", data, index + 10)
    return channels, pre_skip


def _ogg_kind(data: bytes) -> str | None:
    head = _opus_head(data)
    return "ogg" if head is not None and head[0] == 1 else None


def _ogg_duration(data: bytes) -> float | None:
    head = _opus_head(data)
    if head is None:
        return None
    last = data.rfind(b"OggS")
    if last < 0 or last + 14 > len(data):
        return None
    (granule,) = struct.unpack_from("<q", data, last + 6)
    if granule < 0:
        return None
    return max(granule - head[1], 0) / _OPUS_RATE


# --- Results ----------------------------------------------------------------------------------


def summarize(words: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Counts of mispronounced, omitted and inserted words (other error types count nowhere)."""
    errors = [word.get("error_type") for word in words]
    return {
        "mispronounced": errors.count(MISPRONUNCIATION),
        "omitted": errors.count(OMISSION),
        "inserted": errors.count(INSERTION),
    }


def weakest_phonemes(words: Sequence[Mapping[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """The `n` lowest-scored phonemes over the whole take, lowest first; ties keep the order of
    the take. Each entry: `{phoneme, accuracy, word}`."""
    flat = [
        {"phoneme": phoneme["phoneme"], "accuracy": phoneme["accuracy"], "word": word["word"]}
        for word in words
        for phoneme in word.get("phonemes") or []
        if phoneme.get("accuracy") is not None
    ]
    flat.sort(key=lambda entry: entry["accuracy"])  # stable
    return flat[: max(n, 0)]


def scores_document(
    output: Mapping[str, Any], provider: str, model: str, at: datetime
) -> dict[str, Any]:
    """The `azure-pa-1` document stored in `pronunciation_result.scores`.

    `output` is the dump of the gateway's `PronunciationAssessmentOutput`. Scores are 0-100 and
    None on silence. The words keep the provider's order and their phonemes.
    """
    return {
        "format": FORMAT,
        "provider": provider,
        "model": model,
        "assessed_at": at.isoformat(),
        "status": output["status"],
        "overall": {
            "accuracy": output.get("accuracy"),
            "fluency": output.get("fluency"),
            "completeness": output.get("completeness"),
            "pronunciation": output.get("pronunciation"),
        },
        "words": [dict(word) for word in output.get("words") or []],
        "duration_s": output.get("duration_s"),
    }
