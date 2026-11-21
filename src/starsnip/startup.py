"""开机启动：注册表 Run 键（默认）/ 启动文件夹兜底 / 任务计划程序（高级）。

为什么默认不用任务计划程序：
- 创建任务要管理员权限（UAC 一取消就整段失败），而且任务不出现在
  「设置 → 应用 → 启动」里，用户会以为没生效；
- 本程序不该提权（提权后资源管理器的拖拽会失效），任务计划那点
  「延迟启动」的能力不值得付 UAC 的代价；
- 大多数人是在任务管理器「启动」页管理自启的，那里只认 Run 键与启动文件夹。

三套机制必须一起看：Run 键存在、但被 StartupApproved 标记成禁用时，
登录后根本不会启动——只看「键在不在」会误报「已启用」。
"""

import os
import subprocess
import sys
import winreg

from . import autostart, paths

APP_VALUE = "StarSnip"
SHORTCUT_NAME = "星剪 StarSnip.lnk"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Explorer 记录的「启动项是否被用户/系统关掉」：12 字节，02=启用，03+FILETIME=禁用
APPR_RUN = (r"Software\Microsoft\Windows\CurrentVersion"
            r"\Explorer\StartupApproved\Run")
APPR_FOLDER = (r"Software\Microsoft\Windows\CurrentVersion"
               r"\Explorer\StartupApproved\StartupFolder")
POLICY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
POLICY_NAME = "DisableCurrentUserRun"

APPROVED_ON = bytes([0x02] + [0] * 11)
CREATE_NO_WINDOW = 0x08000000

MODE_AUTO, MODE_RUN, MODE_FOLDER, MODE_TASK = "auto", "run", "folder", "task"
MODE_LABELS = {
    MODE_AUTO: "自动（推荐）",
    MODE_RUN: "注册表启动项",
    MODE_FOLDER: "启动文件夹",
    MODE_TASK: "任务计划程序",
}
MODE_KEYS = {label: key for key, label in MODE_LABELS.items()}


# ---------- 命令与路径 ----------
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_target() -> tuple:
    """返回 (程序, 参数, 工作目录)：与「登录时要执行什么」保持一致。"""
    if is_frozen():
        exe = os.path.abspath(sys.executable)
        return exe, "--startup", os.path.dirname(exe)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.isfile(pythonw) else os.path.abspath(sys.executable)
    return exe, "-m starsnip --startup", os.path.join(paths.app_root(), "src")


def command_line() -> str:
    """注册表 Run 值：Windows 不支持工作目录，所以源码模式必须走启动文件夹。"""
    exe, args, _workdir = launch_target()
    return '"%s" %s' % (exe, args)


def startup_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


def shortcut_path() -> str:
    return os.path.join(startup_dir(), SHORTCUT_NAME)


# ---------- 读取状态 ----------
def approved_state(kind: str = "run") -> str:
    """读 StartupApproved：enabled / disabled / unset（未记录＝按启用算）。"""
    path = APPR_RUN if kind == "run" else APPR_FOLDER
    name = APP_VALUE if kind == "run" else SHORTCUT_NAME
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            data, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return "unset"
    if isinstance(data, (bytes, bytearray)) and data:
        return "enabled" if data[0] in (0x02, 0x04) else "disabled"
    return "unset"


def parse_approved(blob) -> str:
    """纯函数版（好写单测）：None/空 → unset；02/04 → enabled；其余 → disabled。"""
    if not blob:
        return "unset"
    first = blob[0] if isinstance(blob, (bytes, bytearray)) else int(blob)
    return "enabled" if first in (0x02, 0x04) else "disabled"


def policy_blocked() -> list:
    """组策略是否禁止当前用户的 Run 键启动项。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, POLICY_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, POLICY_NAME)
    except OSError:
        return []
    try:
        blocked = int(value) != 0
    except (TypeError, ValueError):
        blocked = False
    return ["组策略已禁止当前用户的注册表启动项"] if blocked else []


def run_entry() -> tuple:
    """(是否存在, 命令行)。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, APP_VALUE)
    except OSError:
        return False, ""
    return True, str(value or "")


def status() -> dict:
    """把三套机制合成一个「登录后到底会不会启动」的结论。"""
    present, value = run_entry()
    cmd = command_line()
    run_current = bool(present and value.strip().lower() == cmd.strip().lower())
    run_appr = approved_state("run")
    folder = os.path.isfile(shortcut_path())
    folder_appr = approved_state("folder")
    task = autostart.is_enabled()
    blocked = policy_blocked()

    run_effective = bool(present and run_appr != "disabled" and run_current)
    folder_effective = bool(folder and folder_appr != "disabled")
    warnings = []
    if present and not run_current:
        warnings.append("注册表启动项指向旧位置，需要重新启用一次")
    if present and run_current and run_appr == "disabled":
        warnings.append("注册表启动项被 Windows 启动管理禁用了")
    if folder and folder_appr == "disabled":
        warnings.append("启动文件夹的快捷方式被 Windows 启动管理禁用了")
    if not run_effective and not folder_effective and not task and blocked:
        warnings.append(blocked[0])

    if run_effective:
        mode = MODE_RUN
    elif folder_effective:
        mode = MODE_FOLDER
    elif task:
        mode = MODE_TASK
    else:
        mode = "none"
    return {
        "run": {"present": present, "current": run_current,
                "approved": run_appr, "command": value},
        "folder": {"present": folder, "approved": folder_appr,
                   "path": shortcut_path()},
        "task": task,
        "policy": blocked,
        "warnings": warnings,
        "enabled": bool(run_effective or folder_effective or task),
        "effective": bool(run_effective or folder_effective or task),
        "mode": mode,
        "needs_admin": mode == MODE_TASK,
        "command": cmd,
    }


