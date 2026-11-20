import copy
import json
import os
import sys

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    "default_model": "glm-ocr:latest",
    "joint_enabled": False,
    "joint_models": ["glm-ocr:latest", "richardyoung/unlimited-ocr:latest"],
    "verify_models": ["glm-ocr:latest", "richardyoung/unlimited-ocr:latest"],
    "hotkey": "ctrl+alt+o",
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
    "prompt": "请识别图片中的所有文字内容，按原样逐行输出，不要遗漏，不要翻译。表格请保持行列对齐。",
    "table_prompt": "请将图片中的表格转换为 Markdown 表格，包含表头与所有数据行，保留合计行，数字不得遗漏或改动。只输出 Markdown。",
}

def _default_config_path() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile: config sits next to the exe
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config.json")


CONFIG_PATH = _default_config_path()


def load(path: str = CONFIG_PATH) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            merged = json.load(f)
        cfg.update(merged)
    except FileNotFoundError:
        pass
    cfg["ollama_url"] = os.environ.get("OLLAMA_URL", cfg["ollama_url"]).rstrip("/")
    cfg["default_model"] = os.environ.get("OLLAMA_MODEL", cfg["default_model"])
    return cfg


def save_setting(key: str, value, path: str = None) -> str:
    """Update one key in config.json, preserving everything else."""
    p = path or CONFIG_PATH
    data = {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data[key] = value
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p
