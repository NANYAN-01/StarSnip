"""版本检查与自动更新。

更新源按顺序尝试（任一成功即停）：
1. config 里的 update_url（自建/内网清单，默认空 = 不启用）；
2. GitHub Releases 的 latest API（公开仓库免 token，60 次/小时/IP）；
3. 仓库里的静态 version.json（raw 地址）。

清单格式（version.json 与自建 URL 同一套）：

    {"version": "1.1.0",
     "url": "https://github.com/NANYAN-01/StarSnip/releases/tag/v1.1.0",
     "notes": "修了什么",
     "assets": {"exe": "https://.../StarSnip.exe", "sha256": "<可选>"}}

只依赖标准库：urllib 下载、hashlib 校验、MoveFileExW 替换正在运行的 exe。
"""

import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from . import __repo__, __version__, paths

API_URL = "https://api.github.com/repos/%s/releases/latest" % __repo__
RAW_URL = ("https://raw.githubusercontent.com/%s/main/version.json" % __repo__)
CACHE_NAME = "update.json"
TTL_S = 24 * 3600
TIMEOUT_S = 5
CHUNK = 64 * 1024
MIN_EXE_BYTES = 5 * 1024 * 1024     # 小于这个数肯定不是我们的 exe
MOVEFILE_REPLACE_EXISTING = 0x1


# ---------- 版本号 ----------
def parse_version(text) -> tuple:
    """v1.2.0 / 1.2.0-beta.1 / 1.2 都能认出 (1, 2, 0)；认不出返回 (0, 0, 0)。"""
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text or ""))
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def is_newer(latest, current=None) -> bool:
    return parse_version(latest) > parse_version(current or __version__)


# ---------- 清单解析 ----------
def _manifest(data: dict) -> dict:
    """自建清单 / version.json。"""
    assets = data.get("assets") or {}
    exe = assets.get("exe") or data.get("exe") or ""
    sha = assets.get("sha256") or data.get("sha256") or ""
    if not data.get("version"):
        raise ValueError("清单缺少 version")
    return {"latest": str(data["version"]),
            "url": data.get("url") or data.get("html_url") or "",
            "notes": data.get("notes") or data.get("body") or "",
            "exe": exe, "sha256": sha}


def _release(data: dict) -> dict:
    """GitHub Releases API。"""
    assets = data.get("assets") or []
    exe, sha = "", ""
    for item in assets:
        name = str(item.get("name") or "")
        if name.lower().endswith(".exe"):
            exe = item.get("browser_download_url") or ""
            digest = str(item.get("digest") or "")
            if digest.startswith("sha256:"):
                sha = digest.split(":", 1)[1]
            break
    if not data.get("tag_name"):
        raise ValueError("Release 缺少 tag_name")
    return {"latest": str(data["tag_name"]),
            "url": data.get("html_url") or "",
            "notes": data.get("body") or "",
            "exe": exe, "sha256": sha}


def _fetch(url: str, timeout: float = TIMEOUT_S) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "StarSnip/%s" % __version__,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check(cfg: dict = None, timeout: float = TIMEOUT_S) -> dict:
    """查最新版本。返回 {ok, latest, newer, url, notes, exe, sha256, source}。"""
    cfg = cfg or {}
    sources = []
    custom = (cfg.get("update_url") or "").strip()
    if custom:
        sources.append(("custom", custom))
    sources.append(("github", API_URL))
    sources.append(("raw", RAW_URL))

    errors = []
    for name, url in sources:
        try:
            raw = _fetch(url, timeout).lstrip(b"\xef\xbb\xbf")
            data = json.loads(raw.decode("utf-8", "replace"))
            info = _release(data) if name == "github" else _manifest(data)
        except urllib.error.HTTPError as exc:
            hint = "（GitHub 限流，稍后再试）" if exc.code == 403 else ""
            errors.append("%s: HTTP %s%s" % (name, exc.code, hint))
            continue
        except Exception as exc:  # noqa: BLE001 - 网络/格式问题都换下一个源
            errors.append("%s: %s" % (name, type(exc).__name__))
            continue
        info["ok"] = True
        info["newer"] = is_newer(info["latest"])
        info["source"] = name
        info["current"] = __version__
        write_cache(info)
        return info
    return {"ok": False, "newer": False, "current": __version__,
            "error": "；".join(errors[:2]) or "无法连接更新服务"}


# ---------- 缓存（24h 内不重复自动查） ----------
def cache_path() -> str:
    return os.path.join(paths.data_home(), CACHE_NAME)


