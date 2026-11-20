"""单实例保护：命名互斥体 + 广播消息通知已运行实例。

Windows 上双击 exe 会再起一个进程，和常驻实例抢全局热键/托盘。常驻模式启动时
先抢命名互斥体；抢不到说明已有实例在跑，就广播 StarSnip.Activate 让它弹个轻提示，
然后自己退出（互斥体随进程退出自动释放，不会留下锁文件）。
"""

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
HWND_BROADCAST = 0xFFFF
MUTEX_NAME = "Local\\StarSnip.SingleInstance"

kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL,
                                  wintypes.LPCWSTR]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]

# 已运行实例收到这条消息后弹「已在运行」提示（托盘窗口的 WndProc 处理）
ACTIVATE_MESSAGE = user32.RegisterWindowMessageW("StarSnip.Activate")

_handle = None


def acquire(name: str = MUTEX_NAME) -> bool:
    """抢单实例锁；已有实例时返回 False。拿不到锁不阻止启动。"""
    global _handle
    if _handle:
        return True
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True


def notify_running() -> bool:
    """广播激活消息给已运行实例（没有窗口接收也不会报错）。"""
    if not ACTIVATE_MESSAGE:
        return False
    return bool(user32.PostMessageW(HWND_BROADCAST, ACTIVATE_MESSAGE, 0, 0))
