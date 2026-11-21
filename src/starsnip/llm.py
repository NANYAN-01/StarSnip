"""统一的 OpenAI 兼容调用层（chat/completions，可选 SSE 流式）。

- 云端厂商一律走标准 OpenAI 协议：POST {base_url}/chat/completions
- Ollama（本地）继续走它自己的 /api/generate、/api/chat：
  本机不需要 Key，而且原生接口对图片、think、keep_alive 的控制更细。
- 只依赖标准库（urllib），不引入 requests。
"""

import base64
import json
import urllib.error
import urllib.request

from . import providers


class LLMError(RuntimeError):
    """给界面看的错误：已经翻译成人话。"""


_HINTS = {
    400: "请求被拒绝，多半是模型名或参数不对",
    401: "API Key 无效或没填",
    403: "无权限 / 额度不足",
    404: "BaseURL 写错了，或该厂商没有这个模型",
    429: "限流或额度不足（检查余额 / 套餐）",
    500: "服务端错误，稍后再试",
    503: "服务暂时不可用",
}


def is_ollama(profile: dict) -> bool:
    return providers.is_ollama((profile or {}).get("provider") or "ollama")


def _model(profile: dict) -> str:
    model = (profile.get("model") or "").strip()
    if not model:
        raise LLMError("没有填模型名")
    return model


def _base(profile: dict) -> str:
    base = (profile.get("base_url") or "").strip()
    if not base:
        base = providers.base_url((profile or {}).get("provider") or "ollama")
    if not base:
        raise LLMError("没有填 BaseURL")
    return base.rstrip("/")


def _headers(profile: dict) -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8",
               "Accept": "application/json"}
    key = (profile.get("api_key") or "").strip()
    if key:
        name = (profile.get("auth_header") or "Authorization").strip()
        prefix = profile.get("auth_prefix")
        prefix = "Bearer " if prefix is None else prefix
        headers[name or "Authorization"] = (prefix + key).strip()
    return headers


def _url(profile: dict, suffix: str) -> str:
    base = _base(profile)
    return base if base.endswith(suffix) else base + suffix


def _timeout(profile: dict, fallback: float) -> float:
    try:
        value = float(profile.get("timeout") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else fallback


def _http_error(exc: urllib.error.HTTPError) -> LLMError:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        body = ""
    message = body.strip()[:300]
    try:
        data = json.loads(body)
        err = data.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or message)
        elif isinstance(err, str):
            message = err
        elif data.get("message"):
            message = str(data["message"])
    except ValueError:
        pass
    hint = _HINTS.get(exc.code, "")
    return LLMError("%s（HTTP %s）%s" % (message or "请求失败", exc.code,
                                       ("｜" + hint) if hint else ""))


