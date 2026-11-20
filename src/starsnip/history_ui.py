"""历史记录浏览窗口（customtkinter 重设计）。"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk

from . import theme
from .ui import _style_tree


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master, history):
        super().__init__(master)
        self._F = theme.Fonts()
        self.history = history
        self.title("星剪 · 历史记录")
        self.geometry("900x560")
        self.minsize(640, 420)
        self._photo = None
        self._rows = {}

        self._build()
        self.bind("<Escape>", lambda e: self.destroy())
        self.reload()

    def _build(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x")
        logo = theme.logo_image(22)
        if logo:
            ctk.CTkLabel(header, text="", image=logo).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(header, text="历史记录", font=self._F.title,
                     text_color=theme.FG).pack(side="left")

        tools = ctk.CTkFrame(root, fg_color="transparent")
        tools.pack(fill="x", pady=(12, 8))
        self.search_var = tk.StringVar()
        entry = ctk.CTkEntry(tools, textvariable=self.search_var, width=260,
                             height=theme.CONTROL_H, corner_radius=theme.RADIUS_SM,
                             font=self._F.body, placeholder_text="搜索文字 / 模型…",
                             border_width=1, border_color=theme.SEPARATOR)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.reload())
        ctk.CTkButton(tools, text="搜索", width=70, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self.reload).pack(side="left", padx=8)
        ctk.CTkButton(tools, text="清空全部", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.DANGER,
                      hover_color=theme.DANGER,
                      text_color=theme.ACCENT_TEXT, command=self._clear).pack(side="right")

        pane = ctk.CTkFrame(root, fg_color="transparent")
        pane.pack(fill="both", expand=True)
        pane.columnconfigure(0, weight=3)
        pane.columnconfigure(1, weight=2)
        pane.rowconfigure(0, weight=1)

        list_frame = ctk.CTkFrame(pane, corner_radius=theme.RADIUS,
                                  fg_color=theme.SURFACE, border_width=1,
                                  border_color=theme.SEPARATOR)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        columns = ("time", "model", "ms", "preview")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                 selectmode="browse", style="Snip.Treeview")
        for col, title, width in (("time", "时间", 150), ("model", "模型", 150),
                                  ("ms", "耗时", 70), ("preview", "内容", 360)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y")
        _style_tree()
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._copy())

        right = ctk.CTkFrame(pane, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.thumb = ctk.CTkLabel(right, text="（无缩略图）", font=self._F.small,
                                  text_color=theme.FG_SECONDARY, corner_radius=theme.RADIUS,
                                  fg_color=theme.SURFACE_SOFT, height=170)
        self.thumb.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        self.detail = ctk.CTkTextbox(right, font=theme.font(13), wrap="word",
                                     corner_radius=theme.RADIUS, fg_color=theme.SURFACE,
                                     border_width=1, border_color=theme.SEPARATOR,
                                     text_color=theme.FG)
        self.detail.grid(row=1, column=0, sticky="nsew")

        bar = ctk.CTkFrame(root, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(bar, text="复制文本", width=110, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self._copy).pack(side="left")
        ctk.CTkButton(bar, text="删除", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.SURFACE_SOFT,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="关闭", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.SURFACE_SOFT,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self.destroy).pack(side="right")

    def reload(self, _event=None):
        rows = self.history.search(self.search_var.get().strip())
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        for row in rows:
            preview = (row["text"] or "").replace("\n", " ")
            if len(preview) > 90:
                preview = preview[:90] + "…"
            iid = str(row["id"])
            self._rows[iid] = row
            self.tree.insert("", "end", iid=iid,
                             values=(row["created_at"].replace("T", " "),
                                     row["model"], row["elapsed_ms"], preview))

    def _selected(self):
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def _on_select(self, _event=None):
        row = self._selected()
        if not row:
            return
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", row["text"])
        self._show_thumb(row)

    def _show_thumb(self, row):
        path = self.history.thumb_file(row.get("thumb_path") or "")
        self._photo = None
        if not path or not os.path.isfile(path):
            self.thumb.configure(image="", text="（无缩略图）")
            return
        img, w, h = theme.photo(path, (240, 150))
        if img is None:
            self.thumb.configure(image="", text="（无法显示缩略图）")
            return
        self._photo = img
        self.thumb.configure(image=img, text="")

    def _copy(self):
        row = self._selected()
        if not row:
            return
        self.clipboard_clear()
        self.clipboard_append(row["text"])

    def _delete(self):
        row = self._selected()
        if not row:
            return
        self.history.delete(row["id"])
        self.reload()

    def _clear(self):
        if not self.history.search():
            return
        if not messagebox.askyesno("清空历史", "确定删除全部历史记录？"):
            return
        self.history.clear()
        self.reload()
