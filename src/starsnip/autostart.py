"""开机启动：用 Windows 任务计划程序（登录时触发）。

任务名固定为 StarSnip，以当前用户、交互式身份、普通权限启动本程序：
- 打包版：直接运行 StarSnip.exe；
- 源码版：pythonw.exe -m starsnip（工作目录设为 src，-m 会把当前目录加进 sys.path）。

创建/删除任务需要管理员权限：当前进程未提权时，用 ShellExecuteExW("runas")
拉起一次 schtasks（会弹 UAC）；用户取消返回 ERROR_CANCELLED，不会静默失败。
"""

import ctypes
import os
import subprocess
import sys
import tempfile
from ctypes import wintypes
from xml.sax.saxutils import escape

from . import paths

TASK_NAME = "StarSnip"
TASK_DESC = "星剪 StarSnip · 登录 Windows 后自动启动"
CREATE_NO_WINDOW = 0x08000000
ERROR_CANCELLED = 1223
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
WAIT_TIMEOUT_MS = 180000

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
shell32.ShellExecuteExW.restype = wintypes.BOOL
shell32.IsUserAnAdmin.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def is_elevated() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def action() -> tuple:
    """返回任务要执行的 (程序, 参数, 工作目录)。"""
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        return exe, "", os.path.dirname(exe)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.isfile(pythonw) else os.path.abspath(sys.executable)
    return exe, "-m starsnip", os.path.join(paths.app_root(), "src")


def task_xml(exe: str, args: str, workdir: str) -> str:
    arg_tag = ""
    if args:
        arg_tag = "      <Arguments>%s</Arguments>\n" % escape(args)
    work_tag = ""
    if workdir:
        work_tag = "      <WorkingDirectory>%s</WorkingDirectory>\n" % escape(workdir)
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        "    <Description>%s</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        "    </LogonTrigger>\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        "    <StartWhenAvailable>false</StartWhenAvailable>\n"
        "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n"
        "    <IdleSettings>\n"
        "      <StopOnIdleEnd>false</StopOnIdleEnd>\n"
        "      <RestartOnIdle>false</RestartOnIdle>\n"
        "    </IdleSettings>\n"
        "    <AllowStartOnDemand>true</AllowStartOnDemand>\n"
        "    <Enabled>true</Enabled>\n"
        "    <Hidden>false</Hidden>\n"
        "    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n"
        "    <WakeToRun>false</WakeToRun>\n"
        "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n"
        "    <Priority>7</Priority>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        "      <Command>%s</Command>\n"
        "%s"
        "%s"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    ) % (escape(TASK_DESC), escape(exe), arg_tag, work_tag)


def _schtasks() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "schtasks.exe")


def _shell_execute(verb, exe: str, params: str = ""):
    """ShellExecuteEx + 等待退出。返回 (exit_code, error_code)。"""
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = verb
    sei.lpFile = exe
    sei.lpParameters = params or None
    sei.nShow = SW_HIDE
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None, ctypes.get_last_error()
    try:
        kernel32.WaitForSingleObject(sei.hProcess, WAIT_TIMEOUT_MS)
        code = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code)):
            return None, ctypes.get_last_error()
        return code.value, 0
    finally:
        if sei.hProcess:
            kernel32.CloseHandle(sei.hProcess)


def _invoke(args) -> tuple:
    """运行 schtasks；未提权就走 UAC。返回 (exit_code|None, error_code)。"""
    exe = _schtasks()
    if is_elevated():
        try:
            proc = subprocess.run([exe] + list(args), capture_output=True,
                                  creationflags=CREATE_NO_WINDOW, timeout=120)
            return proc.returncode, 0
        except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
            return None, getattr(exc, "winerror", -1) or -1
    return _shell_execute("runas", exe, subprocess.list2cmdline(list(args)))


def is_enabled() -> bool:
    """任务计划程序里是否存在 StarSnip 任务（只读，不需要提权）。"""
    try:
        proc = subprocess.run([_schtasks(), "/Query", "/TN", TASK_NAME],
                              capture_output=True,
                              creationflags=CREATE_NO_WINDOW, timeout=20)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def enable() -> tuple:
    """创建（覆盖）登录启动任务。返回 (ok, message)。"""
    exe, args, workdir = action()
    try:
        fd, xml_path = tempfile.mkstemp(prefix="starsnip_task_", suffix=".xml")
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(task_xml(exe, args, workdir))
    except OSError as exc:
        return False, "无法写入任务定义：%s" % exc
    try:
        code, err = _invoke(["/Create", "/TN", TASK_NAME,
                             "/XML", xml_path, "/F"])
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    if code is None:
        if err == ERROR_CANCELLED:
            return False, "已取消管理员授权，未创建计划任务"
        return False, "无法启动任务计划程序（错误码 %s）" % err
    if code != 0:
        return False, ("创建计划任务失败（schtasks 退出码 %d）："
                       "请在 UAC 弹窗里选「是」，并确认当前账户有管理员权限" % code)
    if not is_enabled():
        return False, "任务未出现在任务计划程序中，请重试"
    return True, "已创建计划任务：登录 Windows 后自动启动"


def disable() -> tuple:
    """删除登录启动任务。返回 (ok, message)。"""
    if not is_enabled():
        return True, "计划任务不存在（已是关闭状态）"
    code, err = _invoke(["/Delete", "/TN", TASK_NAME, "/F"])
    if code is None:
        if err == ERROR_CANCELLED:
            return False, "已取消管理员授权，计划任务未删除"
        return False, "无法启动任务计划程序（错误码 %s）" % err
    if code != 0:
        return False, ("删除计划任务失败（schtasks 退出码 %d）："
                       "请在 UAC 弹窗里选「是」" % code)
    if is_enabled():
        return False, "计划任务仍存在，请到「任务计划程序」手动删除"
    return True, "已删除计划任务：不再随 Windows 启动"
