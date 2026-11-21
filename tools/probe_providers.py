r"""厂商连通性自测（开发工具）：读你的 API 表格，逐个厂商跑一次 chat。

用法：
    python tools\probe_providers.py "D:\path\01My Model API.xlsx"
    python tools\probe_providers.py "D:\path\01My Model API.xlsx" --vision

- 表格按列名取：序号 / 归属 / 名称 / 服务商/平台 / Base URL / API Key / 包含模型
- Key 只在内存里用，屏幕输出一律打码（前 6 位 + 后 4 位）
- --vision 额外发一张带文字的图片，验证「OCR 角色」能不能用（需要 Pillow）

依赖 openpyxl（只在这个工具里需要，主程序不依赖）：
    pip install openpyxl
"""

import base64
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from starsnip import llm  # noqa: E402

SKIP_MODEL = re.compile(
    r"(asr|tts|speech|voice|embedding|rerank|bge|cosy|paraformer|sensevoice"
    r"|whisper|image-|video|seedream|seedance)", re.I)


def mask(value):
    text = str(value or "").strip()
    return text[:6] + "…" + text[-4:] if len(text) > 12 else text


def clean_url(text):
    match = re.search(r"https?://[^\s（(）)\]]+", str(text or ""))
    return match.group(0).rstrip("/") if match else ""


def read_rows(path):
    import openpyxl

    book = openpyxl.load_workbook(path, data_only=True)
    sheet = book[book.sheetnames[1]] if len(book.sheetnames) > 1 else book.active
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c) if c is not None else "" for c in rows[0]]
    index = {name: i for i, name in enumerate(header)}

    def get(row, name):
        return row[index[name]] if name in index else ""

    out = []
    for row in rows[1:]:
        if not any(row):
            continue
        models = [m.strip() for m in re.split(r"[、,，]", str(get(row, "包含模型") or ""))
                  if m.strip()]
        entry = {
            "id": str(get(row, "序号") or ""),
            "owner": str(get(row, "归属") or ""),
            "name": str(get(row, "名称") or ""),
            "vendor": str(get(row, "服务商/平台") or ""),
            "base": clean_url(get(row, "Base URL")),
            "key": str(get(row, "API Key") or "").strip().lstrip("\u200b"),
            "models": models,
        }
        if entry["base"] and entry["key"]:
            out.append(entry)
    return out


def profile_of(entry, model=""):
    return {"provider": "custom", "base_url": entry["base"],
            "api_key": entry["key"], "model": model, "timeout": 30,
            "stream": False, "auth_header": "Authorization",
            "auth_prefix": "Bearer "}


def chat_once(entry, model):
    started = time.time()
    try:
        reply = llm.chat(profile_of(entry, model),
                         [{"role": "user", "content": "只回复 OK 两个字母"}])
        return True, reply.get("text", "")[:40], int((time.time() - started) * 1000), ""
    except Exception as exc:  # noqa: BLE001
        return False, "", int((time.time() - started) * 1000), str(exc)[:160]


def probe_chat(entry):
    tried = []
    for model in ([m for m in entry["models"]
                   if not SKIP_MODEL.search(m)] or entry["models"])[:2]:
        ok, text, ms, err = chat_once(entry, model)
        tried.append({"model": model, "ok": ok, "ms": ms, "error": err})
        if ok:
            return True, model, tried
    try:
        names = llm.list_models(profile_of(entry), timeout=20)
    except Exception as exc:  # noqa: BLE001
        tried.append({"model": "<list_models>", "ok": False, "ms": 0,
                      "error": str(exc)[:120]})
        names = []
    for name in names[:2]:
        if name in [t["model"] for t in tried]:
            continue
        ok, text, ms, err = chat_once(entry, name)
        tried.append({"model": name, "ok": ok, "ms": ms, "error": err})
        if ok:
            return True, name, tried
    # Ollama 的 OpenAI 兼容入口在 /v1 下：表里只写了主机+端口时补一次
    base = entry["base"]
    if ":11434" in base and not base.rstrip("/").endswith("/v1"):
        entry = dict(entry, base=base.rstrip("/") + "/v1")
        for name in [m for m in entry["models"]
                     if not SKIP_MODEL.search(m)][:2]:
            ok, text, ms, err = chat_once(entry, name)
            tried.append({"model": name + " @/v1", "ok": ok, "ms": ms,
                          "error": err})
            if ok:
                return True, name + "（经 /v1）", tried
    return False, "", tried


def probe_vision(entry):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False, "需要 Pillow 才能测图片"
    image = Image.new("RGB", (260, 90), "white")
    ImageDraw.Draw(image).text((20, 32), "HELLO 123", fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode()

    candidates = []
    for model in entry["models"]:
        if re.search(r"(vl|vision|ocr|omni|seed-1-6|seed-2|doubao)", model, re.I) \
                and not SKIP_MODEL.search(model):
            candidates.append(model)
    try:
        names = llm.list_models(profile_of(entry), timeout=20)
        candidates += [n for n in names if re.search(r"(vl|vision|ocr)", n, re.I)][:3]
    except Exception:  # noqa: BLE001
        pass
    for model in candidates[:3]:
        try:
            text = llm.generate(profile_of(entry, model), "只输出图片里的文字",
                                images=[data], timeout=60)
            if re.search(r"HELLO|123", text or "", re.I):
                return True, model
        except Exception:  # noqa: BLE001
            continue
    return False, "没有模型读出图片文字"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    want_vision = "--vision" in argv[2:]
    rows = read_rows(path)
    print("共 %d 条可用配置（Key 已打码）\n" % len(rows))
    failed = 0
    for entry in rows:
        ok, model, tried = probe_chat(entry)
        line = "#%s %-12s %-24s %s" % (entry["id"], entry["name"][:12],
                                       entry["vendor"][:24],
                                       ("OK  " + model) if ok else "FAIL")
        if not ok:
            failed += 1
            line += "  | " + (tried[-1]["error"] if tried else "")
        print(line)
        if ok and want_vision:
            vok, vdetail = probe_vision(entry)
            print("      vision: %s %s" % ("OK" if vok else "FAIL", vdetail))
        if not ok:
            for item in tried[-2:]:
                print("      tried %s: %s" % (item["model"], item["error"]))
    print("\n失败 %d 条" % failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
