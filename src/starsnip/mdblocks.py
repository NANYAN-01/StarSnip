"""Lightweight Markdown block parser (headings/paragraphs/lists/tables)."""

import re

from . import tablefmt

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST = re.compile(r"^[-*+]\s+(.*)$")


def parse_blocks(markdown: str) -> list:
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue
        m = _HEADING.match(s)
        if m:
            blocks.append({"type": "heading", "level": len(m.group(1)),
                           "text": m.group(2).strip()})
            i += 1
            continue
        if "|" in s and s.startswith("|"):
            group = []
            while i < n and lines[i].strip().startswith("|"):
                group.append(lines[i].strip())
                i += 1
            rows = tablefmt.parse_markdown(group)
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        m = _LIST.match(s)
        if m:
            items = []
            while i < n and _LIST.match(lines[i].strip()):
                items.append(_LIST.match(lines[i].strip()).group(1).strip())
                i += 1
            blocks.append({"type": "list", "items": items})
            continue
        para = [s]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if not nxt or _HEADING.match(nxt) or nxt.startswith("|") or _LIST.match(nxt):
                break
            para.append(nxt)
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para)})
    return blocks
