"""End-to-end: OCR -> text view -> table re-OCR -> AI layout export -> history."""

import os
import sys
import tempfile
import time
import tkinter as tk
import zipfile

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

HIST_HOME = tempfile.mkdtemp(prefix="starsnip_e2e_")
EXPORT_DIR = tempfile.mkdtemp(prefix="starsnip_exp_")
os.environ["STARSNIP_HOME"] = HIST_HOME

from starsnip import config
from starsnip.app import App
from starsnip.history import History

FIXTURE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "ocr_table.png"))


def main():
    cfg = config.load()
    cfg["export_dir"] = EXPORT_DIR
    cfg["image_dir"] = tempfile.mkdtemp(prefix="starsnip_img_")
    root = tk.Tk()
    root.withdraw()
    app = App(root, cfg)
    app.busy = True
    app.open_file(FIXTURE)

    deadline = time.time() + 180
    state = {"stage": "text", "failure": None}

    def finish(failure=None):
        state["failure"] = failure
        state["stage"] = "done"
        root.destroy()

    def check():
        if state["stage"] == "text" and app.window is not None:
            try:
                text = app.window.text.get("1.0", "end-1c")
            except tk.TclError:
                text = ""
            if text.strip():
                if not ("上海分公司" in text and "34615.50" in text):
                    return finish("unexpected OCR text")
                print("text view OK (%d chars)" % len(text))
                state["stage"] = "table"
                app._request_table(app.window)
        elif state["stage"] == "table":
            rows = app.window.tree.get_children() if app.window else ()
            if rows:
                print("table view rows:", len(rows))
                cells = []
                for iid in rows:
                    cells.extend(app.window.tree.item(iid, "values"))
                if len(rows) < 4 or "34615.50" not in " ".join(cells):
                    return finish("table view content wrong")
                state["stage"] = "export"
                app._export_file(app.window, "docx")
        elif state["stage"] == "export":
            if app.last_export:
                path = app.last_export
                if not (os.path.isfile(path) and path.endswith(".docx")):
                    return finish("export file missing")
                with zipfile.ZipFile(path) as z:
                    assert z.testzip() is None
                    doc = z.read("word/document.xml").decode("utf-8")
                # 表格内容已在本地解析出来，导出必须带真表格且数字不被改写
                assert "<w:tbl>" in doc and "34615.50" in doc, doc[:500]
                print("export OK:", os.path.basename(path),
                      os.path.getsize(path), "bytes, table preserved")
                return finish(None)
        if time.time() > deadline:
            return finish("timeout at stage %s" % state["stage"])
        root.after(200, check)

    root.after(200, check)
    root.mainloop()

    assert state["failure"] is None, state["failure"]
    hist = History(base_dir=HIST_HOME)
    rows = hist.search()
    hist.close()
    assert rows, "history should contain OCR records"
    modes = {r["mode"] for r in rows}
    print("history rows:", len(rows), "| modes:", modes)
    assert "text" in modes and "table" in modes
    print("test_e2e OK")


if __name__ == "__main__":
    main()
