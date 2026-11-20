"""History window UI test: row listed, detail shown, copy works."""

import os
import sys
import tempfile
import tkinter as tk

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import png
from starsnip.history import History
from starsnip.history_ui import HistoryWindow

THUMB = png.encode_png(2, 2, bytes([0, 200, 0, 255] * 4))


def main():
    base = tempfile.mkdtemp(prefix="starsnip_histui_")
    hist = History(base_dir=base, keep=100)
    hist.add("hotkey", "text", "glm-ocr:latest", 1800,
             "上海分公司 合计 34615.50", thumb_png=THUMB)

    root = tk.Tk()
    root.withdraw()
    win = HistoryWindow(root, hist)
    root.update()
    items = win.tree.get_children()
    assert len(items) == 1, items
    win.tree.selection_set(items[0])
    root.update()
    detail = win.detail.get("1.0", "end-1c")
    print("detail:", detail.strip())
    assert "34615.50" in detail
    win._copy()
    assert "34615.50" in win.clipboard_get()
    print("copy to clipboard OK")

    win.search_var.set("不存在")
    win.reload()
    root.update()
    assert len(win.tree.get_children()) == 0
    win.search_var.set("34615")
    win.reload()
    root.update()
    assert len(win.tree.get_children()) == 1
    print("search OK")

    win.destroy()
    root.destroy()
    hist.close()
    print("test_history_ui OK")


if __name__ == "__main__":
    main()
