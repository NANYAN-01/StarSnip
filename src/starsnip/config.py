import copy
import json
import os
import sys

from . import ocr_core

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    "default_model": "glm-ocr:latest",
    # 交叉校验的对照模型；主模型始终用当前选中的 OCR 模型，同名的会被跳过
    "verify_models": ["glm-ocr:latest", "richardyoung/unlimited-ocr:latest"],
    "hotkey": "ctrl+2",
    "hotkey_capture_only": "ctrl+1",
    "max_side_px": 1280,
    "timeout_s": 60,
    "history_enabled": True,
    "history_keep": 500,
    "save_image": True,
    "image_dir": "",
    "clipboard_image": True,
    "toast_ms": 2000,
    "export_dir": "",
    "layout_model": "qwen3.5:4b",
    "layout_timeout": 120,
    "keep_alive": "30m",
    "tray_toast": True,
    "theme": "system",
    "translate_model": "",
    "pin_alpha": 1.0,
    "beautify_bg": "white",
    "beautify_pad_ratio": 0.08,
    "beautify_radius_ratio": 0.025,
    # 提示词只维护一份：ocr_core 的常量即默认值，config.json 里改同名键可覆盖
    "prompt": ocr_core.DEFAULT_PROMPT,
    "table_prompt": ocr_core.TABLE_PROMPT,
}

def _default_config_path() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile: config sits next to the exe
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config.json")


CONFIG_PATH = _default_config_path()

# 本地私密覆盖文件：与 config.json 同目录，不入库（.gitignore）。
# 内网 Ollama 地址、个人路径之类不该公开的设置放这里，启动时它覆盖 config.json。
LOCAL_CONFIG_NAME = "config.local.json"


def local_config_path(path: str = None) -> str:
    base = path or CONFIG_PATH
    return os.path.join(os.path.dirname(base) or ".", LOCAL_CONFIG_NAME)


def _read_json(p: str) -> dict:
    # utf-8-sig：兼容记事本/PowerShell 写出的 BOM，否则整个本地配置会被静默忽略
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load(path: str = CONFIG_PATH) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    cfg.update(_read_json(path))
    cfg.update(_read_json(local_config_path(path)))
    cfg["ollama_url"] = os.environ.get("OLLAMA_URL", cfg["ollama_url"]).rstrip("/")
    cfg["default_model"] = os.environ.get("OLLAMA_MODEL", cfg["default_model"])
    return cfg


def save_setting(key: str, value, path: str = None) -> str:
    """Update one key in config.json, preserving everything else.

    若同目录存在 config.local.json，则写入它而不是 config.json：
    避免「在设置里填了内网地址」把私密值写进入库的基础配置文件。
    """
    base = path or CONFIG_PATH
    local = local_config_path(base)
    target = local if os.path.isfile(local) else base
    data = _read_json(target)
    data[key] = value
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return target
