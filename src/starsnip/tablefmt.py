"""Table text parsing: markdown / HTML tables or space/tab aligned columns.

OCR 模型对表格的输出版式不统一：`glm-ocr` 有时给 Markdown 管道表，有时给
`<tr><td>…` 的 HTML 片段（没有 `<table>` 包裹也会出现）。这里统一成行列表，
并把 HTML 表格转成 Markdown，避免表格视图/导出拿到一坨标签。
"""

import html
import re

_SEPARATOR = re.compile(r"^:?-{2,}:?$")
_SPLIT_GAP = re.compile(r"\s{2,}|\t+")

_HTML_HINT = re.compile(r"<\s*(?:table|thead|tbody|tr|td|th)\b", re.IGNORECASE)
_HTML_TABLE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_HTML_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HTML_CELL = re.compile(r"<(t[hd])\b([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_STRUCT_TAG = re.compile(
    r"</?(?:table|thead|tbody|tfoot|tr|td|th)\b[^>]*>", re.IGNORECASE)
_COLSPAN = re.compile(r'colspan\s*=\s*["\']?\s*(\d+)', re.IGNORECASE)


def _clean_fences(text: str) -> list:
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        lines.append(line.rstrip())
    return lines


def parse_table(text: str):
    """Return list of rows (list of cells) or None if not a table."""
    rows, _titles = html_table(text)
    if rows:
        return rows
    rows = _parse_markdown(_clean_fences(text))
    if rows:
        return rows
    return _parse_aligned(_clean_fences(text)) or None


# ---------- HTML 表格 ----------
def _clean_cell(raw: str) -> str:
    text = _HTML_TAG.sub("", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "｜")      # 单元格里的竖线会破坏 Markdown 表格


def html_table(text: str):
    """解析 HTML 表格片段，返回 (rows, titles)。

    跨整行的合并单元格（`<td colspan="4">标题</td>`）是标题而非表头，
    单独放进 titles，避免表格视图把标题行当成列名。
    """
    if not _HTML_HINT.search(text or ""):
        return [], []
    blocks = list(_HTML_TABLE.finditer(text))
    if blocks:                          # 多张 HTML 表：表格视图只看第一张
        text = blocks[0].group(0)
    rows, spans = [], []
    for row_match in _HTML_ROW.finditer(text):
        cells, row_spans = [], []
        for cell_match in _HTML_CELL.finditer(row_match.group(1)):
            cells.append(_clean_cell(cell_match.group(3)))
            span = _COLSPAN.search(cell_match.group(2) or "")
            row_spans.append(max(1, int(span.group(1))) if span else 1)
        if cells:
            rows.append(cells)
            spans.append(row_spans)
    if len(rows) < 2:
        return [], []

    width = max(sum(s) for s in spans)
    titles, keep, keep_spans = [], [], []
    for cells, row_spans in zip(rows, spans):
        if len(cells) == 1 and width >= 2 and sum(row_spans) >= width:
            titles.append(cells[0])
            continue
        keep.append(cells)
        keep_spans.append(row_spans)
    if len(keep) < 2:                   # 全被当成标题：退回原样
        keep, keep_spans, titles = rows, spans, []

    expanded = []
    for cells, row_spans in zip(keep, keep_spans):
        out = []
        for cell, span in zip(cells, row_spans):
            out.append(cell)
            out.extend([""] * (span - 1))
        expanded.append(out)
    width = max(len(r) for r in expanded)
    return [r + [""] * (width - len(r)) for r in expanded], titles


def html_to_markdown(text: str) -> str:
    """把文本里的 HTML 表格换成 Markdown 表格；没有 HTML 表格时原样返回。"""
    if not _HTML_HINT.search(text or ""):
        return text

    def _replace(match):
        rows, titles = html_table(match.group(0))
        if not rows:
            return match.group(0)
        head = "\n".join(titles)
        return (head + "\n" if head else "") + to_markdown(rows)

    converted = _HTML_TABLE.sub(_replace, text)
    if converted != text:
        # 去掉表格块外面的 <thead>/<tbody> 等包裹，否则会把 Markdown 首行顶歪
        return _HTML_STRUCT_TAG.sub("", converted)

    # 没有 <table> 包裹的裸 <tr> 片段（glm-ocr 常见输出）
    rows, titles = html_table(text)
    if not rows:
        return text
    first = re.search(r"<tr\b", text, re.IGNORECASE)
    ends = list(re.finditer(r"</tr>", text, re.IGNORECASE))
    if not first or not ends:
        return text
    head = "\n".join(titles)
    body = (head + "\n" if head else "") + to_markdown(rows)
    out = text[:first.start()] + body + text[ends[-1].end():]
    return _HTML_STRUCT_TAG.sub("", out)


def structured_table(text: str):
    """只认 Markdown / HTML 表格（不做空格对齐推断）。

    导出等「确定性」路径用它：普通文本里的对齐空格可能被误判成表格，
    宁可交给 AI 排版，也不要把一段散文导成表格。
    """
    rows, _titles = html_table(text)
    if rows:
        return rows
    return _parse_markdown(_clean_fences(text)) or None


def parse_markdown(lines) -> list:
    """Public wrapper: parse markdown table lines into rows."""
    return _parse_markdown(lines)


def _parse_markdown(lines) -> list:
    # 按「非空非表格行」切段：一张截图里有两张表时，不同列宽只取第一张
    # （否则会被拼成 5 列、后半张全错位）；同列宽的断行仍合并，容忍中间空行。
    groups, cur = [], []
    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            cur.append(line)
        elif line.strip():
            if cur:
                groups.append(cur)
                cur = []
    if cur:
        groups.append(cur)

    runs = []
    for group in groups:
        if len(group) < 2:
            continue
        rows = []
        for line in group:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(_SEPARATOR.match(c) or c == "" for c in cells):
                continue
            rows.append(cells)
        rows = _normalize(rows)
        if rows:
            runs.append(rows)
    if not runs:
        return []
    if len(runs) > 1 and len({len(r[0]) for r in runs}) > 1:
        return runs[0]
    return _normalize([row for rows in runs for row in rows])


def _parse_aligned(lines) -> list:
    rows = []
    for line in lines:
        if not line.strip():
            continue
        cells = [c.strip() for c in _SPLIT_GAP.split(line.strip())]
        rows.append(cells)
    if len(rows) < 2:
        return []
    width = max(len(r) for r in rows)
    if width < 2:
        return []
    consistent = sum(1 for r in rows if len(r) == width)
    if consistent < max(2, len(rows) // 2):
        return []
    # rows with fewer cells are likely title/notes lines; keep only full rows
    rows = [r for r in rows if len(r) == width]
    return _normalize(rows)


def _normalize(rows) -> list:
    if not rows:
        return []
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def to_tsv(rows) -> str:
    def esc(cell):
        return cell.replace("\t", " ").replace("\n", " ")
    return "\n".join("\t".join(esc(c) for c in row) for row in rows)


def to_markdown(rows) -> str:
    if not rows:
        return ""
    width = len(rows[0])
    out = ["| " + " | ".join(rows[0]) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def looks_like_table(text: str) -> bool:
    rows = parse_table(text)
    return bool(rows) and len(rows) >= 2 and len(rows[0]) >= 2
