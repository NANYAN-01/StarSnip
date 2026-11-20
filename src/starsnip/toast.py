"""轻提示 Toast：右下角深色圆角 HUD，自动消失，带品牌强调点。

用原生 tk + Canvas 手绘圆角矩形（配合 -transparentcolor 实现真实圆角透明），
不依赖 CTk 的 Toplevel 行为，稳定可控。
"""

import tkinter as tk

from . import theme

_SENTINEL = "#010203"  # 透明哨兵色（几乎不会出现的颜色）


def _round_rect(canvas, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0,
           x1, y0 + r, x1, y0 + r, x1, y1 - r, x1, y1 - r, x1, y1,
           x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1, x0, y1,
           x0, y1 - r, x0, y1 - r, x0, y0 + r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Toast:
    def __init__(self, root, ms: int = 2000):
        self.root = root
        self.ms = ms
        self._win = None
        self._after = None

    def show(self, text, ms=None):
        self._destroy()
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.configure(bg=_SENTINEL)
            win.attributes("-transparentcolor", _SENTINEL)
        except tk.TclError:
            win.configure(bg="#1e1e22")
        try:
            win.attributes("-alpha", 0.97)
        except tk.TclError:
            pass

        dark = theme._mode_key() == "dark"
        hud = "#2C2C30" if dark else "#1C1C1E"
        fg = "#F2F2F7" if dark else "#FFFFFF"

        canvas = tk.Canvas(win, bg=_SENTINEL, highlightthickness=0)
        canvas.pack()
        label = canvas.create_text(0, 0, text=text, anchor="w", fill=fg,
                                   font=("Segoe UI", 11), width=520)
        bbox = canvas.bbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        dot_area, pad_x, pad_y = 22, 14, 10   # 左侧强调点宽度 + 内边距
        w, h = tw + pad_x * 2 + dot_area, th + pad_y * 2
        _round_rect(canvas, 0, 0, w, h, 13, fill=hud, outline="")
        cy = h / 2.0
        canvas.coords(label, pad_x + dot_area, cy)   # 绝对定位，不用相对 move
        canvas.create_oval(12, cy - 5, 22, cy + 5,
                           fill=theme.resolve(theme.ACCENT), outline="")
        canvas.tag_raise(label)
        canvas.configure(width=w, height=h)

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry("%dx%d%+d%+d" % (w, h, sw - w - 26, sh - h - 84))
        self._win = win
        self._after = self.root.after(ms or self.ms, self._destroy)

    def _destroy(self):
        if self._after:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None
