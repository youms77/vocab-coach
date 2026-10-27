"""Pure parts of the pronunciation module: audio format check, counters, stored document."""

import struct
from datetime import UTC, datetime

from app.domain import pronunciation as pa
from tests.audio_support import WEBM, ogg, wav


def test_wav_16k_mono_is_accepted():
    assert pa.audio_problem(wav(), "wav") is None
    assert pa.audio_kind(wav()) == "wav"


def test_wav_variants_are_refused():
    assert pa.audio_problem(wav(rate=44100), "wav") == pa.UNSUPPORTED_FOR_ASSESSMENT
    assert pa.audio_problem(wav(channels=2), "wav") == pa.UNSUPPORTED_FOR_ASSESSMENT
    assert pa.audio_problem(wav(bits=8), "wav") == pa.UNSUPPORTED_FOR_ASSESSMENT
    assert pa.audio_problem(wav(tag=3), "wav") == pa.UNSUPPORTED_FOR_ASSESSMENT


def test_truncated_or_chunkless_wav_is_refused():
    assert pa.audio_problem(wav()[:20], "wav") is not None
    assert pa.audio_problem(b"RIFF\x00\x00\x00\x00WAVE", "wav") is not None


def test_ogg_opus_mono_is_accepted_stereo_refused():
    assert pa.audio_problem(ogg(), "ogg") is None
    assert pa.audio_problem(ogg(), "opus") is None
    assert pa.audio_problem(ogg(channels=2), "ogg") is not None


def test_webm_m4a_mp3_and_garbage_are_refused():
    for data, ext in (
        (WEBM, "webm"),
        (b"\x00\x00\x00\x18ftypM4A ", "m4a"),
        (b"ID3\x03", "mp3"),
        (b"", "wav"),
        (b"hello", ""),
    ):
        assert pa.audio_problem(data, ext) == pa.UNSUPPORTED_FOR_ASSESSMENT


def test_extension_must_agree_with_content():
    assert pa.audio_problem(wav(), "webm") is not None
    assert pa.audio_problem(ogg(), "wav") is not None
    assert pa.audio_problem(wav(), "") is None


def test_duration_from_headers():
    assert pa.audio_duration_s(wav(1.5)) == 1.5
    assert abs(pa.audio_duration_s(ogg(2.0)) - 2.0) < 1e-6
    assert pa.audio_duration_s(WEBM) is None


def test_streamed_wav_with_unknown_size_uses_what_is_there():
    data = bytearray(wav(1.0))
    data[40:44] = struct.pack("<I", 0xFFFFFFFF)
    assert pa.audio_duration_s(bytes(data)) == 1.0


WORDS = [
    {
        "word": "think",
        "accuracy": 55,
        "error_type": "Mispronunciation",
        "phonemes": [{"phoneme": "θ", "accuracy": 20}, {"phoneme": "ɪ", "accuracy": 90}],
    },
    {"word": "the", "accuracy": 0, "error_type": "Omission", "phonemes": []},
    {"word": "uh", "accuracy": 0, "error_type": "Insertion"},
    {
        "word": "ship",
        "accuracy": 80,
        "error_type": "None",
        "phonemes": [{"phoneme": "ʃ", "accuracy": 20}, {"phoneme": "p", "accuracy": None}],
    },
    {"word": "so", "accuracy": 70, "error_type": "Monotone"},
]


def test_summarize_counts_only_the_three_error_types():
    assert pa.summarize(WORDS) == {"mispronounced": 1, "omitted": 1, "inserted": 1}
    assert pa.summarize([]) == {"mispronounced": 0, "omitted": 0, "inserted": 0}


def test_weakest_phonemes_lowest_first_ties_in_take_order():
    weakest = pa.weakest_phonemes(WORDS, 2)
    assert [(p["phoneme"], p["word"]) for p in weakest] == [("θ", "think"), ("ʃ", "ship")]
    assert len(pa.weakest_phonemes(WORDS, 10)) == 3  # the None accuracy is left out
    assert pa.weakest_phonemes(WORDS, 0) == []


def test_scores_document_shape():
    at = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
    out = {
        "status": "ok",
        "accuracy": 80.0,
        "fluency": 70.0,
        "completeness": 100.0,
        "pronunciation": 75.0,
        "words": WORDS,
        "duration_s": 2.5,
    }
    doc = pa.scores_document(out, "azure", "pa-rest-v1", at)
    assert doc["format"] == "azure-pa-1"
    assert doc["overall"] == {
        "accuracy": 80.0,
        "fluency": 70.0,
        "completeness": 100.0,
        "pronunciation": 75.0,
    }
    assert doc["assessed_at"] == "2026-10-24T09:00:00+00:00"
    assert doc["words"] == WORDS and doc["words"] is not WORDS
    silent = pa.scores_document({"status": "silence"}, "azure", "pa-rest-v1", at)
    assert silent["overall"]["pronunciation"] is None and silent["words"] == []
