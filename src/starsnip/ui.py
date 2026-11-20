"""Result window and cross-check window (customtkinter redesign)."""

from tkinter import ttk

import customtkinter as ctk

from . import theme, tablefmt


def _style_tree():
    """Style ttk.Treeview to match the theme (accent selection)."""
    style = ttk.Style()
    style.theme_use("clam")
    dark = theme._mode_key() == "dark"
    bg = theme.TEXT_BG["dark" if dark else "light"]
    fg = theme.TEXT_FG["dark" if dark else "light"]
    head_bg = theme.TEXT_BG_SOFT["dark" if dark else "light"]
    sel = theme.SEL_BG["dark" if dark else "light"]
    line = "#3A3A3E" if dark else "#E2E2E6"
    style.configure("Snip.Treeview", background=bg, foreground=fg,
                    fieldbackground=bg, bordercolor=line, rowheight=30,
                    font=("Segoe UI", 11))
    style.configure("Snip.Treeview.Heading", background=head_bg,
                    foreground=fg, bordercolor=line, relief="flat",
                    font=("Segoe UI", 11, "bold"))
    style.map("Snip.Treeview", background=[("selected", sel)],
              foreground=[("selected", fg)])


class ResultWindow(ctk.CTkToplevel):
    def __init__(self, master, on_verify=None, on_retry=None, on_close=None,
                 on_table=None, on_export=None, on_translate=None,
                 on_pin=None, on_beautify=None):
        super().__init__(master)
        self.title("星剪 · 识别结果")
        self.geometry("900x540")
        self.minsize(760, 420)
        self.attributes("-topmost", True)
        self.on_verify = on_verify
        self.on_retry = on_retry
        self.on_table = on_table
        self.on_export = on_export
        self.on_translate = on_translate
        self.on_pin = on_pin
        self.on_beautify = on_beautify
        self._on_close = on_close
        self._rows = None
        self._table_requested = False
        self._orig_text = ""
        self._trans_text = ""
        self._showing_translation = False
        self._F = theme.Fonts()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self.bind("<Escape>", lambda e: self._close())
        self.bind("<Control-c>", lambda e: self.copy_selection() or "break")

    # ---------- build ----------
    def _build(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=theme.PAD, pady=(theme.PAD, 10))

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x")
        logo = theme.logo_image(24)
        if logo:
            ctk.CTkLabel(header, text="", image=logo).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(header, text="识别结果", font=self._F.title,
                     text_color=theme.FG).pack(side="left")
        self.pill = ctk.CTkLabel(header, text="  准备中  ", font=self._F.small,
                                 corner_radius=theme.RADIUS_PILL,
                                 fg_color=theme.SURFACE_SOFT,
                                 text_color=theme.FG, height=26)
        self.pill.pack(side="right")

        ctrl = ctk.CTkFrame(root, fg_color="transparent")
        ctrl.pack(fill="x", pady=(14, 6))
        self.seg = ctk.CTkSegmentedButton(ctrl, values=["文本", "表格"],
                                          font=self._F.body, height=32,
                                          corner_radius=theme.RADIUS_SM,
                                          command=self._switch_view)
        self.seg.set("文本")
        self.seg.pack(side="left")
        self._btn(ctrl, "校验双模型", self._verify, padx=(0, 6))
        self._btn(ctrl, "重试", self._retry)

        self.body = ctk.CTkFrame(root, corner_radius=theme.RADIUS,
                                 fg_color=theme.SURFACE, border_width=1,
                                 border_color=theme.SEPARATOR)
        self.body.pack(fill="both", expand=True, pady=(4, 0))

        self.text = ctk.CTkTextbox(self.body, font=self._F.mono, wrap="word",
                                   corner_radius=theme.RADIUS,
                                   fg_color="transparent", text_color=theme.FG)
        self.text.pack(fill="both", expand=True, padx=2, pady=2)

        self.table_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self.tree = ttk.Treeview(self.table_frame, show="headings",
                                 style="Snip.Treeview")
        yv = ttk.Scrollbar(self.table_frame, orient="vertical",
                           command=self.tree.yview)
        xv = ttk.Scrollbar(self.table_frame, orient="horizontal",
                           command=self.tree.xview)
        self.tree.configure(yscrollcommand=yv.set, xscrollcommand=xv.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yv.grid(row=0, column=1, sticky="ns")
        xv.grid(row=1, column=0, sticky="ew")
        self.table_frame.rowconfigure(0, weight=1)
        self.table_frame.columnconfigure(0, weight=1)
        _style_tree()

        bar = ctk.CTkFrame(root, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        self._btn(bar, "关闭", self._close, side="right")
        self._btn(bar, "复制全部", self.copy_all, variant="primary")
        self._btn(bar, "复制选中", self.copy_selection, padx=(8, 0))
        self._btn(bar, "翻译", self._translate, padx=(16, 0))
        self._btn(bar, "贴图", self._pin, padx=(8, 0))

        self.export_menu = ctk.CTkOptionMenu(
            bar, values=["导出 Word .docx", "导出 TXT", "导出 XLSX",
                         "导出 Markdown .md", "导出 美化分享图 PNG"],
            command=self._on_export_pick, font=self._F.body, width=150,
            corner_radius=theme.RADIUS_SM, fg_color=theme.SURFACE_SOFT,
            button_color=theme.SEPARATOR, button_hover_color=theme.SEPARATOR,
            text_color=theme.FG, dynamic_resizing=False)
        self.export_menu.set("导出 ▾")
        self.export_menu.pack(side="left", padx=(16, 0))

    def _btn(self, parent, text, cmd, side="left", variant="secondary", padx=0):
        if variant == "primary":
            fg, hc, tc, bw, bc = theme.ACCENT, theme.ACCENT_HOVER, "#FFFFFF", 0, ""
        else:
            fg, hc, tc, bw, bc = (theme.SURFACE_SOFT, theme.SEPARATOR,
                                  theme.FG, 1, theme.SEPARATOR)
        b = ctk.CTkButton(parent, text=text, command=cmd,
                          height=theme.CONTROL_H, width=0,
                          corner_radius=theme.RADIUS_SM, font=self._F.body,
                          fg_color=fg, hover_color=hc, text_color=tc,
                          border_width=bw, border_color=bc)
        b.pack(side=side, padx=padx)
        return b

    # ---------- data ----------
    def show_result(self, result, prefer_table=False):
        self._orig_text = result.get("text", "")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self._orig_text)
        self._rows = None
        self._table_requested = False
        self._showing_translation = False
        self.seg.set("文本")
        self._show_text_page()
        if result.get("ok"):
            self.pill.configure(
                text="  %s · %.1fs  " % (result["model"],
                                         result["elapsed_ms"] / 1000.0),
                fg_color=theme.SURFACE_SOFT, text_color=theme.FG_SECONDARY)
        else:
            self.pill.configure(text="  识别失败  ", fg_color=theme.DANGER,
                                text_color="#FFFFFF")
        if prefer_table:
            self.seg.set("表格")
            self._switch_view("表格")

    def status_note(self, text):
        self.pill.configure(text="  %s  " % text, fg_color=theme.SURFACE_SOFT,
                            text_color=theme.FG_SECONDARY)

    def _content(self):
        return self.text.get("1.0", "end-1c")

    def _switch_view(self, value):
        if value == "表格":
            rows = self._rows or tablefmt.parse_table(self._content())
            if not rows:
                self.seg.set("文本")
                self._show_text_page()
                if not self._table_requested and self.on_table:
                    self._table_requested = True
                    self.status_note("正在识别表格…")
                    self.on_table(self)
                else:
                    self.status_note("无法解析为表格")
                return
            self._rows = rows
            self._show_table_page()
            self._fill_tree(rows)
        else:
            self._show_text_page()

    def _show_text_page(self):
        self.table_frame.pack_forget()
        self.text.pack(fill="both", expand=True, padx=2, pady=2)

    def _show_table_page(self):
        self.text.pack_forget()
        self.table_frame.pack(fill="both", expand=True, padx=2, pady=2)

    def _fill_tree(self, rows):
        cols = ["c%d" % i for i in range(len(rows[0]))]
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=cols)
        for i, col in enumerate(cols):
            self.tree.heading(col, text=rows[0][i] or ("列%d" % (i + 1)))
            self.tree.column(col, width=120, anchor="w", minwidth=60)
        for row in rows[1:]:
            self.tree.insert("", "end", values=row)

    # ---------- actions ----------
    def copy_all(self):
        content = self._content()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_note("已复制全部（%d 字）" % len(content))

    def copy_selection(self):
        tb = self.text._textbox
        try:
            content = tb.get("sel.first", "sel.last")
        except Exception:
            self.copy_all()
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_note("已复制选中 %d 字" % len(content))

    def _verify(self):
        if self.on_verify:
            self.on_verify(self)

    def _retry(self):
        if self.on_retry:
            self.on_retry(self)

    def _translate(self):
        if self.on_translate:
            self.on_translate(self)

    def _pin(self):
        if self.on_pin:
            self.on_pin(self)

    def _on_export_pick(self, value):
        fmt = {"导出 Word .docx": "docx", "导出 TXT": "txt",
               "导出 XLSX": "xlsx", "导出 Markdown .md": "md",
               "导出 美化分享图 PNG": "png"}.get(value)
        self.export_menu.set("导出 ▾")
        if not fmt:
            return
        if fmt == "png":
            if self.on_beautify:
                self.on_beautify(self)
        elif self.on_export:
            self.on_export(self, fmt)

    def _close(self):
        if self._on_close:
            self._on_close()
        self.destroy()


