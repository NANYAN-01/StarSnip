"""Remote Ollama OCR core: generate/chat modes, grounding cleanup, diffing."""

import base64
import json
import re
import threading
import urllib.request

from . import llm, tablefmt

OCR_SYSTEM = "You are an OCR engine. Output only the text found in the image."

DEFAULT_PROMPT = (
    "请识别图片中的所有文字内容，按原样逐行输出，不要遗漏，不要翻译。"
    "表格请保持行列对齐。"
)

TABLE_PROMPT = (
    "请将图片中的表格转换为 Markdown 表格，包含表头与所有数据行，"
    "保留合计行，数字不得遗漏或改动。只输出 Markdown。"
)

GROUNDING_RE = re.compile(r"^\s*[A-Za-z_]+\s*\[\s*\d+(?:\s*,\s*\d+){2,3}\s*\]\s*")
GROUNDING_TOKEN_RE = re.compile(r"<\|[^|]*\|>")
STRUCT_TAG_RE = re.compile(
    r"</?(?:table|thead|tbody|tfoot|tr|td|th|figure|text|title|list|equation"
    r"|header|footer|reference|formula)\b[^>]*>",
    re.IGNORECASE,
)


def pick_mode(model: str, mode: str = "auto") -> str:
    if mode in ("generate", "chat"):
        return mode
    return "chat" if "unlimited-ocr" in model.lower() else "generate"


def clean_grounding(text: str) -> str:
    # glm-ocr 对表格可能直接输出 HTML 片段：先转 Markdown，再清定位/结构标签，
    # 否则文本视图和导出都会拿到 <tr><td> 一类的标签。
    text = tablefmt.html_to_markdown(text or "")
    lines = []
    for line in text.splitlines():
        line = GROUNDING_TOKEN_RE.sub("", line)
        line = GROUNDING_RE.sub("", line)
        line = STRUCT_TAG_RE.sub("", line)
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines)


def _profile(model: str, url: str) -> dict:
    """老调用方（只给 model + url）→ 一个 Ollama 角色配置。"""
    return {"provider": "ollama", "base_url": url, "api_key": "",
            "model": model or "", "timeout": 60, "stream": False}


def call(png_bytes: bytes, model: str = None, url: str = None,
         prompt: str = DEFAULT_PROMPT, mode: str = "auto",
         timeout: float = 60.0, keep_alive: str = "30m",
         profile: dict = None) -> dict:
    """识别一张图。

    profile 决定走哪家：Ollama 走原生接口（generate / chat 两模式），
    云端一律 OpenAI 兼容的 chat/completions（图片以 data URL 传）。
    """
    profile = profile or _profile(model, url)
    model = (profile.get("model") or model or "")
    local = llm.is_ollama(profile)
    api = pick_mode(model, mode) if local else "openai"
    img_b64 = base64.b64encode(png_bytes).decode("ascii")

    started = time_ms()
    result = {"model": model, "mode": api, "ok": False,
              "text": "", "error": None, "elapsed_ms": 0,
              "provider": profile.get("provider") or "ollama"}
    try:
        text = llm.generate(profile, prompt, system=OCR_SYSTEM,
                            images=[img_b64], timeout=timeout,
                            keep_alive=keep_alive, ollama_mode=api)
        text = clean_grounding((text or "").strip())
        if not text:
            raise RuntimeError("empty response")
        result.update(ok=True, text=text)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        result["error"] = str(exc) if isinstance(exc, llm.LLMError) \
            else "%s: %s" % (type(exc).__name__, exc)
    result["elapsed_ms"] = int(time_ms() - started)
    return result


def call_many(png_bytes: bytes, models, url: str = None,
              prompt: str = DEFAULT_PROMPT, timeout: float = 60.0,
              keep_alive: str = "30m", profile: dict = None) -> list:
    results = [None] * len(models)

    def worker(idx, model):
        base = dict(profile or _profile(model, url))
        base["model"] = model
        results[idx] = call(png_bytes, prompt=prompt, timeout=timeout,
                            keep_alive=keep_alive, profile=base)

    threads = [threading.Thread(target=worker, args=(i, m), daemon=True)
               for i, m in enumerate(models)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def disagreements(primary_text: str, other_texts) -> set:
    """Indices of primary lines that are missing from at least one other text."""
    lines = [ln for ln in (primary_text or "").splitlines() if ln.strip()]
    others = [_norm(t) for t in other_texts if t]
    bad = set()
    for idx, line in enumerate(lines):
        norm = _norm(line)
        if not any(norm in other for other in others):
            bad.add(idx)
    return bad


def time_ms() -> float:
    import time
    return time.time() * 1000.0


def list_models_detail(url: str, timeout: float = 6.0) -> list:
    """列出后端模型及其能力：[{name, capabilities, family}]。失败返回 []。"""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/tags",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 后端不可用时只是没得选
        return []
    items = []
    for item in (data.get("models") or []):
        name = item.get("name")
        if not name:
            continue
        details = item.get("details") or {}
        items.append({"name": name,
                      "capabilities": list(item.get("capabilities") or []),
                      "family": details.get("family") or ""})
    return items


def is_ocr_model(name: str, capabilities=None) -> bool:
    """OCR 专用模型判定：名字里带 ocr（glm-ocr / unlimited-ocr / xiaomi-ocr…）。

    capabilities 来自 /api/tags；已知能力时必须有 vision（看不到图不可能 OCR）。
    老版本后端不返回 capabilities，此时只看名字，避免把列表清空。
    """
    caps = [str(c).lower() for c in (capabilities or [])]
    if caps and "vision" not in caps:
        return False
    return "ocr" in (name or "").lower()


def list_candidates(profile: dict, timeout: float = 8.0) -> list:
    """按角色配置拉候选模型：Ollama 走 /api/tags 过滤，云端走 /models。"""
    if llm.is_ollama(profile):
        return list_ocr_models((profile or {}).get("base_url") or "", timeout)
    try:
        return llm.list_models(profile, timeout=timeout)
    except Exception:  # noqa: BLE001 - 拉不到就让人手填
        return []


def list_ocr_models(url: str, timeout: float = 6.0) -> list:
    """设置里 OCR 下拉的候选：优先只给 OCR 模型。

    一个 OCR 模型都没装时退回「支持视觉的模型」，再退回全部模型，
    免得下拉框空着让人以为后端挂了（提示文案会说明）。
    """
    items = list_models_detail(url, timeout)
    if not items:
        return []
    ocr = [i["name"] for i in items
           if is_ocr_model(i["name"], i["capabilities"])]
    if ocr:
        return sorted(ocr)
    vision = [i["name"] for i in items
              if "vision" in [str(c).lower() for c in i["capabilities"]]]
    if vision:
        return sorted(vision)
    return sorted(i["name"] for i in items)
