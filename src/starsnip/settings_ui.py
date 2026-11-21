"""设置中心：左导航轨 + 行式设置卡（DeskBox 风格）。

布局参考 DeskBox 的设置页：214px 左导航 + 右内容列（28px 页面标题、64px 高的
设置卡、4px 缝、6px 圆角、约 12% 白描边、控件右对齐）。层次靠「窗口底 → 卡片 →
描边」三档明度叠出来，不用投影；图标用系统自带的 Segoe Fluent Icons 字形，
不额外打包图标资源。

业务逻辑与原版一致：主题点一下即时生效并落盘，开机启动走计划任务，
其余项点「保存」写回 config.json。
"""

import os
import queue
import threading
import time
import tkinter as tk
import webbrowser

import customtkinter as ctk

from . import (__issues_url__, __repo_url__, __tagline__, __version__,
               config, llm, ocr_core, paths, providers, startup, theme, update)

MODEL_HINT = "只列出 OCR 模型（名称含 ocr）；排版/翻译固定用默认模型，无需选择"


def _split_auth(text: str) -> tuple:
    """把「Authorization: Bearer 」这类输入拆成 (头名, 前缀)。"""
    name, _sep, rest = (text or "").strip().partition(":")
    name = name.strip() or "Authorization"
    prefix = rest.lstrip()
    if prefix and not prefix.endswith(" "):
        prefix += " "
    return name, prefix

_THEME_LABELS = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
_THEME_KEYS = {v: k for k, v in _THEME_LABELS.items()}
_BG_LABELS = {"white": "纯白", "gradient": "渐变"}
_BG_KEYS = {v: k for k, v in _BG_LABELS.items()}

# 页面顺序与导航字形（Segoe Fluent Icons 码位）
_PAGES = [
    ("general", "\uE80F", "常规"),
    ("keys", "\uE765", "快捷与交互"),
    ("backend", "\uE950", "模型接入"),
    ("storage", "\uE8B7", "存储与导出"),
    ("about", "\uE946", "关于"),
]


def _descendants(widget):
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(_descendants(child))
    return out


def _bind_hover(widget, on_enter, on_leave):
    """悬停绑定：CTk 的子 canvas / 标签会吃掉父级事件，需逐个绑。

    鼠标在一个控件内部从一个子件移到另一个子件时也会触发 Leave，
    所以离开时要回查光标是否仍落在自己身上，否则选中态会闪烁。
    """

    def inside(x_root, y_root):
        try:
            w = widget.winfo_containing(x_root, y_root)
        except Exception:  # noqa: BLE001 - 窗口销毁时查询会失败
            return False
        while w is not None:
            if w is widget:
                return True
            w = getattr(w, "master", None)
        return False

    def handle_leave(event):
        if not inside(event.x_root, event.y_root):
            on_leave()

    for w in [widget] + _descendants(widget):
        w.bind("<Enter>", lambda _e: on_enter(), add="+")
        w.bind("<Leave>", handle_leave, add="+")


class _SearchBox(ctk.CTkFrame):
    """搜索框：左侧放大镜 + 无边框输入，整条做成胶囊。"""

    def __init__(self, parent, placeholder, fonts, on_change=None):
        super().__init__(parent, fg_color=theme.INPUT_BG, corner_radius=17,
                         border_width=1, border_color=theme.CARD_STROKE,
                         height=34)
        self.pack_propagate(False)
        self._icon = ctk.CTkLabel(self, text="\uE721", font=fonts.glyph_sm,
                                  text_color=theme.FG_SECONDARY, width=16)
        self._icon.pack(side="left", padx=(14, 6))
        self.entry = ctk.CTkEntry(
            self, font=fonts.desc, fg_color="transparent", border_width=0,
            height=28, text_color=theme.FG)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 14))
        # CTkEntry 自带 placeholder 一获焦就消失；这里用独立标签，聚焦时也保留
        self._ph = ctk.CTkLabel(self, text=placeholder, font=fonts.desc,
                                text_color=theme.FG_SECONDARY, anchor="w")
        self._ph.place(x=36, rely=0.5, anchor="w")
        self._ph.bind("<Button-1>", lambda _e: self.entry.focus_set())
        self._on_change = on_change
        self.entry.bind("<KeyRelease>", lambda _e: self._changed())

    def _changed(self):
        has_text = bool(self.entry.get())
        if has_text:
            self._ph.place_forget()
        else:
            self._ph.place(x=36, rely=0.5, anchor="w")
        if self._on_change:
            self._on_change()

    def get(self):
        return self.entry.get()

    def clear(self):
        self.entry.delete(0, "end")
        self._changed()


class _NavItem(ctk.CTkFrame):
    """导航项：字形 + 文字；选中 = 低饱和色底 + 左侧 3px 强调色条。"""

    def __init__(self, parent, key, glyph, text, command, fonts):
        super().__init__(parent, fg_color="transparent",
                         corner_radius=theme.RADIUS_CARD)
        self.key = key
        self._command = command
        self._fonts = fonts
        self._active = False
        self._bar = ctk.CTkFrame(self, width=3, height=16,
                                 fg_color=theme.ACCENT, corner_radius=2)
        self._icon = ctk.CTkLabel(self, text=glyph, font=fonts.glyph,
                                  width=22, text_color=theme.FG_SECONDARY)
        self._icon.pack(side="left", padx=(15, 10), pady=9)
        self._text = ctk.CTkLabel(self, text=text, font=fonts.nav,
                                  text_color=theme.FG, anchor="w")
        self._text.pack(side="left")
        for w in [self] + _descendants(self):
            w.bind("<Button-1>", lambda _e: self._command(self.key), add="+")
        _bind_hover(self, self._hover_on, self._hover_off)

    def _hover_on(self):
        if not self._active:
            self.configure(fg_color=theme.SURFACE_SOFT)

    def _hover_off(self):
        if not self._active:
            self.configure(fg_color="transparent")

    def set_active(self, active):
        self._active = bool(active)
        self.configure(fg_color=theme.NAV_SEL if active else "transparent")
        self._text.configure(font=self._fonts.nav_bold if active
                             else self._fonts.nav)
        self._icon.configure(
            text_color=theme.ACCENT if active else theme.FG_SECONDARY)
        if active:
            self._bar.place(x=0, rely=0.5, anchor="w")
        else:
            self._bar.place_forget()


