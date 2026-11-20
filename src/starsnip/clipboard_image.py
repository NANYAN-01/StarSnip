"""Put a BGRA screenshot onto the Windows clipboard as CF_DIB (stdlib ctypes)."""

import ctypes
import struct
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_DIB = 8
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


def _dib_bytes(bgra: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0,
                         stride * height, 0, 0, 0, 0)
    rows = []
    for y in range(height - 1, -1, -1):  # bottom-up
        row = bytearray(bgra[y * stride:(y + 1) * stride])
        row[3::4] = b"\xff" * width  # opaque alpha
        rows.append(bytes(row))
    return header + b"".join(rows)


def copy_image(bgra: bytes, width: int, height: int, retries: int = 3) -> None:
    """Copy the image to the clipboard; raises OSError if the clipboard is busy."""
    data = _dib_bytes(bgra, width, height)
    if len(bgra) != width * height * 4:
        raise ValueError("buffer size mismatch")
    last = None
    for attempt in range(retries):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not handle:
                    raise OSError("GlobalAlloc failed")
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    kernel32.GlobalFree(handle)
                    raise OSError("GlobalLock failed")
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(handle)
                if not user32.SetClipboardData(CF_DIB, handle):
                    kernel32.GlobalFree(handle)
                    raise OSError("SetClipboardData failed")
                return
            finally:
                user32.CloseClipboard()
        last = "clipboard busy (attempt %d/%d)" % (attempt + 1, retries)
        time.sleep(0.12)
    raise OSError(last or "clipboard unavailable")
