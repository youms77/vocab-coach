"""Tiny synthetic clips for the pronunciation tests (no audio file is ever committed)."""

import struct


def wav(
    seconds: float = 1.0, *, rate: int = 16000, channels: int = 1, bits: int = 16, tag: int = 1
) -> bytes:
    frames = int(seconds * rate)
    audio = b"\x00" * (frames * channels * bits // 8)
    fmt = struct.pack(
        "<HHIIHH", tag, channels, rate, rate * channels * bits // 8, channels * bits // 8, bits
    )
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(audio))
    return b"RIFF" + struct.pack("<I", len(body) + len(audio)) + body + audio


def ogg(seconds: float = 2.0, *, channels: int = 1, pre_skip: int = 312) -> bytes:
    head = b"OpusHead" + bytes([1, channels]) + struct.pack("<H", pre_skip) + b"\x00" * 9
    first = b"OggS" + b"\x00\x02" + struct.pack("<q", 0) + b"\x00" * 12 + head
    granule = int(seconds * 48000) + pre_skip
    last = b"OggS" + b"\x00\x04" + struct.pack("<q", granule) + b"\x00" * 12 + b"x" * 20
    return first + last


WEBM = bytes.fromhex("1a45dfa3") + b"\x00" * 64