def describe(st: dict = None) -> str:
    """给设置页描述行用的一句人话。"""
    st = st or status()
    if not st["enabled"]:
        if st["warnings"]:
            return st["warnings"][0] + "（打开开关可修复）"
        if st["policy"]:
            return st["policy"][0] + "（只能用启动文件夹或任务计划程序）"
        return "未启用（登录 Windows 后不会自动启动）"
    if st["warnings"]:
        return st["warnings"][0] + "，开启开关可重新启用"
    if st["mode"] == MODE_RUN:
        return "已启用 · 注册表启动项（可在 设置 → 应用 → 启动 里查看）"
    if st["mode"] == MODE_FOLDER:
        return "已启用 · 启动文件夹快捷方式"
    return "已启用 · 任务计划程序（需要管理员权限）"


# ---------- 写入 ----------
def _set_run(cmd: str) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_VALUE, 0, winreg.REG_SZ, cmd)


def _del_run() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_VALUE)
    except OSError:
        pass


def approve(kind: str = "run") -> bool:
    """把 StartupApproved 改回「启用」（用户在任务管理器里关过的情况）。"""
    path = APPR_RUN if kind == "run" else APPR_FOLDER
    name = APP_VALUE if kind == "run" else SHORTCUT_NAME
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, APPROVED_ON)
        return True
    except OSError:
        return False


def _ps_quote(text: str) -> str:
    return str(text).replace("'", "''")


def _create_shortcut() -> tuple:
    exe, args, workdir = launch_target()
    target = shortcut_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    script = (
        "$W = New-Object -ComObject WScript.Shell; "
        "$s = $W.CreateShortcut('%s'); "
        "$s.TargetPath = '%s'; $s.Arguments = '%s'; "
        "$s.WorkingDirectory = '%s'; $s.IconLocation = '%s,0'; $s.Save()"
    ) % (_ps_quote(target), _ps_quote(exe), _ps_quote(args),
         _ps_quote(workdir), _ps_quote(exe))
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                        "-WindowStyle", "Hidden", "-Command", script],
                       capture_output=True, creationflags=CREATE_NO_WINDOW,
                       timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
        return False, "创建快捷方式失败：%s" % exc
    if not os.path.isfile(target):
        return False, "启动文件夹里没有生成快捷方式（被安全软件拦了？）"
    return True, target


def disable(clean_task: bool = True) -> tuple:
    """关掉所有我们写过的机制（幂等）。"""
    _del_run()
    removed = []
    try:
        if os.path.isfile(shortcut_path()):
            os.remove(shortcut_path())
            removed.append("启动文件夹")
    except OSError as exc:  # noqa: BLE001
        return False, "删除启动文件夹快捷方式失败：%s" % exc
    task_note = ""
    if clean_task and autostart.is_enabled():
        ok, msg = autostart.disable()
        if not ok:
            return False, "注册表/文件夹已清理，但删除旧计划任务失败：%s" % msg
        task_note = "，并删除了旧计划任务"
    st = status()
    if st["enabled"]:
        return False, "仍检测到启动项：%s" % "、".join(st["warnings"]) or "未知"
    return True, "已关闭开机启动%s" % task_note


def enable(mode: str = MODE_AUTO) -> tuple:
    """按指定方式注册开机启动；auto 会自己选最稳的一种。"""
    mode = mode if mode in MODE_LABELS else MODE_AUTO
    blocked = policy_blocked()

    if mode == MODE_TASK:
        ok, msg = autostart.enable()
        return ok, msg

    if mode == MODE_RUN and not is_frozen():
        # 源码模式：注册表没有工作目录，-m starsnip 会找不到包，只能走启动文件夹
        mode = MODE_FOLDER

    if mode == MODE_AUTO:
        mode = MODE_FOLDER if (blocked or not is_frozen()) else MODE_RUN

    if mode == MODE_RUN:
        if blocked:
            return False, blocked[0] + "，请改用启动文件夹或任务计划程序"
        try:
            _set_run(command_line())
        except OSError as exc:  # noqa: BLE001
            return False, "写入注册表失败：%s" % exc
        present, value = run_entry()
        if not present or value.strip().lower() != command_line().lower():
            return False, "注册表写入后回读不一致，未生效"
        if approved_state("run") == "disabled":
            approve("run")
        st = status()
        if not st["enabled"]:
            return False, "启动项已写入，但系统仍标记为禁用，请在任务管理器里手动启用"
        return True, "已启用：登录 Windows 后自动启动（注册表启动项）"

    ok, target = _create_shortcut()
    if not ok:
        return False, target
    if approved_state("folder") == "disabled":
        approve("folder")
    st = status()
    if not st["enabled"]:
        return False, "快捷方式已创建，但系统仍标记为禁用，请在任务管理器里手动启用"
    return True, "已启用：登录 Windows 后自动启动（启动文件夹）"


def migrate_note() -> str:
    """旧版留下的计划任务提示（存在才提示，不擅自删）。"""
    if not autostart.is_enabled():
        return ""
    st = status()
    if st["mode"] == MODE_TASK:
        return ""
    return "旧的计划任务还在，可能重复启动；需要清理请在任务计划程序里删除 StarSnip"
