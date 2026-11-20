"""Table text parsing: markdown tables or space/tab aligned columns."""

import re

_SEPARATOR = re.compile(r"^:?-{2,}:?$")
_SPLIT_GAP = re.compile(r"\s{2,}|\t+")


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
    rows = _parse_markdown(_clean_fences(text))
    if rows:
        return rows
    return _parse_aligned(_clean_fences(text)) or None


def parse_markdown(lines) -> list:
    """Public wrapper: parse markdown table lines into rows."""
    return _parse_markdown(lines)


def _parse_markdown(lines) -> list:
    raw = [ln for ln in lines if "|" in ln and ln.strip().startswith("|")]
    if len(raw) < 2:
        return []
    rows = []
    for line in raw:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(_SEPARATOR.match(c) or c == "" for c in cells):
            continue
        rows.append(cells)
    return _normalize(rows)


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
