import copy
import json
import os
import sys

from . import ocr_core, providers

# 三个模型角色：主 LLM / OCR / 排版布局，各自独立选择厂商与接口
MODEL_ROLES = ("main", "ocr", "layout")
ROLE_LABELS = {"main": "主 LLM", "ocr": "OCR 模型", "layout": "排版布局模型"}
DEFAULT_TIMEOUT = {"main": 120, "ocr": 60, "layout": 120}

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
    # 更新检查：update_url 留空时按 GitHub Releases → raw version.json 回退
    "update_check": True,
    "update_url": "",
    "update_auto": True,
    # 开机启动方式：auto / run / folder / task（见 startup.MODE_*）
    "startup_mode": "auto",
    # 三个模型角色的接入配置；空 = 由旧键（ollama_url/default_model/...）迁移而来
    "models": {},
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
    cfg["models"] = normalize_models(cfg)
    return cfg


# ---------- 三模型接入配置 ----------
def normalize_models(cfg: dict) -> dict:
    """把 models 规范成三个角色各一份完整配置。

    老配置里没有 models（只有 ollama_url / default_model / layout_model），
    这里就地迁移成「Ollama（本地）」的三个 profile，用户不用重设。
    """
    raw = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    legacy = {
        "main": cfg.get("translate_model") or cfg.get("layout_model") or "",
        "ocr": cfg.get("default_model") or "",
        "layout": cfg.get("layout_model") or "",
    }
    out = {}
    for role in MODEL_ROLES:
        item = raw.get(role)
        item = item if isinstance(item, dict) else {}
        provider = item.get("provider") or "ollama"
        base = str(item.get("base_url") or "").strip()
        if not base:
            base = providers.base_url(provider) or cfg.get("ollama_url", "")
        try:
            timeout = int(item.get("timeout") or DEFAULT_TIMEOUT[role])
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT[role]
        prefix = item.get("auth_prefix")
        out[role] = {
            "provider": provider,
            "base_url": base,
            "api_key": item.get("api_key") or "",
            "model": item.get("model") or legacy[role],
            "timeout": timeout,
            "stream": bool(item.get("stream", False)),
            "auth_header": item.get("auth_header") or "Authorization",
            "auth_prefix": "Bearer " if prefix is None else prefix,
        }
    # 环境变量只覆盖 ollama 角色（老行为：OLLAMA_URL / OLLAMA_MODEL）
    env_url = os.environ.get("OLLAMA_URL")
    env_model = os.environ.get("OLLAMA_MODEL")
    for role, profile in out.items():
        if profile["provider"] != "ollama":
            continue
        if env_url:
            profile["base_url"] = env_url.rstrip("/")
        if env_model and role == "ocr":
            profile["model"] = env_model
    return out


def model_profile(cfg: dict, role: str) -> dict:
    """取某个角色的接入配置（缺了就现场规范化一份）。"""
    models = cfg.get("models")
    if not isinstance(models, dict) or not models:
        return normalize_models(cfg)[role]
    profile = models.get(role)
    if not isinstance(profile, dict):
        return normalize_models(cfg)[role]
    return profile


def save_models(models: dict, path: str = None) -> str:
    """三模型配置一律写 config.local.json。

    API Key 是隐私：绝不能写进受版本控制的 config.json。顺手把旧键同步一份，
    让 --check / 旧版本代码仍能读到当前选择。
    """
    base = path or CONFIG_PATH
    local = local_config_path(base)
    data = _read_json(local)
    data["models"] = models
    ocr = models.get("ocr") or {}
    layout = models.get("layout") or {}
    main = models.get("main") or {}
    if ocr.get("model"):
        data["default_model"] = ocr["model"]
    if layout.get("model"):
        data["layout_model"] = layout["model"]
    if main.get("model"):
        data["translate_model"] = main["model"]
    if ocr.get("provider") == "ollama" and ocr.get("base_url"):
        data["ollama_url"] = ocr["base_url"]
    os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
    with open(local, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return local


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