def _content_text(content) -> str:
    """OpenAI 的 content 可能是字符串，也可能是 [{type:text,...}] 数组。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("text", "output_text"):
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


def _post(url: str, payload: dict, headers: dict, timeout: float):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from None
    except urllib.error.URLError as exc:
        raise LLMError("连不上服务：%s" % (exc.reason,)) from None
    except OSError as exc:
        raise LLMError("网络错误：%s" % exc) from None


# ---------- 云端：OpenAI 协议 ----------
def chat(profile: dict, messages, timeout: float = None, stream: bool = None,
         on_delta=None) -> dict:
    """OpenAI /chat/completions。返回 {text, usage, model}。"""
    model = _model(profile)
    use_stream = bool(profile.get("stream") if stream is None else stream)
    payload = {"model": model, "messages": messages, "stream": use_stream}
    url = _url(profile, "/chat/completions")
    limit = _timeout(profile, timeout or 60)

    if not use_stream:
        resp = _post(url, payload, _headers(profile), limit)
        try:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        finally:
            resp.close()
        if data.get("error"):
            raise LLMError(str(data["error"]))
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("模型没有返回内容")
        text = _content_text((choices[0].get("message") or {}).get("content"))
        return {"text": text, "usage": data.get("usage") or {},
                "model": data.get("model") or model}

    resp = _post(url, payload, _headers(profile), limit)
    parts = []
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            if data.get("error"):
                raise LLMError(str(data["error"]))
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = _content_text(delta.get("content"))
            if piece:
                parts.append(piece)
                if on_delta:
                    on_delta(piece)
    finally:
        resp.close()
    return {"text": "".join(parts), "usage": {}, "model": model}


def _ollama_generate(profile: dict, prompt: str, system: str = None,
                     images=None, think: bool = False,
                     keep_alive: str = "30m", timeout: float = None) -> str:
    payload = {"model": _model(profile), "prompt": prompt, "stream": False,
               "keep_alive": keep_alive,
               "options": {"temperature": 0.1, "num_predict": 4096}}
    if think is not None:
        payload["think"] = bool(think)
    if system:
        payload["system"] = system
    if images:
        payload["images"] = list(images)
    resp = _post(_url(profile, "/api/generate"), payload, _headers(profile),
                 _timeout(profile, timeout or 60))
    try:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    finally:
        resp.close()
    if data.get("error"):
        raise LLMError(str(data["error"]))
    return (data.get("response") or "").strip()


def _ollama_chat(profile: dict, prompt: str, system: str = None,
                 images=None, keep_alive: str = "30m",
                 timeout: float = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    user = {"role": "user", "content": prompt}
    if images:
        user["images"] = list(images)
    messages.append(user)
    payload = {"model": _model(profile), "messages": messages, "stream": False,
               "keep_alive": keep_alive,
               "options": {"temperature": 0.1, "num_predict": 4096}}
    resp = _post(_url(profile, "/api/chat"), payload, _headers(profile),
                 _timeout(profile, timeout or 60))
    try:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    finally:
        resp.close()
    if data.get("error"):
        raise LLMError(str(data["error"]))
    return ((data.get("message") or {}).get("content") or "").strip()


def generate(profile: dict, prompt: str, system: str = None, images=None,
             timeout: float = None, think: bool = False,
             keep_alive: str = "30m", on_delta=None,
             ollama_mode: str = "generate") -> str:
    """一次性拿完整文本：云端走 chat/completions，本地走 Ollama 原生接口。"""
    if is_ollama(profile):
        if ollama_mode == "chat":
            return _ollama_chat(profile, prompt, system=system, images=images,
                                keep_alive=keep_alive, timeout=timeout)
        return _ollama_generate(profile, prompt, system=system, images=images,
                                think=think, keep_alive=keep_alive,
                                timeout=timeout)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if images:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64,%s" % img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    return chat(profile, messages, timeout=timeout, on_delta=on_delta)["text"]


def generate_vision(profile: dict, png_bytes: bytes, prompt: str,
                    system: str = None, timeout: float = None) -> str:
    """图片 + 文本：本地转 base64 给 Ollama，云端用 image_url data URL。"""
    img = base64.b64encode(png_bytes).decode("ascii")
    return generate(profile, prompt, system=system, images=[img],
                    timeout=timeout)


def list_models(profile: dict, timeout: float = 8.0) -> list:
    """拉模型清单：Ollama 用 /api/tags，云端用 /models（OpenAI 协议）。"""
    if is_ollama(profile):
        req = urllib.request.Request(_base(profile) + "/api/tags",
                                     headers=_headers(profile))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from None
        except OSError as exc:
            raise LLMError("连不上 Ollama：%s" % exc) from None
        return sorted(str(m.get("name")) for m in (data.get("models") or [])
                      if m.get("name"))
    req = urllib.request.Request(_url(profile, "/models"),
                                 headers=_headers(profile))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from None
    except OSError as exc:
        raise LLMError("连不上服务：%s" % exc) from None
    items = data.get("data") if isinstance(data, dict) else None
    names = []
    for item in (items or []):
        name = item.get("id") or item.get("name")
        if name:
            names.append(str(name))
    return sorted(names)


def probe(profile: dict, timeout: float = 10.0) -> tuple:
    """「测试连接」：能列出模型就算通；列不出来就看具体错误。"""
    try:
        names = list_models(profile, timeout=timeout)
    except LLMError as exc:
        return False, str(exc)
    if names:
        return True, "连接正常，可用模型 %d 个" % len(names)
    return True, "连接正常（接口未返回模型列表，可直接手填模型名）"
