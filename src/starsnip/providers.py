"""预置厂商清单：全部走 OpenAI 兼容的 /chat/completions。

BaseURL 取自各厂商官方文档（2026-11 核对）：
- DeepSeek   https://api.deepseek.com                     （官方 SDK 示例；也接受 /v1 前缀）
- Kimi       https://api.moonshot.cn/v1                   （OpenAI 兼容）
- 阿里百炼   https://dashscope.aliyuncs.com/compatible-mode/v1
             注意：形如 llm-xxxx.cn-beijing.maas.aliyuncs.com 的是「专属部署」地址，
             不是标准入口，需要的话在「自定义 API」里填。
- 腾讯 TokenHub https://tokenhub.tencentmaas.com/v1       （国际站 tokenhub-intl.tencentmaas.com）
- 火山方舟   https://ark.cn-beijing.volces.com/api/v3     （数据面标准调用地址）

URL 一律可编辑：换地域、走代理、用专属部署都直接改输入框。
"""

OLLAMA_DEFAULT = "http://127.0.0.1:11434"

# 顺序就是下拉框顺序（Ollama 在最前：老用户零成本）
PROVIDERS = [
    {
        "key": "ollama",
        "label": "Ollama（本地）",
        "base_url": OLLAMA_DEFAULT,
        "docs": "https://ollama.com",
        "keys_url": "",
        "hint": "本地模型，无需 API Key；OCR 建议 glm-ocr:latest",
        "vision": True,
        "native": True,
    },
    {
        "key": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "docs": "https://api-docs.deepseek.com/zh-cn",
        "keys_url": "https://platform.deepseek.com/api_keys",
        "hint": "deepseek-chat / deepseek-reasoner",
        "vision": False,
    },
    {
        "key": "kimi",
        "label": "Kimi（Moonshot）",
        "base_url": "https://api.moonshot.cn/v1",
        "docs": "https://platform.kimi.com/docs/api/overview",
        "keys_url": "https://platform.kimi.com/console/account",
        "hint": "kimi-k2-* / moonshot-v1-*",
        "vision": False,
    },
    {
        "key": "bailian",
        "label": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "docs": "https://docs.bailian.console.aliyun.com/zh/model-studio/get-api-key",
        "keys_url": "https://bailian.console.aliyun.com/",
        "hint": "qwen-plus / qwen3-vl-plus（视觉）；专属部署走自定义",
        "vision": True,
    },
    {
        "key": "tencent",
        "label": "腾讯 TokenHub",
        "base_url": "https://tokenhub.tencentmaas.com/v1",
        "docs": "https://cloud.tencent.com/document/product/1823",
        "keys_url": "https://console.cloud.tencent.com/tokenhub",
        "hint": "模型名按 TokenHub 模型广场填",
        "vision": None,
    },
    {
        "key": "volcengine",
        "label": "火山方舟",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "docs": "https://www.volcengine.com/docs/82379/1298459",
        "keys_url": "https://console.volcengine.com/ark",
        "hint": "接入点 ep-xxx 或模型名（doubao-seed-1-6 等）",
        "vision": True,
    },
    {
        "key": "custom",
        "label": "自定义 API",
        "base_url": "",
        "docs": "",
        "keys_url": "",
        "hint": "任意 OpenAI 兼容服务；BaseURL 一般要写到 /v1",
        "vision": None,
    },
]

BY_KEY = {p["key"]: p for p in PROVIDERS}
LABELS = [p["label"] for p in PROVIDERS]
LABEL_TO_KEY = {p["label"]: p["key"] for p in PROVIDERS}


def get(key: str) -> dict:
    return BY_KEY.get(key or "ollama") or BY_KEY["ollama"]


def base_url(key: str) -> str:
    return get(key)["base_url"]


def label(key: str) -> str:
    return get(key)["label"]


def key_of(label_text: str) -> str:
    return LABEL_TO_KEY.get(label_text, "custom")


def is_ollama(key: str) -> bool:
    return get(key)["key"] == "ollama"


def needs_key(key: str) -> bool:
    return get(key)["key"] != "ollama"


def default_profile(key: str = "ollama", model: str = "") -> dict:
    """选中厂商时预填的一套配置（BaseURL 自动填、其余留空）。"""
    item = get(key)
    return {
        "provider": item["key"],
        "base_url": item["base_url"],
        "api_key": "",
        "model": model,
        "timeout": 60,
        "stream": False,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    }
