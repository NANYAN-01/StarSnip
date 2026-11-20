"""Minimal stdlib PNG encoder for BGRA buffers (no Pillow dependency)."""

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(width: int, height: int, bgra: bytes) -> bytes:
    """Encode a top-down BGRA buffer to PNG bytes."""
    if len(bgra) != width * height * 4:
        raise ValueError("buffer size mismatch: %d != %d"
                         % (len(bgra), width * height * 4))
    w4 = width * 4
    raw = bytearray(height * (w4 + 1))
    for y in range(height):
        src = bgra[y * w4:(y + 1) * w4]
        ro = y * (w4 + 1)
        raw[ro] = 0  # filter: none
        # BGRA -> RGBA via extended-slice assignment, bounded to the row (C-speed)
        for c, channel in ((0, src[2::4]), (1, src[1::4]),
                           (2, src[0::4]), (3, src[3::4])):
            start = ro + 1 + c
            raw[start:start + 4 * width - 3:4] = channel
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + _chunk(b"IEND", b""))
