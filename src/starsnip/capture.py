"""Win32 GDI screen capture, crop and high-quality downscale (stdlib only)."""

import ctypes
from ctypes import wintypes

from .png import encode_png

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:
    shcore = None

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
BI_RGB = 0
DIB_RGB_COLORS = 0
HALFTONE = 4


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


def enable_dpi_awareness() -> None:
    """Make tkinter coords equal physical pixels (multi-DPI safe)."""
    try:
        if shcore is not None:
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def virtual_screen() -> tuple:
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


class Image:
    def __init__(self, width: int, height: int, bgra: bytes, origin=(0, 0)):
        self.width = width
        self.height = height
        self.bgra = bgra
        self.origin = origin

    def crop(self, x: int, y: int, w: int, h: int) -> "Image":
        x = max(0, min(x, self.width))
        y = max(0, min(y, self.height))
        w = max(1, min(w, self.width - x))
        h = max(1, min(h, self.height - y))
        stride = self.width * 4
        rows = []
        for yy in range(y, y + h):
            start = yy * stride + x * 4
            rows.append(self.bgra[start:start + w * 4])
        return Image(w, h, b"".join(rows),
                     (self.origin[0] + x, self.origin[1] + y))

    def to_png(self) -> bytes:
        return encode_png(self.width, self.height, self.bgra)

    def to_png_scaled(self, max_side: int) -> bytes:
        scale = max_side / float(max(self.width, self.height))
        if scale >= 1.0:
            return self.to_png()
        nw = max(1, int(round(self.width * scale)))
        nh = max(1, int(round(self.height * scale)))
        try:
            return encode_png(nw, nh, _gdi_scale(self.bgra, self.width, self.height, nw, nh))
        except OSError:
            return self.to_png()


def _create_dib(hdc, width: int, height: int):
    bmi = BITMAPINFO()
    hdr = bmi.bmiHeader
    hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    hdr.biWidth = width
    hdr.biHeight = -height  # top-down
    hdr.biPlanes = 1
    hdr.biBitCount = 32
    hdr.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                  ctypes.byref(bits), None, 0)
    if not hbmp:
        raise OSError("CreateDIBSection failed")
    return hbmp, bits


def capture_screen() -> Image:
    x, y, w, h = virtual_screen()
    if w <= 0 or h <= 0:
        raise OSError("invalid virtual screen size")
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    hbmp = bits = old = None
    try:
        hbmp, bits = _create_dib(mem_dc, w, h)
        old = gdi32.SelectObject(mem_dc, hbmp)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y,
                            SRCCOPY | CAPTUREBLT):
            raise OSError("BitBlt failed")
        data = ctypes.string_at(bits, w * h * 4)
        return Image(w, h, data, (x, y))
    finally:
        if old:
            gdi32.SelectObject(mem_dc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


def _gdi_scale(bgra: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    screen_dc = user32.GetDC(None)
    src_dc = gdi32.CreateCompatibleDC(screen_dc)
    dst_dc = gdi32.CreateCompatibleDC(screen_dc)
    sbmp = dbmp = sold = dold = None
    try:
        sbmp, sbits = _create_dib(src_dc, sw, sh)
        ctypes.memmove(sbits, bgra, len(bgra))
        sold = gdi32.SelectObject(src_dc, sbmp)
        dbmp, dbits = _create_dib(dst_dc, dw, dh)
        dold = gdi32.SelectObject(dst_dc, dbmp)
        gdi32.SetStretchBltMode(dst_dc, HALFTONE)
        gdi32.SetBrushOrgEx(dst_dc, 0, 0, None)
        if not gdi32.StretchBlt(dst_dc, 0, 0, dw, dh, src_dc, 0, 0, sw, sh,
                                SRCCOPY):
            raise OSError("StretchBlt failed")
        return ctypes.string_at(dbits, dw * dh * 4)
    finally:
        if sold:
            gdi32.SelectObject(src_dc, sold)
        if dold:
            gdi32.SelectObject(dst_dc, dold)
        for bmp in (sbmp, dbmp):
            if bmp:
                gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(src_dc)
        gdi32.DeleteDC(dst_dc)
        user32.ReleaseDC(None, screen_dc)


def save_png(img: Image, path: str) -> None:
    with open(path, "wb") as f:
        f.write(img.to_png())
