"""Windows system tray via Shell_NotifyIcon (stdlib ctypes, no deps).

Includes a visibility diagnostic: Shell_NotifyIconGetRect tells us whether the
icon really exists in the notification area (it may be collapsed into the "^"
overflow on Windows 11).
"""

import ctypes
import os
import sys
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_SHOWTIP = 0x00000080
NOTIFYICON_VERSION_4 = 4

IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


# ---- Win32 prototypes (64-bit safe) ----
kernel32.GetModuleHandleW.restype = wintypes.HANDLE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

user32.RegisterClassW.restype = wintypes.WORD
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPARAM]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                              wintypes.UINT, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT]
user32.CreatePopupMenu.restype = wintypes.HANDLE
user32.CreatePopupMenu.argtypes = []
user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                               ctypes.c_size_t, wintypes.LPCWSTR]
user32.DestroyMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HANDLE]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.TrackPopupMenu.restype = wintypes.UINT
user32.TrackPopupMenu.argtypes = [
    wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                      ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
shell32.Shell_NotifyIconGetRect.argtypes = [
    ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wintypes.RECT)]


class SystemTray:
    """Tray icon + context menu. Callbacks fire on the tray thread."""

    MENU_CAPTURE = 1
    MENU_HISTORY = 2
    MENU_CONFIG = 3
    MENU_EXIT = 4
    MENU_HOTKEY = 5
    MENU_LOG = 6
    MENU_SETTINGS = 7
    MENU_CAPTURE_ONLY = 8

    def __init__(self, on_capture, on_history, on_config, on_exit,
                 tooltip="星剪 StarSnip", log=None, on_hotkey=None, on_log=None,
                 on_settings=None, icon_path=None, on_capture_only=None):
        self.on_capture = on_capture
        self.on_capture_only = on_capture_only
        self.on_history = on_history
        self.on_config = on_config
        self.on_exit = on_exit
        self.on_hotkey = on_hotkey
        self.on_log = on_log
        self.on_settings = on_settings
        self._icon_path = icon_path
        self.tooltip = tooltip
        self._log = log or (lambda msg: None)
        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self.error = None
        self._icon = None
        self._wndproc = WNDPROC(self._wnd_proc)  # keep reference alive

    def _load_icon(self, hinst):
        """自定义图标文件优先；失败回退系统默认图标。"""
        if self._icon_path and os.path.isfile(self._icon_path):
            h = user32.LoadImageW(hinst, self._icon_path, IMAGE_ICON, 0, 0,
                                  LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if h:
                self._log("tray: custom icon loaded %s" % self._icon_path)
                return h
            self._log("tray: LoadImageW failed for %s, fallback" % self._icon_path)
        return user32.LoadIconW(None, IDI_APPLICATION)

    # ---------- public ----------
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3)
        return self.error is None

    def stop(self) -> None:
        hwnd = self._hwnd
        if hwnd:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    def _load_icon(self, hinst):
        """优先用自定义 .ico；失败回退系统默认图标。"""
        if self._icon_path and os.path.isfile(self._icon_path):
            h = user32.LoadImageW(hinst, self._icon_path, IMAGE_ICON,
                                  0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if h:
                self._log("tray: custom icon loaded %s" % self._icon_path)
                return h
        return user32.LoadIconW(None, IDI_APPLICATION)

    def get_rect(self):
        """Rect of the tray icon in screen coords, or None if it is not there."""
        hwnd = self._hwnd
        if not hwnd:
            return None
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = hwnd
        ident.uID = 1
        rect = wintypes.RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(ident),
                                             ctypes.byref(rect))
        if hr != 0:
            self._log("tray: GetRect failed hr=0x%08X (hwnd=%s)"
                      % (hr & 0xFFFFFFFF, hwnd))
            return None
        return (rect.left, rect.top, rect.right - rect.left,
                rect.bottom - rect.top)

    def wait_rect(self, timeout: float = 2.0):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            rect = self.get_rect()
            if rect:
                return rect
            time.sleep(0.08)
        return self.get_rect()

    def update_tooltip(self, text: str) -> None:
        self.tooltip = text
        hwnd = self._hwnd
        if not hwnd:
            return
        nid = self._nid()
        nid.uFlags = NIF_TIP
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ---------- internals ----------
    def _run(self) -> None:
        try:
            hinst = kernel32.GetModuleHandleW(None)
            cls = "StarSnip_Tray_%d" % id(self)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = cls
            if not user32.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._hwnd = user32.CreateWindowExW(
                0, cls, "StarSnip", 0, 0, 0, 0, 0, None, None, hinst, None)
            if not self._hwnd:
                raise ctypes.WinError(ctypes.get_last_error())

            self._icon = self._load_icon(hinst)
            nid = self._nid()
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._log("tray: NIM_ADD ok, icon handle=%s" % self._icon)
            # V4 semantics + tooltip on hover (more reliable on Win10/11)
            nid.uVersion = NOTIFYICON_VERSION_4
            ver_ok = shell32.Shell_NotifyIconW(NIM_SETVERSION,
                                               ctypes.byref(nid))
            self._log("tray: NIM_SETVERSION -> %s" % bool(ver_ok))
            self._ready.set()

            rect = None
            for _ in range(10):
                rect = self.get_rect()
                if rect:
                    break
                import time
                time.sleep(0.1)
            if rect:
                self._log("tray: icon visible at %s (overflow area if you only"
                          " see '^' near the clock)" % (rect,))
            else:
                self._log("tray: icon added but Shell_NotifyIconGetRect failed"
                          " (may be collapsed in the '^' overflow / hidden icons)")

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:  # noqa: BLE001
            self.error = exc
            self._log("tray: FAILED %s: %s" % (type(exc).__name__, exc))
        finally:
            self._ready.set()
            hwnd = self._hwnd
            if hwnd:
                nid = self._nid()
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                user32.DestroyWindow(hwnd)
                self._hwnd = None
            self._log("tray: stopped")

    def _nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = getattr(self, "_icon", None) or 0
        nid.szTip = self.tooltip[:127]
        return nid

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._safe(self.on_capture)
            elif event == WM_RBUTTONUP:
                self._show_menu(hwnd)
            return 0
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            mapping = {
                self.MENU_CAPTURE: self.on_capture,
                self.MENU_CAPTURE_ONLY: self.on_capture_only,
                self.MENU_HISTORY: self.on_history,
                self.MENU_CONFIG: self.on_config,
                self.MENU_EXIT: self.on_exit,
                self.MENU_HOTKEY: self.on_hotkey,
                self.MENU_LOG: self.on_log,
                self.MENU_SETTINGS: self.on_settings,
            }
            handler = mapping.get(cmd)
            if handler:
                self._safe(handler)
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self, hwnd) -> None:
        menu = user32.CreatePopupMenu()
        try:
            user32.AppendMenuW(menu, MF_STRING, self.MENU_CAPTURE, "截图识别")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_CAPTURE_ONLY,
                               "仅截图（不识别）")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_HISTORY, "历史记录")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_SETTINGS, "设置…")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_HOTKEY, "设置快捷键…")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, self.MENU_CONFIG, "打开配置文件")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_LOG, "打开日志")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_EXIT, "退出")
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(
                menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                pt.x, pt.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
            if cmd:
                user32.SendMessageW(hwnd, WM_COMMAND, cmd, 0)
        finally:
            user32.DestroyMenu(menu)

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception:
            pass
