"""贴图钉屏（Pin）：把截图钉在桌面最上层，可拖动、滚轮缩放、复制、关闭。

借鉴 Snipaste/XPin 的贴图：用原生 tk + PIL 帧显示，交互稳定。
"""

import os

import tkinter as tk
from PIL import Image, ImageTk

from . import clipboard_image, imgconv, paths, screenfiles


class PinWindow:
    _scale_steps = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]

    def __init__(self, master, pil, screen_pos=None, alpha=1.0, on_close=None):
        self.pil = pil.convert("RGB")
        self.orig_w, self.orig_h = self.pil.size
        self.scale = 1.0
        self.on_close = on_close
        self._drag = None

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", max(0.4, min(1.0, alpha)))
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.win, highlightthickness=2,
                                highlightbackground="#6C5CE7", bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._photo = None

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<MouseWheel>", self._zoom)
        self.canvas.bind("<Double-Button-1>", lambda e: self.close())
        self.canvas.bind("<Button-3>", self._menu)
        self.win.bind("<Escape>", lambda e: self.close())

        self._render()
        x, y = screen_pos or (120, 120)
        self.win.geometry("%dx%d%+d%+d" % (self._cur_w(), self._cur_h(), x, y))

    # ---------- 显示 ----------
    def _cur_w(self):
        return max(20, int(self.orig_w * self.scale))

    def _cur_h(self):
        return max(20, int(self.orig_h * self.scale))

    def _render(self):
        w, h = self._cur_w(), self._cur_h()
        img = self.pil.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(width=w, height=h, bg="#2c2c30")

    def _reposition(self, x, y):
        self.win.geometry("%dx%d%+d%+d" % (self._cur_w(), self._cur_h(), x, y))

    # ---------- 交互 ----------
    def _press(self, event):
        self._drag = (event.x_root - self.win.winfo_x(),
                      event.y_root - self.win.winfo_y())

    def _move(self, event):
        if not self._drag:
            return
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self._reposition(x, y)

    def _zoom(self, event):
        factor = 1.0
        delta = event.delta
        if delta:
            factor = 1.1 if delta > 0 else 0.9
        new = max(self._scale_steps[0],
                  min(self._scale_steps[-1], self.scale * factor))
        cx = self.win.winfo_x() + self._cur_w() // 2
        cy = self.win.winfo_y() + self._cur_h() // 2
        self.scale = new
        self._render()
        self._reposition(cx - self._cur_w() // 2, cy - self._cur_h() // 2)

    def _menu(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="复制图片", command=self._copy)
        menu.add_command(label="另存为 PNG", command=self._save)
        menu.add_command(label="原始大小", command=self._reset)
        menu.add_separator()
        menu.add_command(label="关闭（Esc）", command=self.close)
        menu.tk_popup(event.x_root, event.y_root)

    # ---------- 动作 ----------
    def _copy(self):
        data, w, h = imgconv.to_bgra(self.pil)
        try:
            clipboard_image.copy_image(data, w, h)
        except OSError:
            pass

    def _save(self):
        d = paths.pictures_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "StarSnip_pin_%s.png" % screenfiles.timestamp())
        self.pil.save(path, "PNG")
        try:
            os.startfile(d)
        except OSError:
            pass

    def _reset(self):
        cx = self.win.winfo_x() + self._cur_w() // 2
        cy = self.win.winfo_y() + self._cur_h() // 2
        self.scale = 1.0
        self._render()
        self._reposition(cx - self._cur_w() // 2, cy - self._cur_h() // 2)

    def close(self):
        if self.on_close:
            self.on_close(self)
        try:
            self.win.destroy()
        except tk.TclError:
            pass