class _SettingsRow(ctk.CTkFrame):
    """一行设置卡：左字形 + 标题/描述，右控件槽（row.slot）。"""

    def __init__(self, parent, glyph, title, desc, fonts, wrap=360):
        super().__init__(parent, fg_color=theme.SURFACE,
                         corner_radius=theme.RADIUS_CARD, border_width=1,
                         border_color=theme.CARD_STROKE)
        self.title_text = title
        self.desc_text = desc or ""
        self.hidden = False        # 按厂商隐藏（自定义 API 才显示高级项）
        self._wrap = wrap
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, minsize=theme.ROW_H - 2)
        self._icon = ctk.CTkLabel(self, text=glyph, font=fonts.glyph,
                                  width=22, text_color=theme.FG_SECONDARY)
        self._icon.grid(row=0, column=0, padx=(16, 12))
        # 文字列要占满剩余宽度（sticky="we"），否则描述会被右侧控件挤掉、
        # 表现成「句子末尾被切掉」而不是折行。
        self.textbox = ctk.CTkFrame(self, fg_color="transparent")
        self.textbox.grid(row=0, column=1, sticky="we", pady=10)
        self._title = ctk.CTkLabel(self.textbox, text=title, font=fonts.card,
                                   text_color=theme.FG, anchor="w",
                                   justify="left")
        self._title.pack(anchor="w")
        self._desc = None
        if desc:
            # 固定折行宽度（同时固定控件宽度）：用实测宽度反推会形成
            #「标签越宽 → 列越宽 → 折行宽度又变大」的正反馈，最后完全不折行。
            self._desc = ctk.CTkLabel(
                self.textbox, text=desc, font=fonts.desc,
                text_color=theme.FG_SECONDARY, anchor="w", justify="left",
                wraplength=wrap, width=wrap)
            self._desc.pack(anchor="w", pady=(2, 0))
        # 空 CTkFrame 默认请求 200x200，会把整行撑高；没有控件时保持 1x1
        self.slot = ctk.CTkFrame(self, fg_color="transparent",
                                 width=1, height=1)
        self.slot.grid(row=0, column=2, padx=(14, 16), sticky="e")
        # 说明：不再按窗口宽度动态改 wraplength（见上面的正反馈说明）。

    def set_desc(self, text):
        self.desc_text = text or ""
        if self._desc is not None:
            self._desc.configure(text=text or "")

    def configure_desc_color(self, color):
        """描述行临时改色（连接失败时标红）。"""
        if self._desc is not None:
            self._desc.configure(text_color=color)


