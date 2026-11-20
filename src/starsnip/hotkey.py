"""Global hotkey via Win32 RegisterHotKey (stdlib, works when app is unfocused)."""

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_SPECIAL = {
    "space": 0x20, "esc": 0x1B, "tab": 0x09, "enter": 0x0D,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
}


def parse_hotkey(spec: str):
    mods = 0
    vk = None
    for part in spec.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "meta", "super"):
            mods |= MOD_WIN
        elif part in _SPECIAL:
            vk = _SPECIAL[part]
        elif len(part) == 2 and part[0] == "f" and part[1].isdigit():
            vk = 0x70 + int(part[1]) - 1
        elif len(part) == 3 and part[0] == "f" and part[1:].isdigit():
            vk = 0x70 + int(part[1:]) - 1
        elif len(part) == 1:
            vk = user32.VkKeyScanW(ord(part.upper())) & 0xFF
        else:
            raise ValueError("unsupported hotkey part: %s" % part)
    if vk is None:
        raise ValueError("hotkey needs a non-modifier key: %s" % spec)
    return mods, vk


class HotkeyManager:
    """Runs a Win32 message loop on a daemon thread.

    The callback fires on that thread - keep it short and hand off to the
    UI thread via a queue.
    """

    def __init__(self, spec: str, callback):
        self.spec = spec
        self.callback = callback
        self._thread = None
        self._thread_id = None
        self._mods = self._vk = None
        self.error = None

    def start(self) -> bool:
        self._mods, self._vk = parse_hotkey(self.spec)
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(timeout=3)
        return self.error is None

    def _run(self, ready: threading.Event) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self._mods, self._vk):
            self.error = ctypes.WinError(ctypes.get_last_error())
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread_id = None
