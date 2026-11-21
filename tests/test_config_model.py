"""三模型接入配置的离线单测：老配置迁移 / 预置厂商 / 保存落点。"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

_TMP = tempfile.mkdtemp(prefix="probe_models_")
os.environ["STARSNIP_HOME"] = _TMP

from starsnip import config, providers  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  x %s" % msg)
    else:
        print("  v %s" % msg)


def test_providers():
    print("[预置厂商]")
    check(providers.LABELS[0].startswith("Ollama"), "第一项是 Ollama（本地）")
    check(providers.LABELS[-1] == "自定义 API", "最后一项是自定义 API")
    expected = {
        "deepseek": "https://api.deepseek.com",
        "kimi": "https://api.moonshot.cn/v1",
        "bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "tencent": "https://tokenhub.tencentmaas.com/v1",
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    }
    for key, url in expected.items():
        check(providers.base_url(key) == url, "%s 的 BaseURL" % key)
    check(providers.key_of("DeepSeek") == "deepseek", "中文/英文标签能反查")
    check(providers.needs_key("ollama") is False, "Ollama 不需要 Key")


def test_legacy_migration():
    print("[老配置迁移]")
    cfg = {"ollama_url": "http://127.0.0.1:11434",
           "default_model": "glm-ocr:latest",
           "layout_model": "qwen3.5:4b",
           "translate_model": ""}
    models = config.normalize_models(cfg)
    check(set(models) == {"main", "ocr", "layout"}, "生成三个角色")
    check(models["ocr"]["provider"] == "ollama", "默认还是 Ollama")
    check(models["ocr"]["model"] == "glm-ocr:latest", "OCR 沿用旧模型")
    check(models["layout"]["model"] == "qwen3.5:4b", "排版沿用旧模型")
    check(models["main"]["model"] == "qwen3.5:4b", "主 LLM 空时退回排版模型")
    check(models["ocr"]["base_url"] == "http://127.0.0.1:11434", "沿用旧地址")


def test_cloud_profile():
    print("[云端配置]")
    cfg = {"models": {"ocr": {"provider": "bailian", "base_url": "",
                              "api_key": "sk-x", "model": "qwen-vl-max",
                              "timeout": "45", "stream": True}}}
    models = config.normalize_models(cfg)
    ocr = models["ocr"]
    check(ocr["base_url"].endswith("/compatible-mode/v1"), "空 BaseURL 自动补预置地址")
    check(ocr["timeout"] == 45 and ocr["stream"] is True, "超时/流式按配置")
    check(ocr["api_key"] == "sk-x", "Key 保留")
    check(models["main"]["provider"] == "ollama", "未配置的角色仍走 Ollama")


def test_save_models():
    print("[保存落点]")
    tmp = tempfile.mkdtemp(prefix="probe_models_save_")
    base = os.path.join(tmp, "config.json")
    models = {"ocr": {"provider": "deepseek", "model": "deepseek-chat",
                      "api_key": "sk-secret",
                      "base_url": "https://api.deepseek.com"},
              "layout": {"provider": "ollama", "model": "qwen3.5:4b",
                         "api_key": "", "base_url": "http://127.0.0.1:11434"},
              "main": {"provider": "ollama", "model": "qwen3.5:4b",
                       "api_key": "", "base_url": "http://127.0.0.1:11434"}}
    path = config.save_models(models, path=base)
    check(path.endswith("config.local.json"), "写进 config.local.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    check(data["models"]["ocr"]["api_key"] == "sk-secret", "Key 落盘")
    check(data.get("default_model") == "deepseek-chat", "同步旧键 default_model")
    check(not os.path.exists(base), "不创建受版本控制的 config.json")


def test_model_profile_helper():
    print("[model_profile]")
    cfg = {"models": {"main": {"provider": "kimi", "model": "kimi-k2",
                               "base_url": "https://api.moonshot.cn/v1"}}}
    profile = config.model_profile(cfg, "main")
    check(profile["provider"] == "kimi", "取到指定角色")
    profile = config.model_profile({"models": {}}, "ocr")
    check(profile["provider"] == "ollama", "缺省回退 Ollama")


def main():
    test_providers()
    test_legacy_migration()
    test_cloud_profile()
    test_save_models()
    test_model_profile_helper()
    if failures:
        print("\nFAILED %d 项：" % len(failures))
        for item in failures:
            print("  -", item)
        return 1
    print("\ntest_config_model OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