class _Toggle(tk.Canvas):
    """40×20 胶囊开关：轨道 + 内嵌圆形滑块（DeskBox / WinUI 的形态）。

    CTkSwitch 的滑块是骑在轨道右端、有一半露在轨道外的：深色下好看，
    浅色下白色滑块与白卡片融为一体，看起来像被咬掉一块。这里自绘一个
    轨道 40×20、滑块 16、四周留 2px 的版本，两种主题都有清晰轮廓。
    """

    W, H = 40, 20

    def __init__(self, parent, value=False, command=None):
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(parent)
        except Exception:  # noqa: BLE001 - 拿不到缩放就按 100% 画
            scale = 1.0
        self._scale = max(1.0, float(scale))
        super().__init__(parent, width=int(self.W * self._scale),
                         height=int(self.H * self._scale),
                         highlightthickness=0, bd=0, cursor="hand2",
                         bg=theme.resolve(theme.SURFACE))
        self._on = bool(value)
        self._command = command
        self._disabled = False
        self.bind("<Button-1>", lambda _e: self.invoke())
        theme.on_theme_change(self._repaint)
        self._repaint()

    # ---- 绘制 ----
    def _repaint(self):
        try:
            s = self._scale
            w, h = self.W * s, self.H * s
            self.delete("all")
            self.configure(bg=theme.resolve(theme.SURFACE))
            track = theme.resolve(theme.ACCENT if self._on
                                  else theme.SEPARATOR)
            radius = h / 2
            self.create_oval(0, 0, h, h, fill=track, outline="")
            self.create_oval(w - h, 0, w, h, fill=track, outline="")
            self.create_rectangle(radius, 0, w - radius, h, fill=track,
                                 outline="")
            pad = 2 * s
            diameter = h - 2 * pad
            x = (w - pad - diameter) if self._on else pad
            self.create_oval(x, pad, x + diameter, pad + diameter,
                             fill="#FFFFFF",
                             outline=theme.resolve(theme.CARD_STROKE),
                             width=max(1, int(s)))
        except Exception:  # noqa: BLE001 - 窗口正在销毁
            pass

    # ---- 取值 / 置值 ----
    def get(self):
        return 1 if self._on else 0

    def select(self):
        self._set(True)

    def deselect(self):
        self._set(False)

    def _set(self, on):
        on = bool(on)
        if on != self._on:
            self._on = on
            self._repaint()

    def invoke(self):
        if self._disabled:
            return
        self._set(not self._on)
        if self._command:
            self._command()

    def configure(self, **kwargs):  # noqa: D401 - 与 CTkSwitch 的调用方式对齐
        state = kwargs.pop("state", None)
        if state is not None:
            self._disabled = (state == "disabled")
            kwargs["cursor"] = "" if self._disabled else "hand2"
        if kwargs:
            super().configure(**kwargs)


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, cfg, on_save, on_hotkey, on_theme=None,
                 on_hotkey_only=None):
        super().__init__(master)
        self.cfg = cfg
        self.on_save = on_save
        self.on_hotkey = on_hotkey
        self.on_theme = on_theme
        self.on_hotkey_only = on_hotkey_only
        self.title("星剪 · 设置")
        self.geometry("980x780")
        self.minsize(860, 600)
        self.configure(fg_color=theme.BG)
        self._F = theme.Fonts()

        self._theme_key = cfg.get("theme", "system")
        self._hotkey_var = ctk.StringVar(value=cfg.get("hotkey", ""))
        self._hotkey_only_var = ctk.StringVar(
            value=cfg.get("hotkey_capture_only", ""))
        self._models_queue = queue.Queue()
        self._refreshing = False
        self._update_queue = queue.Queue()
        self._checking = False
        # 三个角色各存一份接入配置（切换角色时只在界面复用同一组控件）
        self._models = {role: dict(config.model_profile(cfg, role))
                        for role in config.MODEL_ROLES}
        self._role = "ocr"
        self._test_queue = queue.Queue()
        self._rows = {key: [] for key, _g, _t in _PAGES}
        self._pages = {}
        self._nav_items = {}
        self._active = "general"
        self._titles = {key: text for key, _g, text in _PAGES}

        self._build()
        self._show_page("general")
        self.bind("<Escape>", lambda _e: self.destroy())
        # 打开即拉一次模型列表（失败就保持手填，不阻塞窗口）
        self.after(120, self.refresh_models)

    # ---------- 骨架 ----------
    def _build(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True)

        nav = ctk.CTkFrame(shell, fg_color="transparent", width=theme.NAV_W)
        nav.pack(side="left", fill="y", padx=(14, 0), pady=14)
        nav.pack_propagate(False)
        self._build_nav(nav)

        content = ctk.CTkFrame(shell, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True,
                     padx=(20, 22), pady=(14, 16))
        self._build_content(content)

    def _build_nav(self, nav):
        brand = ctk.CTkFrame(nav, fg_color="transparent")
        brand.pack(fill="x", padx=4, pady=(2, 16))
        logo = theme.logo_image(22)
        if logo:
            ctk.CTkLabel(brand, text="", image=logo).pack(side="left",
                                                          padx=(0, 8))
        ctk.CTkLabel(brand, text="星剪", font=self._F.card_bold,
                     text_color=theme.FG).pack(side="left")
        ctk.CTkLabel(brand, text="设置", font=self._F.caption,
                     text_color=theme.FG_SECONDARY).pack(side="left",
                                                         padx=(6, 0),
                                                         pady=(3, 0))

        for key, glyph, text in _PAGES:
            if key == "about":
                ctk.CTkFrame(nav, fg_color="transparent", height=14).pack(
                    fill="x")
            item = _NavItem(nav, key, glyph, text, self._show_page, self._F)
            item.pack(fill="x", pady=(0, 2))
            self._nav_items[key] = item

    def _build_content(self, content):
        search_wrap = ctk.CTkFrame(content, fg_color="transparent", height=34)
        search_wrap.pack(side="top", fill="x", pady=(0, 16))
        search_wrap.pack_propagate(False)
        self._search = _SearchBox(search_wrap, "搜索设置", self._F,
                                  self._filter)
        self._search.place(relx=0, rely=0, relwidth=0.62, relheight=1)

        self._title = ctk.CTkLabel(content, text="常规", font=self._F.display,
                                   text_color=theme.FG, anchor="w")
        self._title.pack(side="top", fill="x", pady=(0, 10))

        bar = ctk.CTkFrame(content, fg_color="transparent")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        ctk.CTkFrame(content, height=1, fg_color=theme.SEPARATOR).pack(
            side="bottom", fill="x")
        self._status = ctk.CTkLabel(
            bar, text="主题与开机启动即时生效，其余项点「保存」",
            font=self._F.desc, text_color=theme.FG_SECONDARY, anchor="w")
        self._status.pack(side="left")
        ctk.CTkButton(bar, text="关闭", width=88, height=34,
                      corner_radius=theme.RADIUS_CARD,
                      fg_color=theme.SURFACE_SOFT, text_color=theme.FG,
                      border_width=1, border_color=theme.SEPARATOR,
                      hover_color=theme.SEPARATOR, font=self._F.card,
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bar, text="保存", width=104, height=34,
                      corner_radius=theme.RADIUS_CARD, fg_color=theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER, font=self._F.card,
                      command=self._save).pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(
            content, fg_color="transparent",
            scrollbar_button_color=theme.SEPARATOR,
            scrollbar_button_hover_color=theme.FG_SECONDARY)
        self._scroll.pack(side="top", fill="both", expand=True)
        self._scroll._parent_canvas.bind(
            "<Configure>", lambda _e: self.after(20, self._sync_scrollbar),
            add="+")

        self._pages = {key: ctk.CTkFrame(self._scroll, fg_color="transparent")
                       for key, _g, _t in _PAGES}
        self._build_general(self._pages["general"])
        self._build_keys(self._pages["keys"])
        self._build_backend(self._pages["backend"])
        self._build_storage(self._pages["storage"])
        self._build_about(self._pages["about"])

    def _add_row(self, page, glyph, title, desc=""):
        row = _SettingsRow(self._pages[page], glyph, title, desc, self._F)
        row.pack(fill="x", pady=(0, theme.ROW_GAP))
        self._rows[page].append(row)
        return row

    def _sync_scrollbar(self):
        """内容没超出视口时收起滚动条（WinUI 的做法），免得右边挂个空滑轨。"""
        try:
            canvas = self._scroll._parent_canvas
            bar = self._scroll._scrollbar
            canvas.update_idletasks()
            content = canvas.bbox("all")
            if content and content[3] > canvas.winfo_height():
                bar.grid()
            else:
                bar.grid_remove()
        except Exception:  # noqa: BLE001 - CTk 内部结构变化时保持默认外观
            pass

    def _show_page(self, key):
        if key not in self._pages:
            return
        for name, frame in self._pages.items():
            if name == key:
                frame.pack(fill="x", pady=(0, 8))
            else:
                frame.pack_forget()
        self._active = key
        self._title.configure(text=self._titles[key])
        for name, item in self._nav_items.items():
            item.set_active(name == key)
        self._search.clear()
        self._filter()
        try:
            self._scroll._parent_canvas.yview_moveto(0)
        except Exception:  # noqa: BLE001 - 内部结构变动时不影响切页
            pass
        self.after(30, self._sync_scrollbar)
        if key == "about":
            self._refresh_update_from_cache()

    def _filter(self):
        """本页内按标题/描述过滤（隐藏用 pack_forget，再按原顺序重排）。"""
        if not hasattr(self, "_search"):
            return
        query = self._search.get().strip().lower()
        rows = self._rows.get(self._active, [])
        for row in rows:
            row.pack_forget()
        for row in rows:
            if getattr(row, "hidden", False):
                continue
            text = (row.title_text + " " + row.desc_text).lower()
            if not query or query in text:
                row.pack(fill="x", pady=(0, theme.ROW_GAP))

    # ---------- 控件工厂 ----------
    def _toggle(self, parent, value, command=None):
        return _Toggle(parent, value, command)

    def _menu(self, parent, labels, value, command):
        menu = ctk.CTkOptionMenu(
            parent, values=list(labels), width=150, height=34,
            corner_radius=theme.RADIUS_CARD, font=self._F.card,
            fg_color=theme.INPUT_BG, button_color=theme.INPUT_BG,
            button_hover_color=theme.SEPARATOR, text_color=theme.FG,
            dropdown_fg_color=theme.SURFACE, dropdown_text_color=theme.FG,
            dropdown_hover_color=theme.SURFACE_SOFT,
            dropdown_font=self._F.card, command=command)
        menu.set(value)
        menu.pack()
        return menu

    def _entry(self, parent, value, width=300, placeholder=""):
        e = ctk.CTkEntry(parent, height=34, width=width,
                         corner_radius=theme.RADIUS_CARD, font=self._F.label,
                         fg_color=theme.INPUT_BG, border_width=1,
                         border_color=theme.CARD_STROKE,
                         text_color=theme.FG,
                         placeholder_text=placeholder or None,
                         placeholder_text_color=theme.FG_SECONDARY)
        # 空值不要 insert("")：CTkEntry.insert 会撤销占位文字且不再恢复
        if value:
            e.insert(0, value)
        e.pack()
        return e

    def _combo(self, parent, value, width=200):
        """可编辑下拉框：既能直接输入，也能从后端模型列表里选。"""
        c = ctk.CTkComboBox(parent, height=34, width=width,
                            corner_radius=theme.RADIUS_CARD,
                            font=self._F.label, fg_color=theme.INPUT_BG,
                            border_width=1, border_color=theme.CARD_STROKE,
                            text_color=theme.FG,
                            button_color=theme.INPUT_BG,
                            button_hover_color=theme.SEPARATOR,
                            dropdown_fg_color=theme.SURFACE,
                            dropdown_text_color=theme.FG,
                            dropdown_font=self._F.label,
                            values=[value] if value else [], state="normal")
        c.set(value or "")
        c.pack(side="left")
        return c

    def _icon_button(self, parent, glyph, command):
        b = ctk.CTkButton(parent, text=glyph, width=32, height=32,
                          corner_radius=theme.RADIUS_CARD,
                          font=self._F.glyph_sm, fg_color="transparent",
                          hover_color=theme.SURFACE_SOFT,
                          text_color=theme.FG_SECONDARY, command=command)
        b.pack(side="left", padx=(8, 0))
        return b

    # ---------- 各页 ----------
    def _build_general(self, page):
        row = self._add_row("general", "\uE706", "界面主题",
                            "跟随系统，或固定浅色 / 深色")
        self.theme_menu = self._menu(
            row.slot, _THEME_LABELS.values(),
            _THEME_LABELS.get(self._theme_key, "跟随系统"),
            lambda label: self._pick_theme(_THEME_KEYS.get(label, "system")))

        row = self._add_row("general", "\uE7E8", "开机启动",
                            "正在检查启动项…")
        self._autostart_row = row
        # 状态直接复用卡片描述行：两行结构与其它设置卡对齐，不会把行撑高
        self.autostart_status = row._desc
        self.autostart_cb = self._toggle(row.slot, False,
                                         self._toggle_autostart)
        self.autostart_cb.pack(side="right")
        self.autostart_cb.configure(state="disabled")
        self._autostart_busy = True
        self._autostart_queue = queue.Queue()
        self.after(120, self._check_autostart)

        row = self._add_row("general", "\uE713", "启动方式",
                            "自动 = 注册表，被策略拦就换文件夹")
        self.startup_menu = self._menu(
            row.slot, startup.MODE_LABELS.values(),
            startup.MODE_LABELS.get(self.cfg.get("startup_mode", "auto"),
                                    "自动（推荐）"),
            self._pick_startup_mode)

        row = self._add_row("general", "\uE74E", "保存截图文件",
                            "截图后同时写入图片目录")
        self.save_cb = self._toggle(row.slot,
                                    self.cfg.get("save_image", True))
        self.save_cb.pack(side="right")

        row = self._add_row("general", "\uE8C8", "写入系统剪贴板",
                            "截图后可直接粘贴到聊天窗口或文档")
        self.clip_cb = self._toggle(row.slot,
                                    self.cfg.get("clipboard_image", True))
        self.clip_cb.pack(side="right")

        row = self._add_row("general", "\uE81C", "保存历史记录",
                            "记录识别文字与缩略图，可在历史窗口搜索")
        self.hist_cb = self._toggle(row.slot,
                                    self.cfg.get("history_enabled", True))
        self.hist_cb.pack(side="right")

        row = self._add_row("general", "\uE790", "美化分享图背景",
                            "导出 PNG 美化图时使用的底色")
        self.bg_seg = self._menu(row.slot, _BG_LABELS.values(),
                                 _BG_LABELS.get(
                                     self.cfg.get("beautify_bg", "white"),
                                     "纯白"),
                                 lambda _label: None)

    def _build_keys(self, page):
        row = self._add_row("keys", "\uE8D7", "截图识别快捷键",
                            "拖拽选区后立即 OCR，默认 Ctrl+2")
        self._hotkey_row(row, self._hotkey_var, self._open_hotkey,
                         primary=True)

        row = self._add_row("keys", "\uE8FF", "仅截图快捷键",
                            "拖拽后停留，点 ✓ 才保存 / 进剪贴板，默认 Ctrl+1")
        self._hotkey_row(row, self._hotkey_only_var, self._open_hotkey_only)

    def _hotkey_row(self, row, var, command, primary=False):
        value = ctk.CTkLabel(row.slot, text=var.get() or "未设置",
                             font=self._F.mono,
                             text_color=theme.ACCENT if var.get()
                             else theme.FG_SECONDARY)
        value.pack(side="left", padx=(0, 12))

        def _sync(*_args):
            try:
                value.configure(text=var.get() or "未设置",
                                text_color=theme.ACCENT if var.get()
                                else theme.FG_SECONDARY)
            except Exception:  # noqa: BLE001 - 窗口已销毁
                pass

        var.trace_add("write", _sync)
        # 行内动作统一走中性按钮：强调色只留给底部的「保存」，避免两行按钮不一样高
        style = {"fg_color": theme.SURFACE_SOFT, "text_color": theme.FG,
                 "border_width": 1, "border_color": theme.CARD_STROKE,
                 "hover_color": theme.SEPARATOR}
        ctk.CTkButton(row.slot, text="更改…", width=88, height=34,
                      corner_radius=theme.RADIUS_CARD, font=self._F.card,
                      command=command, **style).pack(side="left")

    def _build_backend(self, page):
        intro = ctk.CTkLabel(
            page, text="三个角色各配各的：主 LLM 管翻译，OCR 管识图，排版管导出；互不影响。",
            font=self._F.desc, text_color=theme.FG_SECONDARY, anchor="w")
        intro.pack(fill="x", padx=6, pady=(2, 8))

        row = self._add_row("backend", "\uE8EF", "要配置的角色",
                            "切换角色后，下面各字段就是它自己的配置")
        self.role_seg = ctk.CTkSegmentedButton(
            row.slot, values=list(config.ROLE_LABELS.values()),
            width=330, height=32, command=self._pick_role, **theme.SEG_STYLE)
        self.role_seg.set(config.ROLE_LABELS[self._role])
        self.role_seg.pack()

        row = self._add_row("backend", "\uE774", "服务商",
                            self._provider_desc(self._profile()["provider"]))
        self._provider_row = row
        self.provider_menu = self._menu(
            row.slot, providers.LABELS,
            providers.label(self._profile().get("provider")),
            self._pick_provider)

        row = self._add_row("backend", "\uE846", "BaseURL",
                            self._base_desc(self._profile().get("provider")))
        self._base_row = row
        self.base_e = self._entry(row.slot, self._profile().get("base_url"),
                                  width=320,
                                  placeholder="https://example.com/v1")
        self.url_e = self.base_e          # 兼容旧测试与旧代码的字段名

        row = self._add_row("backend", "\uE8A7", "鉴权头",
                            "默认 Bearer，自定义服务可改头名")
        self._auth_row = row
        self.auth_e = self._entry(row.slot, self._auth_text(), width=280)

        row = self._add_row("backend", "\uE8D7", "API Key",
                            "只写本地 config.local.json，不入库")
        self._key_row = row
        self.key_e = self._entry(row.slot, self._profile().get("api_key"),
                                 width=320, placeholder="sk-...")

        row = self._add_row("backend", "\uE8AC", "模型名称",
                            providers.get(self._profile().get("provider")).get("hint") or "")
        self._model_row = row
        self._model_hint = row._desc
        self.model_e = self._combo(row.slot, self._profile().get("model") or "")
        self._icon_button(row.slot, "\uE72C", self.refresh_models)

        row = self._add_row("backend", "\uE81C", "超时时间",
                            "单位秒，云端模型可调大")
        self.timeout_e = self._entry(row.slot,
                                     str(self._profile().get("timeout") or 60),
                                     width=90)

        row = self._add_row("backend", "\uE768", "流式输出",
                            "按 SSE 增量接收，内容一致")
        self._stream_row = row
        self.stream_cb = self._toggle(row.slot,
                                      bool(self._profile().get("stream")))
        self.stream_cb.pack(side="right")

        row = self._add_row("backend", "\uE950", "连接测试",
                            "点一下验证地址 / Key / 模型")
        self._test_row = row
        self._test_btn = self._action_button(row.slot, "测试连接",
                                             self._test_connection, width=104)
        # 初始就按当前角色应用「高级项只在自定义 API 显示」
        self._apply_advanced_rows(self._profile().get("provider"))

    # ---------- 模型接入：角色切换与读写 ----------
    def _profile(self, role=None):
        return self._models[role or self._role]

    def _auth_text(self, profile=None):
        item = profile or self._profile()
        prefix = item.get("auth_prefix")
        prefix = "Bearer " if prefix is None else prefix
        return "%s: %s" % (item.get("auth_header") or "Authorization", prefix)

    def _provider_desc(self, key):
        item = providers.get(key)
        hint = item.get("hint") or ""
        return hint

    def _base_desc(self, key):
        # Tk 的 Label 只在空白处折行，长中文串会被直接切掉；说明文字保持短句。
        return "换地域 / 走代理 / 用专属部署，都可直接改"

    @staticmethod
    def _set_entry(entry, text):
        """CTkEntry 的 insert("") 会撤销占位文字，空值只删不插。"""
        entry.delete(0, "end")
        if text:
            entry.insert(0, str(text))

    def _flush_role(self):
        """把界面上的值写回当前角色的配置（切角色/保存前调用）。"""
        profile = self._models[self._role]
        profile["provider"] = providers.key_of(self.provider_menu.get())
        profile["base_url"] = self.base_e.get().strip()
        profile["api_key"] = self.key_e.get().strip()
        profile["model"] = self.model_e.get().strip()
        header, prefix = _split_auth(self.auth_e.get())
        profile["auth_header"] = header
        profile["auth_prefix"] = prefix
        try:
            profile["timeout"] = max(5, int(float(self.timeout_e.get().strip())))
        except (TypeError, ValueError):
            profile["timeout"] = 60
        profile["stream"] = bool(self.stream_cb.get())

    def _load_role(self):
        profile = self._profile()
        self.provider_menu.set(providers.label(profile.get("provider")))
        self._set_entry(self.base_e, profile.get("base_url") or "")
        self._set_entry(self.key_e, profile.get("api_key") or "")
        self._set_entry(self.auth_e, self._auth_text(profile))
        self.model_e.set(profile.get("model") or "")
        self._set_entry(self.timeout_e, profile.get("timeout") or 60)
        if profile.get("stream"):
            self.stream_cb.select()
        else:
            self.stream_cb.deselect()
        self._provider_row.set_desc(self._provider_desc(profile.get("provider")))
        self._base_row.set_desc(self._base_desc(profile.get("provider")))
        self._model_row.set_desc(
            providers.get(profile.get("provider")).get("hint") or "")
        self._test_row.set_desc("点「测试连接」验证这组配置")
        self._apply_advanced_rows(profile.get("provider"))

    def _apply_advanced_rows(self, provider_key):
        """鉴权头 / 流式只对「自定义 API」露出：预置厂商用标准 Bearer、非流式，
        普通用户不该看到这两项。"""
        item = providers.get(provider_key)
        custom = item.get("key") == "custom"
        for row in (getattr(self, "_auth_row", None),
                    getattr(self, "_stream_row", None)):
            if row is not None:
                row.hidden = not custom
        # 本地 Ollama 不需要 Key（内网无鉴权的也一样），没必要让用户填
        key_row = getattr(self, "_key_row", None)
        if key_row is not None:
            key_row.hidden = item.get("key") == "ollama"
        self._filter()

    def _pick_role(self, label):
        for key, text in config.ROLE_LABELS.items():
            if text == label:
                self._flush_role()
                self._role = key
                self._load_role()
                return

    def _pick_provider(self, label):
        self._flush_role()
        key = providers.key_of(label)
        profile = self._models[self._role]
        profile["provider"] = key
        if key != "custom":
            # 预置厂商：自动填 BaseURL（仍可编辑）
            profile["base_url"] = providers.base_url(key)
            self._set_entry(self.base_e, profile["base_url"])
        self._provider_row.set_desc(self._provider_desc(key))
        self._base_row.set_desc(self._base_desc(key))
        self._model_row.set_desc(providers.get(key).get("hint") or "")
        self._apply_advanced_rows(key)

    def _test_connection(self):
        profile = dict(self._profile())
        profile["base_url"] = self.base_e.get().strip() or profile.get("base_url")
        profile["api_key"] = self.key_e.get().strip()
        profile["model"] = self.model_e.get().strip()
        self._test_btn.configure(state="disabled", text="测试中…")
        self._test_row.set_desc("正在连接…")

        def work():
            ok, message = llm.probe(profile, timeout=12)
            self._test_queue.put((ok, message))

        threading.Thread(target=work, daemon=True).start()
        self._poll_test(0)

    def _poll_test(self, tries):
        if not self.winfo_exists():
            return
        try:
            ok, message = self._test_queue.get_nowait()
        except queue.Empty:
            if tries < 150:                     # 最多等 15 秒
                self.after(100, lambda: self._poll_test(tries + 1))
            else:
                self._test_btn.configure(state="normal", text="测试连接")
                self._test_row.set_desc("测试超时，检查网络或 BaseURL")
            return
        self._test_btn.configure(state="normal", text="测试连接")
        self._test_row.set_desc(("连接成功：" if ok else "连接失败：") + message)
        if not ok:
            self._test_row.configure_desc_color(theme.DANGER)
        else:
            self._test_row.configure_desc_color(theme.FG_SECONDARY)

    def _build_storage(self, page):
        row = self._add_row("storage", "\uE8B7", "截图保存目录",
                            "留空 = 图片\\StarSnip")
        self.imgdir_e = self._entry(row.slot, self.cfg.get("image_dir", ""),
                                    width=320,
                                    placeholder="默认 " + paths.pictures_dir())

        row = self._add_row("storage", "\uE8A5", "导出目录",
                            "留空 = 文档\\StarSnip")
        self.exportdir_e = self._entry(row.slot,
                                       self.cfg.get("export_dir", ""),
                                       width=320,
                                       placeholder="默认 " + paths.documents_dir())

    def _build_about(self, page):
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.pack(fill="x", pady=(4, 14))
        logo = theme.logo_image(56)
        if logo:
            ctk.CTkLabel(head, text="", image=logo).pack(side="left",
                                                         padx=(4, 14))
        box = ctk.CTkFrame(head, fg_color="transparent")
        box.pack(side="left", anchor="w")
        ctk.CTkLabel(box, text="星剪 StarSnip", font=self._F.section,
                     text_color=theme.FG, anchor="w").pack(anchor="w")
        ctk.CTkLabel(box, text="v%s · %s" % (__version__, __tagline__),
                     font=self._F.desc, text_color=theme.FG_SECONDARY,
                     anchor="w").pack(anchor="w", pady=(2, 0))

        row = self._add_row("about", "\uE946", "版本",
                            "当前 v%s · 启动时自动检查更新" % __version__)
        self._update_row = row
        self.update_btn = self._action_button(row.slot, "检查更新",
                                              self.check_update, width=104)

        row = self._add_row("about", "\uE774", "GitHub 仓库", __repo_url__)
        self._action_button(row.slot, "打开",
                            lambda: self._open_url(__repo_url__))

        row = self._add_row("about", "\uE8A7", "问题反馈", __issues_url__)
        self._action_button(row.slot, "打开",
                            lambda: self._open_url(__issues_url__))

        row = self._add_row("about", "\uE8B7", "数据目录", paths.data_home())
        self._action_button(row.slot, "打开",
                            lambda: self._open_path(paths.data_home()))

        row = self._add_row("about", "\uE8A5", "日志文件", paths.log_path())
        self._action_button(row.slot, "打开",
                            lambda: self._open_path(paths.log_path()))

        row = self._add_row("about", "\uE8D7", "快捷键",
                            "截图识别 Ctrl+2 · 仅截图 Ctrl+1 · 可在「快捷与交互」里改")

    # ---------- 关于页的链接 / 更新 ----------
    def _action_button(self, parent, text, command, width=88):
        button = ctk.CTkButton(parent, text=text, width=width, height=34,
                               corner_radius=theme.RADIUS_CARD,
                               font=self._F.card,
                               fg_color=theme.SURFACE_SOFT,
                               text_color=theme.FG, border_width=1,
                               border_color=theme.CARD_STROKE,
                               hover_color=theme.SEPARATOR,
                               command=command)
        button.pack(side="left")
        return button

    def _open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - 没有默认浏览器时退回复制链接
            self._copy(url)

    def _open_path(self, path):
        try:
            target = path if os.path.exists(path) else os.path.dirname(path)
            os.startfile(target)   # noqa: S606 - Windows 专用，打开目录/文件
        except Exception:  # noqa: BLE001
            self._copy(path)

    def _copy(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._status.configure(text="路径已复制到剪贴板")
        except Exception:  # noqa: BLE001
            pass

    def check_update(self):
        """手动检查更新：后台线程查，主线程轮询（Tk 单线程铁律）。"""
        if self._checking:
            return
        self._checking = True
        self.update_btn.configure(state="disabled", text="检查中…")
        self._update_row.set_desc("正在检查更新…")
        threading.Thread(target=self._update_worker, daemon=True).start()
        self._poll_update(0)

    def _update_worker(self):
        try:
            info = update.check(self.cfg)
        except Exception as exc:  # noqa: BLE001 - 网络异常也要有话说
            info = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        self._update_queue.put(info)

    def _poll_update(self, tries):
        if not self.winfo_exists():
            return
        try:
            info = self._update_queue.get_nowait()
        except queue.Empty:
            if tries < 100:                     # 最多等约 10 秒
                self.after(100, lambda: self._poll_update(tries + 1))
            else:
                self._finish_update({"ok": False, "error": "检查超时"})
            return
        self._finish_update(info)

    def _finish_update(self, info):
        self._checking = False
        if not self.winfo_exists():
            return
        self.update_btn.configure(state="normal")
        if not info.get("ok"):
            self.update_btn.configure(text="重试", command=self.check_update)
            self._update_row.set_desc("检查失败：%s" % (info.get("error")
                                                    or "网络不可达"))
            return
        latest = info.get("latest") or ""
        if info.get("newer"):
            url = info.get("url") or (__repo_url__ + "/releases")
            self.update_btn.configure(text="打开发布页",
                                      command=lambda: self._open_url(url))
            self._update_row.set_desc("发现新版本 v%s（当前 v%s）· 自动更新已开启"
                                      % (latest.lstrip("v"), __version__))
        else:
            self.update_btn.configure(text="检查更新", command=self.check_update)
            self._update_row.set_desc("已是最新版本（v%s）" % __version__)

    def _refresh_update_from_cache(self):
        """切到关于页时，把上次检查到的新版本直接显示出来（不再联网）。"""
        try:
            cached = update.read_cache()
            latest = cached.get("latest") or ""
            if latest and update.is_newer(latest):
                url = cached.get("url") or (__repo_url__ + "/releases")
                self._update_row.set_desc("发现新版本 v%s（当前 v%s）"
                                          % (latest.lstrip("v"), __version__))
                self.update_btn.configure(text="打开发布页",
                                          command=lambda: self._open_url(url))
        except Exception:  # noqa: BLE001 - 缓存坏了不影响页面
            pass


    # ---------- 模型列表 ----------
    def refresh_models(self):
        """按当前角色的配置拉模型列表（Ollama → /api/tags，云端 → /models）。

        后台线程只做网络，结果经队列回主线程（Tk 单线程铁律）。
        """
        if self._refreshing:
            return
        self._refreshing = True
        profile = dict(self._profile())
        profile["base_url"] = self.base_e.get().strip() or profile.get("base_url")
        profile["api_key"] = self.key_e.get().strip()
        local = providers.is_ollama(profile.get("provider"))
        self._set_hint("正在拉取模型列表…" if not local
                       else "正在从 Ollama 拉取 OCR 模型…")

        def work():
            self._models_queue.put(ocr_core.list_candidates(profile, timeout=10))

        threading.Thread(target=work, daemon=True).start()
        self._poll_models(0)

    def _poll_models(self, tries):
        try:
            names = self._models_queue.get_nowait()
        except queue.Empty:
            if tries < 120:                     # 最多等约 12 秒
                self.after(100, lambda: self._poll_models(tries + 1))
            else:
                self._refreshing = False
                self._set_hint("拉取超时：检查 BaseURL / 网络，或直接手填模型名")
            return
        self._refreshing = False
        if not self.winfo_exists():
            return
        current = self.model_e.get()
        if names:
            self.model_e.configure(values=names)
            local = providers.is_ollama(self.provider_menu.get())
            self._set_hint("只列出 OCR 模型（%d 个）" % len(names) if local
                           else "可用模型 %d 个（云端不过滤，按需选）" % len(names))
        else:
            self._set_hint("没取到模型（服务不可用或 Key 无效？可直接手填）")
        self.model_e.set(current)

    def _set_hint(self, text):
        """更新模型行的说明文字（同时更新 desc_text，搜索过滤才不会用旧文案）。"""
        row = getattr(self, "_model_row", None)
        if row is not None and row.winfo_exists():
            row.set_desc(text)

    # ---------- 开机启动（注册表 Run / 启动文件夹 / 任务计划） ----------
    def _set_autostart_status(self, text, danger=False):
        if self.autostart_status.winfo_exists():
            self.autostart_status.configure(
                text=text, text_color=theme.DANGER if danger
                else theme.FG_SECONDARY)
            self._autostart_row.desc_text = text

    def _check_autostart(self):
        """打开设置时体检一次启动项（要读计划任务，可能上百毫秒，放后台）。"""
        threading.Thread(target=self._autostart_worker, args=("check",),
                         daemon=True).start()
        self._poll_autostart()

    def _toggle_autostart(self):
        if self._autostart_busy:
            return
        want = bool(self.autostart_cb.get())
        self._autostart_busy = True
        self.autostart_cb.configure(state="disabled")
        if not want:
            self._set_autostart_status("正在移除启动项…")
        elif self.cfg.get("startup_mode") == startup.MODE_TASK:
            self._set_autostart_status("正在请求管理员权限（UAC）…")
        else:
            self._set_autostart_status("正在写入启动项…")
        threading.Thread(target=self._autostart_worker,
                         args=("enable" if want else "disable",),
                         daemon=True).start()
        self._poll_autostart()

    def _autostart_worker(self, action):
        """后台线程：只做系统调用，结果经队列回主线程（Tk 单线程铁律）。"""
        try:
            if action == "check":
                st = startup.status()
                self._autostart_queue.put(
                    (True, startup.describe(st), st["effective"]))
                return
            if action == "enable":
                ok, msg = startup.enable(self.cfg.get("startup_mode",
                                                      startup.MODE_AUTO))
            else:
                ok, msg = startup.disable()
        except Exception as exc:  # noqa: BLE001 - 交给界面提示
            ok, msg = False, "%s: %s" % (type(exc).__name__, exc)
        try:
            state = startup.status()["effective"]
        except Exception:  # noqa: BLE001
            state = None
        self._autostart_queue.put((ok, msg, state))

    def _poll_autostart(self, tries=0):
        if not self.winfo_exists():
            return
        try:
            ok, msg, state = self._autostart_queue.get_nowait()
        except queue.Empty:
            if tries < 6000:                 # 最多等 10 分钟（UAC 可能被搁置）
                self.after(100, lambda: self._poll_autostart(tries + 1))
            else:
                self._autostart_busy = False
                self.autostart_cb.configure(state="normal")
                self._set_autostart_status("操作超时，请重试", danger=True)
            return
        self._autostart_busy = False
        self.autostart_cb.configure(state="normal")
        if state is not None:
            if state:
                self.autostart_cb.select()
            else:
                self.autostart_cb.deselect()
        self._set_autostart_status(msg, danger=not ok)

    # ---------- 交互 ----------
    def _pick_startup_mode(self, label):
        """启动方式：写回配置；若当前已开着开机启动，立即按新方式重注册一次。"""
        key = startup.MODE_KEYS.get(label, startup.MODE_AUTO)
        self.cfg["startup_mode"] = key
        try:
            config.save_setting("startup_mode", key)
        except OSError:
            pass
        if not self.autostart_cb.get():
            self._set_autostart_status("启动方式已改为「%s」，开启开关后生效"
                                       % label)
            return
        if self._autostart_busy:
            return
        self._autostart_busy = True
        self.autostart_cb.configure(state="disabled")
        self._set_autostart_status("正在按「%s」重新注册…" % label)
        threading.Thread(target=self._autostart_worker, args=("enable",),
                         daemon=True).start()
        self._poll_autostart()

    def _pick_theme(self, value):
        """主题下拉：立即应用 + 落盘（无需再点保存）。"""
        theme.apply_theme(value)
        self._theme_key = value
        self.cfg["theme"] = value
        label = _THEME_LABELS.get(value)
        if label and self.theme_menu.get() != label:
            self.theme_menu.set(label)
        if self.on_theme:
            self.on_theme(value)

    def _open_hotkey(self):
        self.on_hotkey(self._hotkey_var)

    def _open_hotkey_only(self):
        if self.on_hotkey_only:
            self.on_hotkey_only(self._hotkey_only_var)

    def _save(self):
        self._flush_role()
        values = {
            "theme": self._theme_key,
            "models": {role: dict(profile)
                       for role, profile in self._models.items()},
            "image_dir": self.imgdir_e.get().strip(),
            "export_dir": self.exportdir_e.get().strip(),
            "save_image": bool(self.save_cb.get()),
            "clipboard_image": bool(self.clip_cb.get()),
            "history_enabled": bool(self.hist_cb.get()),
            "beautify_bg": _BG_KEYS.get(self.bg_seg.get(), "white"),
            "startup_mode": self.cfg.get("startup_mode", startup.MODE_AUTO),
        }
        self.on_save(values)
        if self._status.winfo_exists():
            self._status.configure(
                text="已保存 · %s（主题与开机启动已即时生效）"
                     % time.strftime("%H:%M"))
