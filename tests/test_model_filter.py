"""OCR 模型筛选与配置默认值测试（离线：不联网、不建窗口）。"""

import os
import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import config, ocr_core  # noqa: E402


def test_is_ocr_model():
    print("[is_ocr_model]")
    assert ocr_core.is_ocr_model("glm-ocr:latest", ["completion", "vision"])
    assert ocr_core.is_ocr_model(
        "richardyoung/unlimited-ocr:latest", ["completion", "vision"])
    assert ocr_core.is_ocr_model("longwayxu/xiaomi-ocr-0:bf16",
                                 ["tools", "vision"])
    # 通用视觉 / 对话模型不算 OCR 模型（设置里不该出现）
    assert not ocr_core.is_ocr_model("qwen3.5:4b",
                                     ["completion", "vision", "tools"])
    assert not ocr_core.is_ocr_model("qwen3-vl:8b", ["completion", "vision"])
    # 能力已知但不支持 vision：看不到图，不可能 OCR
    assert not ocr_core.is_ocr_model("glm-ocr:latest", ["completion"])
    # 老后端不返回 capabilities：只看名字，不能把列表清空
    assert ocr_core.is_ocr_model("glm-ocr:latest", [])
    assert ocr_core.is_ocr_model("glm-ocr:latest")
    print("  ✓ OCR / 视觉 / 对话模型区分正确")


def test_list_ocr_models_fallback():
    print("[list_ocr_models 兜底]")
    real = ocr_core.list_models_detail
    pages = [
        [{"name": "b-ocr:latest", "capabilities": ["completion", "vision"]},
         {"name": "a-ocr:latest", "capabilities": ["completion", "vision"]},
         {"name": "chat:7b", "capabilities": ["completion", "vision"]}],
        # 一个 OCR 模型都没装 -> 退回视觉模型
        [{"name": "vl:8b", "capabilities": ["completion", "vision"]},
         {"name": "coder:7b", "capabilities": ["completion"]}],
        # 连 capabilities 都没有 -> 退回全部
        [{"name": "x:1b", "capabilities": []}],
        [],
    ]
    try:
        seq = iter(pages)
        ocr_core.list_models_detail = lambda url, timeout=6.0: next(seq)
        assert ocr_core.list_ocr_models("http://x") ==             ["a-ocr:latest", "b-ocr:latest"]
        assert ocr_core.list_ocr_models("http://x") == ["vl:8b"]
        assert ocr_core.list_ocr_models("http://x") == ["x:1b"]
        assert ocr_core.list_ocr_models("http://x") == []
    finally:
        ocr_core.list_models_detail = real
    print("  ✓ 只列 OCR 模型；没有时依次退回视觉模型 / 全部 / 空")


def test_offline_backend():
    print("[后端不可用]")
    url = "http://127.0.0.1:1"
    assert ocr_core.list_ocr_models(url, timeout=0.5) == []
    assert ocr_core.list_models_detail(url, timeout=0.5) == []
    print("  ✓ 拉不到模型时返回空列表，不抛异常")


def test_config_defaults():
    print("[config 默认值]")
    assert config.DEFAULTS["prompt"] == ocr_core.DEFAULT_PROMPT
    assert config.DEFAULTS["table_prompt"] == ocr_core.TABLE_PROMPT
    for gone in ("auto_ocr", "joint_enabled", "joint_models"):
        assert gone not in config.DEFAULTS, gone
    cfg = config.load()
    assert cfg["layout_model"], "排版/翻译模型必须有默认值"
    assert cfg["verify_models"], "交叉校验需要对照模型"
    print("  ✓ 提示词单源；联合识别 / auto_ocr 已移除；排版模型有默认值")


def main():
    test_is_ocr_model()
    test_list_ocr_models_fallback()
    test_offline_backend()
    test_config_defaults()
    print("test_model_filter OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