class VerifyWindow(ctk.CTkToplevel):
    """Side-by-side model outputs; primary lines missing elsewhere are highlighted."""

    def __init__(self, master, results, disagreements):
        super().__init__(master)
        self._F = theme.Fonts()
        self.title("星剪 · 交叉校验")
        self.geometry("960x540")
        self.minsize(640, 400)
        self.attributes("-topmost", True)

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)
        pane = ctk.CTkFrame(outer, fg_color="transparent")
        pane.pack(fill="both", expand=True)
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)
        pane.rowconfigure(0, weight=1)

        primary = results[0]
        self._panel(pane, 0, "%s (主结果)" % primary["model"], primary,
                    highlight=disagreements)
        right = ctk.CTkFrame(pane, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        for i, res in enumerate(results[1:]):
            self._panel(right, i, res["model"], res)

        bar = ctk.CTkFrame(outer, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(bar, text="复制主结果", width=120,
                      height=theme.CONTROL_H, corner_radius=theme.RADIUS_SM,
                      fg_color=theme.ACCENT,
                      command=lambda: self._copy(primary)).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())

    def _panel(self, parent, row, title, result, highlight=None):
        frame = ctk.CTkFrame(parent, corner_radius=theme.RADIUS,
                             fg_color=theme.SURFACE, border_width=1,
                             border_color=theme.SEPARATOR)
        frame.grid(row=row, column=0, sticky="nsew")
        parent.rowconfigure(row, weight=1)
        parent.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=self._F.body,
                     text_color=theme.FG_SECONDARY).pack(anchor="w",
                                                        padx=10, pady=(8, 2))
        box = ctk.CTkTextbox(frame, font=self._F.label, wrap="word",
                             fg_color="transparent", text_color=theme.FG,
                             corner_radius=theme.RADIUS)
        box.pack(fill="both", expand=True, padx=2, pady=2)
        tb = box._textbox
        if not result.get("ok"):
            tb.insert("1.0", "失败：%s" % result.get("error"))
        else:
            for idx, line in enumerate(result["text"].splitlines()):
                tag = ("diff",) if highlight and idx in highlight else ()
                tb.insert("end", line + "\n", tag)
            tb.tag_configure("diff", background="#FDE68A")
        tb.configure(state="disabled")

    def _copy(self, result):
        self.clipboard_clear()
        self.clipboard_append(result.get("text", ""))