def read_cache() -> dict:
    try:
        with open(cache_path(), "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_cache(info: dict) -> None:
    try:
        os.makedirs(paths.data_home(), exist_ok=True)
        payload = {key: info.get(key) for key in
                   ("latest", "url", "notes", "exe", "sha256")}
        payload["checked_at"] = int(time.time())
        with open(cache_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def cache_fresh() -> bool:
    stamp = read_cache().get("checked_at") or 0
    try:
        return (time.time() - int(stamp)) < TTL_S
    except (TypeError, ValueError):
        return False


# ---------- 下载与校验 ----------
def update_dir() -> str:
    base = os.path.join(tempfile.gettempdir(), "StarSnipUpdate")
    os.makedirs(base, exist_ok=True)
    return base


def download(info: dict, progress=None) -> dict:
    """下载新版 exe 到临时目录并校验。返回 {ok, path, sha256, error}。"""
    url = (info or {}).get("exe") or ""
    if not url:
        return {"ok": False, "error": "发布页没有提供 exe 下载地址"}
    version = str((info or {}).get("latest") or "new").replace("/", "_")
    dest = os.path.join(update_dir(), "StarSnip_%s.exe" % version)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "StarSnip/%s" % __version__})
        hasher = hashlib.sha256()
        total = 0
        with urllib.request.urlopen(req, timeout=60) as resp, \
                open(dest, "wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
                if progress:
                    progress(total)
    except Exception as exc:  # noqa: BLE001 - 失败要能降级成「打开下载页」
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    if total < MIN_EXE_BYTES:
        return {"ok": False, "error": "下载内容不完整（%d 字节）" % total}
    with open(dest, "rb") as handle:
        if handle.read(2) != b"MZ":
            return {"ok": False, "error": "下载的不是 Windows 程序"}
    digest = hasher.hexdigest()
    expected = (info or {}).get("sha256") or ""
    if expected and expected.lower() != digest:
        return {"ok": False, "error": "SHA256 校验不一致，已放弃更新"}
    return {"ok": True, "path": dest, "sha256": digest, "bytes": total}


# ---------- 替换正在运行的 exe ----------
def _move(src: str, dst: str) -> bool:
    try:
        return bool(ctypes.windll.kernel32.MoveFileExW(
            ctypes.c_wchar_p(src), ctypes.c_wchar_p(dst),
            MOVEFILE_REPLACE_EXISTING))
    except Exception:  # noqa: BLE001
        return False


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def apply_pending(new_exe: str) -> tuple:
    """把新 exe 换到当前程序位置。返回 (ok, 备份路径 | 错误)。

    Windows 允许重命名正在运行的 exe（Chrome 就是这么升级的），
    但同一路径上不能直接覆盖，所以先改名成 .old 再放新的。
    """
    if not can_self_update():
        return False, "源码模式不自动替换，请用发布页的 exe"
    if not os.path.isfile(new_exe):
        return False, "更新包不存在"
    current = os.path.abspath(sys.executable)
    backup = current + ".old"
    try:
        if os.path.isfile(backup):
            os.remove(backup)
    except OSError:
        pass
    if not _move(current, backup):
        return False, "无法重命名当前程序（可能装在只读目录）"
    if not _move(new_exe, current):
        _move(backup, current)
        return False, "替换失败，已回滚到旧版本"
    return True, backup


def cleanup_old() -> None:
    """上次更新留下的 <exe>.old 在下次启动后删掉。"""
    if not can_self_update():
        return
    backup = os.path.abspath(sys.executable) + ".old"
    if os.path.isfile(backup):
        try:
            os.remove(backup)
        except OSError:
            pass


def relaunch_after_exit(delay_s: int = 2) -> bool:
    """退出后再拉起新版本。

    不能在退出前直接 Popen：单实例互斥体还没释放，新进程会广播
    「已在运行」然后自己退出。这里交给一个临时 .cmd 等两秒再启动。
    """
    exe = os.path.abspath(sys.executable)
    script = os.path.join(update_dir(), "relaunch.cmd")
    try:
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("@echo off\r\n")
            handle.write("timeout /t %d /nobreak >nul\r\n" % max(1, int(delay_s)))
            handle.write('start "" "%s"\r\n' % exe)
            handle.write('del "%%~f0"\r\n')
        subprocess.Popen(["cmd", "/c", script], close_fds=True,
                         creationflags=0x08000000)
        return True
    except OSError:
        return False
