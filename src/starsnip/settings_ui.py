"""设置窗口：集中配置主题、快捷键、识别/排版模型、后端与目录、历史与联合识别。

保存后逐项写回 config.json（保留其它键），主题即时生效，
快捷键调用现有录入对话框。
"""

import customtkinter as ctk

from . import theme


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
    def __init__(self, master, cfg, on_save, on_hotkey):
        super().__init__(master)
        self.cfg = cfg
        self.on_save = on_save
        self.on_hotkey = on_hotkey
        self.title("星剪 · 设置")
        self.geometry("540x740")
        self.minsize(460, 520)

        self._hotkey_var = ctk.StringVar(value=cfg.get("hotkey", ""))
        self._build()

    def _build(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD, pady=(theme.PAD, 6))
        logo = theme.logo_image(22)
        if logo:
            ctk.CTkLabel(head, text="", image=logo).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(head, text="设置", font=theme.font(16, "bold"), text_color=theme.FG).pack(side="left")

        scroll = ctk.CTkFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=theme.PAD)

        # 主题
        f = _Field(scroll, "界面主题", "system = 跟随系统自动深浅色")
        self.theme_seg = ctk.CTkSegmentedButton(
            f.body, values=["system", "light", "dark"], command=None)
        self.theme_seg.set(self.cfg.get("theme", "system"))
        self.theme_seg.pack(side="left")

        # 快捷键
        f = _Field(scroll, "截图快捷键", "点击右侧按钮，按下新的组合键即可")
        ctk.CTkLabel(f.body, textvariable=self._hotkey_var, font=theme.font(13, mono=True),
                     text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(f.body, text="更改…", width=90, height=30,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      command=self._open_hotkey).pack(side="right")

        # 模型与后端
        f = _Field(scroll, "OCR 识别模型")
        self.model_e = self._entry(f.body, self.cfg.get("default_model", ""))

        f = _Field(scroll, "排版 / 翻译模型", "用于 AI 排版导出与一键翻译")
        self.layout_e = self._entry(f.body, self.cfg.get("layout_model", ""))

        f = _Field(scroll, "后端 Ollama 地址")
        self.url_e = self._entry(f.body, self.cfg.get("ollama_url", ""))

        # 目录
        f = _Field(scroll, "截图保存目录", "留空 = 图片\\StarSnip")
        self.imgdir_e = self._entry(f.body, self.cfg.get("image_dir", ""))

        f = _Field(scroll, "导出目录", "留空 = 文档\\StarSnip")
        self.exportdir_e = self._entry(f.body, self.cfg.get("export_dir", ""))

        # 开关
        f = _Field(scroll, "识别选项")
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
        f = _Field(scroll, "美化分享图背景")
        self.bg_seg = ctk.CTkSegmentedButton(f.body, values=["white", "gradient"])
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

    def _open_hotkey(self):
        self.on_hotkey(self._hotkey_var)

    def _save(self):
        values = {
            "theme": self.theme_seg.get(),
            "default_model": self.model_e.get().strip(),
            "layout_model": self.layout_e.get().strip(),
            "ollama_url": self.url_e.get().strip(),
            "image_dir": self.imgdir_e.get().strip(),
            "export_dir": self.exportdir_e.get().strip(),
            "joint_enabled": bool(self.joint_cb.get()),
            "clipboard_image": bool(self.clip_cb.get()),
            "history_enabled": bool(self.hist_cb.get()),
            "beautify_bg": self.bg_seg.get(),
        }
        self.on_save(values)
