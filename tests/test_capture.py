"""Capture / crop / GDI downscale smoke test. Writes fixture PNGs for inspection."""

import os
import struct
import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import capture


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", head[16:24])


def main():
    capture.enable_dpi_awareness()
    img = capture.capture_screen()
    print("virtual screen: %dx%d origin=%s" % (img.width, img.height, img.origin))
    assert img.width >= 800 and img.height >= 600
    assert len(img.bgra) == img.width * img.height * 4

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")
    out_dir = os.path.normpath(out_dir)
    full = os.path.join(out_dir, "_capture_full.png")
    capture.save_png(img, full)
    print("full screenshot: %s %s" % (full, png_size(full)))

    cx, cy = img.width // 2, img.height // 2
    crop = img.crop(cx - 100, cy - 50, 200, 100)
    assert (crop.width, crop.height) == (200, 100)
    crop_path = os.path.join(out_dir, "_capture_crop.png")
    capture.save_png(crop, crop_path)
    assert png_size(crop_path) == (200, 100)
    print("crop OK: %dx%d" % png_size(crop_path))

    scaled = img.crop(0, 0, img.width, img.height).to_png_scaled(1280)
    scaled_path = os.path.join(out_dir, "_capture_scaled.png")
    with open(scaled_path, "wb") as f:
        f.write(scaled)
    sw, sh = png_size(scaled_path)
    print("scaled: %dx%d (max side 1280)" % (sw, sh))
    assert max(sw, sh) <= 1280
    print("test_capture OK")


if __name__ == "__main__":
    main()
