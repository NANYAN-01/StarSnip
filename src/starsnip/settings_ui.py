"""设置窗口：主题、两个热键、OCR 模型、后端与目录、截图后处理、美化背景。

模型只列 OCR 专用模型（ocr_core.list_ocr_models）；排版/翻译固定使用 config 里的
默认 layout_model，不在这里给选项，避免「选了模型却不生效」的多余开关。
保存后逐项写回 config.json（保留其它键），主题与历史开关即时生效。
"""

import queue
import threading

import customtkinter as ctk

from . import autostart, ocr_core, theme

MODEL_HINT = "只列出 OCR 模型（名称含 ocr）；排版/翻译固定用默认模型，无需选择"


class _Field(ctk.CTkFrame):
    def __init__(self, parent, label, hint="", fonts=None):
        super().__init__(parent, fg_color="transparent")
        fonts = fonts or theme.Fonts()
        ctk.CTkLabel(self, text=label, font=fonts.label,
                     text_color=theme.FG).pack(anchor="w")
        self.hint_label = None
        if hint:
            self.hint_label = ctk.CTkLabel(self, text=hint, font=fonts.small,
                                           text_color=theme.FG_SECONDARY)
            self.hint_label.pack(anchor="w", pady=(0, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", pady=(2, 12))


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
        self.geometry("540x700")
        self.minsize(460, 520)
        self._F = theme.Fonts()

        self._hotkey_var = ctk.StringVar(value=cfg.get("hotkey", ""))
        self._hotkey_only_var = ctk.StringVar(
            value=cfg.get("hotkey_capture_only", ""))
        self._models_queue = queue.Queue()
        self._refreshing = False
        self._build()
        # 打开即拉一次模型列表（失败就保持手填，不阻塞窗口）
        self.after(120, self.refresh_models)

    def _build(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD, pady=(theme.PAD, 6))
        logo = theme.logo_image(22)
        if logo:
            ctk.CTkLabel(head, text="", image=logo).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(head, text="设置", font=self._F.title,
                     text_color=theme.FG).pack(side="left")

        # 内容区可滚动：字段较多，窗口高度不够时不会把底部按钮挤掉
        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent",
                                        scrollbar_button_color=theme.SEPARATOR,
                                        scrollbar_button_hover_color=theme.FG_SECONDARY)
        scroll.pack(fill="both", expand=True, padx=theme.PAD)

        def field(label, hint=""):
            """建一个字段块并 pack 进滚动区（之前漏了这一步，导致设置窗口全空）。"""
            block = _Field(scroll, label, hint, self._F)
            block.pack(fill="x")
            return block

        # 主题（点一下立即生效并保存，不需要再点「保存」）
        f = field("界面主题", "点击即时生效；system = 跟随系统自动深浅色")
        self.theme_seg = ctk.CTkSegmentedButton(
            f.body, values=["system", "light", "dark"],
            command=self._pick_theme, **theme.SEG_STYLE)
        self.theme_seg.set(self.cfg.get("theme", "system"))
        self.theme_seg.pack(side="left")

        # 快捷键（识别 / 仅截图）：两行布局相同，共用 _hotkey_row
        f = field("截图识别快捷键", "拖拽后立即 OCR，默认 Ctrl+2")
        self._hotkey_row(f, self._hotkey_var, self._open_hotkey, primary=True)

        f = field("仅截图快捷键", "拖拽后停留，点 ✓ 才保存/进剪贴板，默认 Ctrl+1")
        self._hotkey_row(f, self._hotkey_only_var, self._open_hotkey_only)

        # 开机启动（任务计划程序）
        f = field("开机启动", "勾选后创建 Windows 计划任务（任务名 StarSnip），登录时自动启动；需要管理员授权")
        if f.hint_label is not None:
            f.hint_label.configure(wraplength=470)
        self.autostart_cb = ctk.CTkCheckBox(
            f.body, text="登录 Windows 后自动启动星剪",
            font=self._F.label, command=self._toggle_autostart)
        self.autostart_cb.pack(anchor="w", pady=(2, 4))
        self.autostart_status = ctk.CTkLabel(
            f.body, text="正在检查计划任务…", font=self._F.small,
            text_color=theme.FG_SECONDARY, anchor="w", justify="left",
            wraplength=430)
        self.autostart_status.pack(anchor="w")
        self.autostart_cb.configure(state="disabled")
        self._autostart_busy = True
        self._autostart_queue = queue.Queue()
        self.after(120, self._check_autostart)

        # OCR 模型（只列 OCR 专用模型）
        f = field("OCR 识别模型", MODEL_HINT)
        self._model_hint = f.hint_label
        # 先 pack 右侧按钮，再 pack 下拉框，两者才会排在同一行
        ctk.CTkButton(f.body, text="刷新列表", width=88, height=34,
                      corner_radius=theme.RADIUS_SM,
                      fg_color=theme.SURFACE_SOFT, text_color=theme.FG,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self.refresh_models).pack(side="right", padx=(8, 0))
        self.model_e = self._combo(f.body, self.cfg.get("default_model", ""))

        f = field("后端 Ollama 地址", "内网地址建议写在 config.local.json，避免提交进仓库")
        self.url_e = self._entry(f.body, self.cfg.get("ollama_url", ""))

        # 目录
        f = field("截图保存目录", "留空 = 图片\\StarSnip")
        self.imgdir_e = self._entry(f.body, self.cfg.get("image_dir", ""))

        f = field("导出目录", "留空 = 文档\\StarSnip")
        self.exportdir_e = self._entry(f.body, self.cfg.get("export_dir", ""))

        # 截图后处理：与「仅截图」热键互补，不再用 auto_ocr 全局开关
        f = field("截图后处理")
        self.save_cb = ctk.CTkCheckBox(f.body, text="保存截图文件到截图目录",
                                       font=self._F.label)
        self.save_cb.select() if self.cfg.get("save_image", True) else self.save_cb.deselect()
        self.save_cb.pack(anchor="w", pady=(2, 4))
        self.clip_cb = ctk.CTkCheckBox(f.body, text="截图写入系统剪贴板",
                                       font=self._F.label)
        self.clip_cb.select() if self.cfg.get("clipboard_image", True) else self.clip_cb.deselect()
        self.clip_cb.pack(anchor="w", pady=(2, 4))
        self.hist_cb = ctk.CTkCheckBox(f.body, text="保存历史记录",
                                       font=self._F.label)
        self.hist_cb.select() if self.cfg.get("history_enabled", True) else self.hist_cb.deselect()
        self.hist_cb.pack(anchor="w", pady=(2, 4))

        # 美化背景
        f = field("美化分享图背景")
        self.bg_seg = ctk.CTkSegmentedButton(f.body, values=["white", "gradient"],
                                             **theme.SEG_STYLE)
        self.bg_seg.set(self.cfg.get("beautify_bg", "white"))
        self.bg_seg.pack(side="left")

        # 底部分隔线 + 按钮：滚动区内容截断处有明确边界，不会像浮在字段上
        ctk.CTkFrame(outer, height=1, fg_color=theme.SEPARATOR).pack(
            fill="x", padx=theme.PAD, pady=(4, 0))
        bar = ctk.CTkFrame(outer, fg_color="transparent")
        bar.pack(fill="x", padx=theme.PAD, pady=(10, theme.PAD))
        ctk.CTkButton(bar, text="保存", width=110, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self._save).pack(side="right")
        ctk.CTkButton(bar, text="关闭", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM,
                      fg_color=theme.SURFACE_SOFT, border_width=1,
                      border_color=theme.SEPARATOR,
                      command=self.destroy).pack(side="right", padx=8)

    def _hotkey_row(self, field_block, var, command, primary=False):
        ctk.CTkLabel(field_block.body, textvariable=var, font=self._F.mono,
                     text_color=theme.ACCENT).pack(side="left")
        if primary:
            style = {"fg_color": theme.ACCENT}
        else:
            style = {"fg_color": theme.SURFACE_SOFT, "text_color": theme.FG,
                     "border_width": 1, "border_color": theme.SEPARATOR}
        ctk.CTkButton(field_block.body, text="更改…", width=90, height=30,
                      corner_radius=theme.RADIUS_SM, command=command,
                      **style).pack(side="right")

    def _entry(self, parent, value):
        e = ctk.CTkEntry(parent, height=34, corner_radius=theme.RADIUS_SM,
                         font=self._F.label, border_width=1,
                         border_color=theme.SEPARATOR)
        e.insert(0, value or "")
        e.pack(fill="x")
        return e

    def _combo(self, parent, value):
        """可编辑下拉框：既能直接输入，也能从后端模型列表里选。"""
        c = ctk.CTkComboBox(parent, height=34, corner_radius=theme.RADIUS_SM,
                            font=self._F.label, border_width=1,
                            border_color=theme.SEPARATOR,
                            values=[value] if value else [],
                            dropdown_font=self._F.label, state="normal")
        c.set(value or "")
        c.pack(fill="x")
        return c

    # ---------- 模型列表 ----------
    def refresh_models(self):
        """后台线程拉 /api/tags 并筛出 OCR 模型，主线程轮询取结果填充下拉框。

        注意：绝不能在子线程里调 self.after()/configure()——Tk 是单线程的，
        跨线程调用会抛 "main thread is not in main loop"，表现为「下拉没有模型」。
        """
        if self._refreshing:
            return
        self._refreshing = True
        self._set_hint("正在从后端拉取 OCR 模型…")
        url = self.url_e.get().strip() or self.cfg.get("ollama_url", "")

        def work():
            self._models_queue.put(ocr_core.list_ocr_models(url))

        threading.Thread(target=work, daemon=True).start()
        self._poll_models(0)

    def _poll_models(self, tries):
        try:
            names = self._models_queue.get_nowait()
        except queue.Empty:
            if tries < 60:                      # 最多等约 6 秒
                self.after(100, lambda: self._poll_models(tries + 1))
            else:
                self._refreshing = False
                self._set_hint("拉取超时：后端不可用？可直接手填模型名")
            return
        self._refreshing = False
        if not self.winfo_exists():
            return
        current = self.model_e.get()
        if names:
            self.model_e.configure(values=names)
            self._set_hint("只列出 OCR 模型（%d 个）；排版/翻译固定用默认模型"
                           % len(names))
        else:
            self._set_hint("没取到模型（后端不可用？），可直接手填模型名")
        self.model_e.set(current)

    def _set_hint(self, text):
        if self._model_hint is not None and self._model_hint.winfo_exists():
            self._model_hint.configure(text=text)

    # ---------- 开机启动（计划任务） ----------
    def _set_autostart_status(self, text, danger=False):
        if self.autostart_status.winfo_exists():
            self.autostart_status.configure(
                text=text, text_color=theme.DANGER if danger else theme.FG_SECONDARY)

    def _check_autostart(self):
        """打开设置时查一次任务是否存在（schtasks 查询可能要上百毫秒，放后台）。"""
        threading.Thread(target=self._autostart_worker, args=("check",),
                         daemon=True).start()
        self._poll_autostart()

    def _toggle_autostart(self):
        if self._autostart_busy:
            return
        want = bool(self.autostart_cb.get())
        self._autostart_busy = True
        self.autostart_cb.configure(state="disabled")
        if autostart.is_elevated():
            self._set_autostart_status("正在写入计划任务…")
        else:
            self._set_autostart_status("正在请求管理员权限（UAC）…")
        threading.Thread(target=self._autostart_worker,
                         args=("enable" if want else "disable",),
                         daemon=True).start()
        self._poll_autostart()

    def _autostart_worker(self, action):
        """后台线程：只做系统调用，结果经队列回主线程（Tk 单线程铁律）。"""
        try:
            if action == "check":
                state = autostart.is_enabled()
                msg = ("已启用：登录 Windows 后自动启动"
                       if state else "未启用（勾选后创建计划任务）")
                self._autostart_queue.put((True, msg, state))
                return
            ok, msg = (autostart.enable() if action == "enable"
                       else autostart.disable())
        except Exception as exc:  # noqa: BLE001 - 交给界面提示
            ok, msg = False, "%s: %s" % (type(exc).__name__, exc)
        try:
            state = autostart.is_enabled()
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

    def _pick_theme(self, value):
        """主题分段按钮：立即应用 + 落盘（无需再点保存）。"""
        theme.apply_theme(value)
        self.cfg["theme"] = value
        if self.on_theme:
            self.on_theme(value)

    def _open_hotkey(self):
        self.on_hotkey(self._hotkey_var)

    def _open_hotkey_only(self):
        if self.on_hotkey_only:
            self.on_hotkey_only(self._hotkey_only_var)

    def _save(self):
        values = {
            "theme": self.theme_seg.get(),
            "default_model": self.model_e.get().strip(),
            "ollama_url": self.url_e.get().strip(),
            "image_dir": self.imgdir_e.get().strip(),
            "export_dir": self.exportdir_e.get().strip(),
            "save_image": bool(self.save_cb.get()),
            "clipboard_image": bool(self.clip_cb.get()),
            "history_enabled": bool(self.hist_cb.get()),
            "beautify_bg": self.bg_seg.get(),
        }
        self.on_save(values)
