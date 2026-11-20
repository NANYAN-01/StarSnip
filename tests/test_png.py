"""PNG encoder round-trip test (no external deps)."""

import struct
import sys
import zlib

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip.png import encode_png


def main():
    # 2x2 BGRA: red, green, blue, white
    bgra = bytes([
        0, 0, 255, 255,   # red
        0, 255, 0, 255,   # green
        255, 0, 0, 255,   # blue
        255, 255, 255, 255,
    ])
    data = encode_png(2, 2, bgra)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "png signature"

    pos = 8
    chunks = {}
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        chunks[tag] = payload
        pos += 12 + length

    assert b"IHDR" in chunks and b"IDAT" in chunks and b"IEND" in chunks
    w, h, depth, ctype = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (w, h, depth, ctype) == (2, 2, 8, 6), (w, h, depth, ctype)

    raw = zlib.decompress(chunks[b"IDAT"])
    # filter byte + 2 pixels RGBA per row
    assert len(raw) == 2 * (1 + 2 * 4)
    px = raw[1:9]
    assert px[:3] == b"\xff\x00\x00", px      # red
    assert px[4:7] == b"\x00\xff\x00", px     # green
    print("test_png OK (signature/IHDR/IDAT/RGBA order verified)")


if __name__ == "__main__":
    main()
