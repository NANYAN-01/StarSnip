"""StarSnip 统一文件系统位置：数据目录、日志、截图/导出目录。

集中此处可避免 logger / history / screenfiles 三处各算一遍路径，
并对历史版本（旧 ScreenOCR 目录）做一次性兼容，避免改名后孤立用户数据。
"""

import os
import sys

APP_NAME = "StarSnip"
LEGACY_NAME = "ScreenOCR"


def data_home() -> str:
    """%APPDATA%\\StarSnip，可用 STARSNIP_HOME（兼容旧 SCREENOCR_HOME）覆盖。

    若新目录尚不存在、而旧 ScreenOCR 目录已存在，则沿用旧目录，
    使改名前已产生的 history.db / 缩略图 / 日志得以保留。
    """
    env = os.environ.get("STARSNIP_HOME") or os.environ.get("SCREENOCR_HOME")
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    new = os.path.join(base, APP_NAME)
    legacy = os.path.join(base, LEGACY_NAME)
    if not os.path.isdir(new) and os.path.isdir(legacy):
        return legacy
    return new


def _user_folder(folder: str) -> str:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(base, folder, APP_NAME)


def pictures_dir() -> str:
    """截图默认保存目录：图片\\StarSnip。"""
    return _user_folder("Pictures")


def documents_dir() -> str:
    """文档导出默认目录：文档\\StarSnip。"""
    return _user_folder("Documents")


def log_path() -> str:
    return os.path.join(data_home(), "starsnip.log")


def app_root() -> str:
    """资源基准目录：打包后为 exe 同级目录，源码运行为仓库根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # paths.py 位于 src/starsnip/paths.py -> 上溯三级到仓库根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def assets_dir() -> str:
    """资源目录：优先 assets/，兼容旧 resource/。

    打包为 onefile 时数据被解到 sys._MEIPASS，应优先在此查找；
    源码运行则用仓库根。
    """
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(meipass)
    bases.append(app_root())
    for base in bases:
        for name in ("assets", "resource"):
            d = os.path.join(base, name)
            if os.path.isdir(d):
                return d
    return os.path.join(app_root(), "assets")


def resource_path(name: str) -> str:
    return os.path.join(assets_dir(), name)
