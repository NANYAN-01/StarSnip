"""Clipboard image test: put screenshot on CF_DIB and read header back."""

import ctypes
import struct
import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import capture, clipboard_image
from starsnip.clipboard_image import user32, kernel32


def main():
    capture.enable_dpi_awareness()
    img = capture.capture_screen().crop(0, 0, 64, 48)
    clipboard_image.copy_image(img.bgra, img.width, img.height)
    assert user32.IsClipboardFormatAvailable(8), "CF_DIB not available"
    assert user32.OpenClipboard(None)
    try:
        handle = user32.GetClipboardData(8)
        assert handle, "no clipboard data"
        ptr = kernel32.GlobalLock(handle)
        try:
            header = ctypes.string_at(ptr, 40)
        finally:
            kernel32.GlobalUnlock(handle)
        size, width, height = struct.unpack("<Iii", header[:12])
        print("clipboard DIB: size=%d width=%d height=%d" % (size, width, height))
        assert (width, height) == (64, 48)
    finally:
        user32.CloseClipboard()
    print("NOTE: system clipboard was overwritten by this test")
    print("test_clipboard OK")


if __name__ == "__main__":
    main()
