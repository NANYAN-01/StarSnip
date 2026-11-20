"""设置窗口：集中配置主题、快捷键、识别/排版模型、后端与目录、历史与联合识别。

保存后逐项写回 config.json（保留其它键），主题即时生效，
快捷键调用现有录入对话框。
"""

import queue
import threading

import customtkinter as ctk

from . import ocr_core, theme


class _Field(ctk.CTkFrame):
    def __init__(self, parent, label, hint=""):
        super().__init__(parent, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=theme.font(13),
                     text_color=theme.FG).pack(anchor="w")
        if hint:
            ctk.CTkLabel(self, text=hint, font=theme.font(12),
                         text_color=theme.FG_SECONDARY).pack(anchor="w", pady=(0, 4))
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
        self.geometry("540x740")
        self.minsize(460, 520)

        self._hotkey_var = ctk.StringVar(value=cfg.get("hotkey", ""))
        self._hotkey_only_var = ctk.StringVar(
            value=cfg.get("hotkey_capture_only", ""))
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
        ctk.CTkLabel(head, text="设置", font=theme.font(16, "bold"), text_color=theme.FG).pack(side="left")

        # 内容区可滚动：字段较多，窗口高度不够时不会把底部按钮挤掉
        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent",
                                        scrollbar_button_color=theme.SEPARATOR,
                                        scrollbar_button_hover_color=theme.FG_SECONDARY)
        scroll.pack(fill="both", expand=True, padx=theme.PAD)

        def field(label, hint=""):
            """建一个字段块并 pack 进滚动区（之前漏了这一步，导致设置窗口全空）。"""
            block = _Field(scroll, label, hint)
            block.pack(fill="x")
            return block

        # 主题（点一下立即生效并保存，不需要再点「保存」）
        f = field("界面主题", "点击即时生效；system = 跟随系统自动深浅色")
        self.theme_seg = ctk.CTkSegmentedButton(
            f.body, values=["system", "light", "dark"],
            command=self._pick_theme, **theme.SEG_STYLE)
        self.theme_seg.set(self.cfg.get("theme", "system"))
        self.theme_seg.pack(side="left")

        # 快捷键（识别 / 仅截图）
        f = field("截图识别快捷键", "拖拽后立即 OCR，默认 Ctrl+2")
        ctk.CTkLabel(f.body, textvariable=self._hotkey_var, font=theme.font(13, mono=True),
                     text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(f.body, text="更改…", width=90, height=30,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self._open_hotkey).pack(side="right")

        f = field("仅截图快捷键", "拖拽后停留，点 ✓ 才保存/进剪贴板，默认 Ctrl+1")
        ctk.CTkLabel(f.body, textvariable=self._hotkey_only_var,
                     font=theme.font(13, mono=True),
                     text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(f.body, text="更改…", width=90, height=30,
                      corner_radius=theme.RADIUS_SM,
                      fg_color=theme.SURFACE_SOFT, text_color=theme.FG,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self._open_hotkey_only).pack(side="right")

        # 模型与后端
        f = field("OCR 识别模型", "点右侧「刷新」可从后端重新拉取模型列表")
        self.model_e = self._combo(f.body, self.cfg.get("default_model", ""))
        ctk.CTkButton(f.body, text="刷新列表", width=88, height=30,
                      corner_radius=theme.RADIUS_SM,
                      fg_color=theme.SURFACE_SOFT, text_color=theme.FG,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self.refresh_models).pack(side="right", padx=(8, 0))

        f = field("排版 / 翻译模型", "用于 AI 排版导出与一键翻译")
        self.layout_e = self._combo(f.body, self.cfg.get("layout_model", ""))

        f = field("后端 Ollama 地址", "内网地址建议写在 config.local.json，避免提交进仓库")
        self.url_e = self._entry(f.body, self.cfg.get("ollama_url", ""))

        # 目录
        f = field("截图保存目录", "留空 = 图片\\StarSnip")
        self.imgdir_e = self._entry(f.body, self.cfg.get("image_dir", ""))

        f = field("导出目录", "留空 = 文档\\StarSnip")
        self.exportdir_e = self._entry(f.body, self.cfg.get("export_dir", ""))

        # 开关
        f = field("识别选项")
        self.auto_cb = ctk.CTkCheckBox(
            f.body, text="截图后自动识别（关闭 = 只截图/存剪贴板）",
            font=theme.font(13))
        self.auto_cb.select() if self.cfg.get("auto_ocr", True) else self.auto_cb.deselect()
        self.auto_cb.pack(anchor="w", pady=(2, 4))
        self.joint_cb = ctk.CTkCheckBox(f.body, text="启用联合识别（多模型）",
                                        font=theme.font(13))
        self.joint_cb.select() if self.cfg.get("joint_enabled") else self.joint_cb.deselect()
        self.joint_cb.pack(anchor="w", pady=(2, 4))
        self.clip_cb = ctk.CTkCheckBox(f.body, text="截图写入系统剪贴板",
                                       font=theme.font(13))
        self.clip_cb.select() if self.cfg.get("clipboard_image", True) else self.clip_cb.deselect()
        self.clip_cb.pack(anchor="w", pady=(2, 4))
        self.hist_cb = ctk.CTkCheckBox(f.body, text="保存历史记录", font=theme.font(13))
        self.hist_cb.select() if self.cfg.get("history_enabled", True) else self.hist_cb.deselect()
        self.hist_cb.pack(anchor="w", pady=(2, 4))

        # 美化背景
        f = field("美化分享图背景")
        self.bg_seg = ctk.CTkSegmentedButton(f.body, values=["white", "gradient"],
                                             **theme.SEG_STYLE)
        self.bg_seg.set(self.cfg.get("beautify_bg", "white"))
        self.bg_seg.pack(side="left")

        # 底部按钮
        bar = ctk.CTkFrame(outer, fg_color="transparent")
        bar.pack(fill="x", padx=theme.PAD, pady=(6, theme.PAD))
        ctk.CTkButton(bar, text="保存", width=110, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self._save).pack(side="right")
        ctk.CTkButton(bar, text="关闭", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM,
                          fg_color=theme.SURFACE_SOFT, border_width=1,
                      border_color=theme.SEPARATOR,
                      command=self.destroy).pack(side="right", padx=8)

    @staticmethod
    def _entry(parent, value):
        e = ctk.CTkEntry(parent, height=34, corner_radius=theme.RADIUS_SM,
                         font=theme.font(13), border_width=1,
                         border_color=theme.SEPARATOR)
        e.insert(0, value or "")
        e.pack(fill="x")
        return e

    @staticmethod
    def _combo(parent, value):
        """可编辑下拉框：既能直接输入，也能从后端模型列表里选。"""
        c = ctk.CTkComboBox(parent, height=34, corner_radius=theme.RADIUS_SM,
                            font=theme.font(13), border_width=1,
                            border_color=theme.SEPARATOR,
                            values=[value] if value else [],
                            dropdown_font=theme.font(13), state="normal")
        c.set(value or "")
        c.pack(fill="x", padx=(0, 96))   # 给右侧「刷新列表」按钮留位置
        return c

    # ---------- 模型列表 ----------
    def refresh_models(self, notify=None):
        """后台线程拉 /api/tags，主线程轮询取结果填充下拉框。

        注意：绝不能在子线程里调 self.after()/configure()——Tk 是单线程的，
        跨线程调用会抛 "main thread is not in main loop"，表现为「下拉没有模型」。
        """
        url = self.url_e.get().strip() or self.cfg.get("ollama_url", "")
        self._models_queue = queue.Queue()

        def work():
            self._models_queue.put(ocr_core.list_models(url))

        threading.Thread(target=work, daemon=True).start()
        self._poll_models(0, notify)

    def _poll_models(self, tries, notify):
        try:
            names = self._models_queue.get_nowait()
        except queue.Empty:
            if tries < 60:                      # 最多等约 6 秒
                self.after(100, lambda: self._poll_models(tries + 1, notify))
            return
        if not self.winfo_exists():
            return
        for combo in (self.model_e, self.layout_e):
            current = combo.get()
            combo.configure(values=names or [current])
            combo.set(current)
        if notify:
            notify(names)

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
            "layout_model": self.layout_e.get().strip(),
            "ollama_url": self.url_e.get().strip(),
            "image_dir": self.imgdir_e.get().strip(),
            "export_dir": self.exportdir_e.get().strip(),
            "auto_ocr": bool(self.auto_cb.get()),
            "joint_enabled": bool(self.joint_cb.get()),
            "clipboard_image": bool(self.clip_cb.get()),
            "history_enabled": bool(self.hist_cb.get()),
            "beautify_bg": self.bg_seg.get(),
        }
        self.on_save(values)
