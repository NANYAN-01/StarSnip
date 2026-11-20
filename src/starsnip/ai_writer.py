"""AI layout: general LLM turns OCR text into Markdown, then export to docx/xlsx/txt/md."""

import json
import urllib.request

from . import mdblocks, screenfiles, tablefmt
from .writers import docx as docx_writer
from .writers import xlsx as xlsx_writer

LAYOUT_PROMPT = (
    "你是文档排版助手。将下面 OCR 识别出的文本整理为规范的 Markdown 文档：\n"
    "1) 不增删任何事实、数字、字段，只做排版；\n"
    "2) 使用 # 标题层级、段落、- 列表、Markdown 表格；\n"
    "3) 表格必须保留全部行列与数值（包括合计行）；\n"
    "4) 只输出 Markdown 正文，不要解释。\n\n---\n"
)

FORMATS = ("docx", "txt", "xlsx", "md")


def llm_layout(text: str, model: str, url: str, timeout: float = 120.0,
               keep_alive: str = "30m") -> str:
    payload = {
        "model": model,
        "prompt": LAYOUT_PROMPT + (text or ""),
        "stream": False,
        # explicit think:false is ~16x faster on qwen3.5 (65s -> 4s)
        "think": False,
        "keep_alive": keep_alive,
        "options": {"temperature": 0.1, "num_predict": 4096},
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError(data["error"])
    md = (data.get("response") or "").strip()
    if not md:
        raise RuntimeError("empty layout response")
    return md


def layout_markdown(text: str, model: str, url: str, timeout: float = 120.0,
                    keep_alive: str = "30m") -> str:
    """Layout via LLM; falls back to the raw OCR text on any failure."""
    try:
        return llm_layout(text, model, url, timeout, keep_alive=keep_alive)
    except Exception:  # noqa: BLE001
        return text


def blocks_to_text(blocks) -> str:
    out = []
    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            out.append(block["text"])
        elif kind == "paragraph":
            out.append(block["text"])
        elif kind == "list":
            out.extend("- " + item for item in block["items"])
        elif kind == "table":
            out.extend("\t".join(row) for row in block["rows"])
        out.append("")
    return "\n".join(out).strip() + "\n"


def export(text: str, fmt: str, model: str, url: str, directory: str = None,
           timeout: float = 120.0, keep_alive: str = "30m") -> tuple:
    """Returns (file_path, markdown_used).

    文本里已经有结构化表格（Markdown / HTML）时，直接按行列本地生成：
    不让大模型重写表格，避免它改数字、并错列或把表格改坏（表格页最常见）。
    只有普通文本才走 AI 排版。
    """
    if fmt not in FORMATS:
        raise ValueError("unsupported format: %s" % fmt)
    rows = tablefmt.structured_table(text)
    if rows:
        md = text
        blocks = mdblocks.parse_blocks(md)
        if not any(b["type"] == "table" for b in blocks):
            blocks.append({"type": "table", "rows": rows})
    else:
        md = layout_markdown(text, model, url, timeout, keep_alive=keep_alive)
        blocks = mdblocks.parse_blocks(md)
    if fmt == "md":
        # 对齐列文本导 .md 时补成 Markdown 表格；本来就是 Markdown 则原样保留
        data = (md if rows is None or "|" in md
                else tablefmt.to_markdown(rows)).encode("utf-8")
    elif fmt == "txt":
        data = blocks_to_text(blocks).encode("utf-8")
    elif fmt == "docx":
        data = docx_writer.build_docx(blocks)
    else:
        tables = [b["rows"] for b in blocks if b["type"] == "table"]
        if tables:
            sheets = tables
        else:
            sheets = [[[line] for line in blocks_to_text(blocks).splitlines()]]
        data = xlsx_writer.build_xlsx(sheets)
    path = screenfiles.save_bytes(data, directory, fmt)
    return path, md


# ---------- 翻译（复用通用对话模型，自动判定中<->英方向） ----------
import re  # noqa: E402

_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def _detect_lang(text: str) -> str:
    return "zh" if _CJK_RE.search(text or "") else "en"


def translate(text: str, model: str, url: str, target: str = "auto",
              timeout: float = 120.0, keep_alive: str = "30m") -> tuple:
    """翻译 OCR 文本。target: auto/en/zh。返回 (译文, 目标语言码)。"""
    src = _detect_lang(text)
    tgt = target if target in ("en", "zh") else ("en" if src == "zh" else "zh")
    tgt_name = "中文" if tgt == "zh" else "English"
    prompt = (
        "你是专业翻译。把下面的文本翻译成%s。"
        "保留原有换行、表格与列表结构，只输出译文，不要解释。\n\n---\n%s"
        % (tgt_name, text or "")
    )
    payload = {
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "keep_alive": keep_alive,
        "options": {"temperature": 0.2, "num_predict": 4096},
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError(data["error"])
    out = (data.get("response") or "").strip()
    if not out:
        raise RuntimeError("empty translation")
    return out, tgt
