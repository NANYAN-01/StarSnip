"""llm.py 离线单测：URL 拼接 / 鉴权头 / 非流式 / 流式 / 错误翻译 / Ollama 原生。"""

import io
import json
import os
import sys
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from starsnip import llm  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  x %s" % msg)
    else:
        print("  v %s" % msg)


class FakeResp:
    def __init__(self, body=b"", lines=None):
        self._body = body
        self._lines = lines or []

    def read(self):
        return self._body

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def profile(**kw):
    base = {"provider": "deepseek", "base_url": "https://api.deepseek.com",
            "api_key": "sk-test", "model": "deepseek-chat", "timeout": 30,
            "stream": False, "auth_header": "Authorization",
            "auth_prefix": "Bearer "}
    base.update(kw)
    return base


def with_fake(resp):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8")) if req.data else None
        if isinstance(resp, Exception):
            raise resp
        return resp

    llm.urllib.request.urlopen = fake_urlopen
    return captured


def hdr(captured, name):
    """urllib 会把头名首字母大写（X-Api-Key → X-api-key），按不区分大小写取。"""
    for key, value in (captured.get("headers") or {}).items():
        if str(key).lower() == name.lower():
            return value
    return None


def test_chat_basic():
    print("[chat 非流式]")
    body = json.dumps({"choices": [{"message": {"content": "你好"}}],
                       "model": "deepseek-chat",
                       "usage": {"total_tokens": 3}}).encode()
    captured = with_fake(FakeResp(body))
    out = llm.chat(profile(), [{"role": "user", "content": "hi"}])
    check(out["text"] == "你好", "取到 choices[0].message.content")
    check(captured["url"] == "https://api.deepseek.com/chat/completions",
          "URL 拼对了：%s" % captured["url"])
    check(hdr(captured, "Authorization") == "Bearer sk-test",
          "带上 Bearer 鉴权头")
    check(captured["body"]["model"] == "deepseek-chat"
          and captured["body"]["stream"] is False, "payload 正确")


def test_base_with_v1():
    print("[BaseURL 已带 /v1]")
    captured = with_fake(FakeResp(json.dumps(
        {"choices": [{"message": {"content": "ok"}}]}).encode()))
    llm.chat(profile(base_url="https://api.moonshot.cn/v1"), [{"role": "user", "content": "x"}])
    check(captured["url"] == "https://api.moonshot.cn/v1/chat/completions",
          "不重复拼 /v1：%s" % captured["url"])


def test_content_parts():
    print("[content 数组]")
    body = json.dumps({"choices": [{"message": {"content": [
        {"type": "text", "text": "A"}, {"type": "text", "text": "B"}]}}]}).encode()
    with_fake(FakeResp(body))
    out = llm.chat(profile(), [{"role": "user", "content": "x"}])
    check(out["text"] == "AB", "数组形式的内容拼接")


def test_stream():
    print("[stream 流式]")
    lines = [
        b'data: {"choices":[{"delta":{"content":"He"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n',
        b"data: [DONE]\n",
    ]
    with_fake(FakeResp(b"", lines=lines))
    deltas = []
    out = llm.chat(profile(stream=True), [{"role": "user", "content": "x"}],
                   on_delta=deltas.append)
    check(out["text"] == "Hello", "SSE 增量拼成完整文本")
    check(deltas == ["He", "llo"], "on_delta 逐段回调：%s" % (deltas,))


def test_error():
    print("[错误翻译]")
    err = urllib.error.HTTPError(
        "https://api.deepseek.com/chat/completions", 401, "Unauthorized", {},
        io.BytesIO(b'{"error":{"message":"invalid api key"}}'))
    with_fake(err)
    try:
        llm.chat(profile(), [{"role": "user", "content": "x"}])
        check(False, "401 应抛错")
    except llm.LLMError as exc:
        check("API Key" in str(exc), "401 → 提示 API Key 无效（%s）" % exc)


def test_ollama_generate():
    print("[Ollama 原生]")
    captured = with_fake(FakeResp(json.dumps({"response": "文字"}).encode()))
    out = llm.generate({"provider": "ollama", "base_url": "http://127.0.0.1:11434",
                        "model": "glm-ocr:latest", "timeout": 30},
                       "识别", images=["AAA"], think=False)
    check(out == "文字", "Ollama /api/generate 返回")
    check(captured["url"].endswith("/api/generate"), "走原生 generate 接口")
    check(captured["body"]["images"] == ["AAA"], "图片按 base64 传给 Ollama")


def test_list_models():
    print("[模型列表]")
    captured = with_fake(FakeResp(json.dumps(
        {"data": [{"id": "b-model"}, {"id": "a-model"}]}).encode()))
    names = llm.list_models(profile(), timeout=5)
    check(names == ["a-model", "b-model"], "云端 /models 排序返回")
    check(captured["url"].endswith("/models"), "GET /models")
    with_fake(FakeResp(json.dumps(
        {"models": [{"name": "glm-ocr:latest"}]}).encode()))
    names = llm.list_models({"provider": "ollama",
                             "base_url": "http://127.0.0.1:11434"}, timeout=5)
    check(names == ["glm-ocr:latest"], "Ollama /api/tags")


def test_custom_auth():
    print("[自定义鉴权头]")
    captured = with_fake(FakeResp(json.dumps(
        {"choices": [{"message": {"content": "ok"}}]}).encode()))
    llm.chat(profile(provider="custom", base_url="https://x.example/v1",
                     api_key="abc", auth_header="X-Api-Key",
                     auth_prefix=""), [{"role": "user", "content": "x"}])
    check(hdr(captured, "X-Api-Key") == "abc",
          "自定义头名 + 空前缀")


def main():
    test_chat_basic()
    test_base_with_v1()
    test_content_parts()
    test_stream()
    test_error()
    test_ollama_generate()
    test_list_models()
    test_custom_auth()
    if failures:
        print("\nFAILED %d 项：" % len(failures))
        for item in failures:
            print("  -", item)
        return 1
    print("\ntest_llm OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
