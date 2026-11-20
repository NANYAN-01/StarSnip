"""Remote Ollama OCR core: generate/chat modes, grounding cleanup, diffing."""

import base64
import json
import re
import threading
import urllib.request

from . import tablefmt

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


def call(png_bytes: bytes, model: str, url: str, prompt: str = DEFAULT_PROMPT,
         mode: str = "auto", timeout: float = 60.0,
         keep_alive: str = "30m") -> dict:
    api = pick_mode(model, mode)
    img_b64 = base64.b64encode(png_bytes).decode("ascii")
    options = {"temperature": 0.1, "num_predict": 4096}
    if api == "chat":
        payload = {
            "model": model,
            "messages": [
                {"role": "system",
                 "content": "You are an OCR engine. Output only the text found in the image."},
                {"role": "user", "content": "<image>\n" + prompt,
                 "images": [img_b64]},
            ],
            "stream": False,
            "options": options,
            "keep_alive": keep_alive,
        }
        endpoint = url.rstrip("/") + "/api/chat"
    else:
        payload = {"model": model, "prompt": prompt, "images": [img_b64],
                   "stream": False, "options": options,
                   "keep_alive": keep_alive}
        endpoint = url.rstrip("/") + "/api/generate"

    started = time_ms()
    result = {"model": model, "mode": api, "ok": False,
              "text": "", "error": None, "elapsed_ms": 0}
    try:
        req = urllib.request.Request(
            endpoint, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("error"):
            raise RuntimeError(data["error"])
        if api == "chat":
            text = (data.get("message") or {}).get("content", "")
        else:
            text = data.get("response", "")
        text = clean_grounding(text.strip())
        if not text:
            raise RuntimeError("empty response")
        result.update(ok=True, text=text)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    result["elapsed_ms"] = int(time_ms() - started)
    return result


def call_many(png_bytes: bytes, models, url: str, prompt: str = DEFAULT_PROMPT,
              timeout: float = 60.0, keep_alive: str = "30m") -> list:
    results = [None] * len(models)

    def worker(idx, model):
        results[idx] = call(png_bytes, model, url, prompt=prompt,
                            timeout=timeout, keep_alive=keep_alive)

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
