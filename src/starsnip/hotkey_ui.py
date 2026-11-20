"""快捷键设置对话框（customtkinter 重设计）。按下组合键即时预览，保存到 config。"""

import ctypes
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import theme

user32 = ctypes.WinDLL("user32", use_last_error=True)

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_KEY_MAP = {
    "return": "enter", "escape": "esc", "space": "space", "tab": "tab",
    "backspace": "backspace", "delete": "delete", "insert": "insert",
    "home": "home", "end": "end", "prior": "pageup", "next": "pagedown",
}


def _pressed(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def build_spec(keysym):
    """把 Tk keysym（+ 当前修饰键状态）转换为 'ctrl+alt+o'。"""
    key = (keysym or "").lower()
    if key in ("control_l", "control_r", "alt_l", "alt_r", "shift_l",
               "shift_r", "win_l", "win_r", "super_l", "super_r",
               "caps_lock", "num_lock"):
        return None
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        pass
    elif len(key) == 1 and key.isalnum():
        pass
    elif key in _KEY_MAP:
        key = _KEY_MAP[key]
    else:
        return None
    parts = []
    if _pressed(VK_CONTROL):
        parts.append("ctrl")
    if _pressed(VK_MENU):
        parts.append("alt")
    if _pressed(VK_SHIFT):
        parts.append("shift")
    if _pressed(VK_LWIN) or _pressed(VK_RWIN):
        parts.append("win")
    if not parts and not (key.startswith("f") and key[1:].isdigit()):
        return None
    return "+".join(parts + [key])


class HotkeyDialog(ctk.CTkToplevel):
    def __init__(self, master, current, on_save):
        super().__init__(master)
        self.title("星剪 · 设置快捷键")
        self.geometry("400x220")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._F = theme.Fonts()
        self.on_save = on_save
        self.spec = None

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(frame, text="请按下新的组合键", font=self._F.title,
                     text_color=theme.FG).pack(anchor="w")
        ctk.CTkLabel(frame, text="需包含 Ctrl / Alt / Shift / Win，或 F1–F24",
                     font=self._F.small,
                     text_color=theme.FG_SECONDARY).pack(anchor="w", pady=(2, 12))

        self.display = tk.StringVar(value=current)
        card = ctk.CTkFrame(frame, corner_radius=theme.RADIUS, fg_color=theme.SURFACE_SOFT,
                            border_width=1, border_color=theme.SEPARATOR, height=58)
        card.pack(fill="x")
        card.pack_propagate(False)
        ctk.CTkLabel(card, textvariable=self.display,
                     font=self._F.mono_big,
                     text_color=theme.ACCENT).place(relx=0.5, rely=0.5, anchor="center")

        self.hint = ctk.CTkLabel(frame, text="", font=self._F.small,
                                 text_color=theme.DANGER)
        self.hint.pack(anchor="w", pady=(8, 0))

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", side="bottom", pady=(14, 0))
        ctk.CTkButton(bar, text="保存并生效", width=120, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER,
                      command=self._save).pack(side="right")
        ctk.CTkButton(bar, text="取消", width=90, height=theme.CONTROL_H,
                      corner_radius=theme.RADIUS_SM, fg_color=theme.SURFACE_SOFT,
                      border_width=1, border_color=theme.SEPARATOR,
                      command=self.destroy).pack(side="right", padx=8)

        self.bind("<KeyPress>", self._on_key)
        self.focus_force()

    def _on_key(self, event):
        spec = build_spec(event.keysym)
        if spec:
            self.spec = spec
            self.display.set(" + ".join(s.upper() for s in spec.split("+")))
            self.hint.configure(text="")
        else:
            self.hint.configure(text="该按键不支持，请换一个（需组合键）")

    def _save(self):
        if not self.spec:
            messagebox.showinfo("设置快捷键", "请先按下新的组合键", parent=self)
            return
        self.on_save(self.spec)
        self.destroy()
