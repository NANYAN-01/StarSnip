"""全屏取景遮罩：拖拽框选识别区域（tkinter Canvas，多显示器/DPI 感知）。

视觉现代化：暗化背景、强调色取景边框 + 四角手柄、跟随光标的实时尺寸标签、
顶部提示胶囊。保持原有交互契约（on_select(bbox) / on_cancel）。
"""

import tkinter as tk

ACCENT = "#6C5CE7"


class SelectionOverlay:
    def __init__(self, master, screen_bbox, on_select, on_cancel=None):
        self._sx, self._sy, sw, sh = screen_bbox
        self.on_select = on_select
        self.on_cancel = on_cancel
        self._start = None
        self._rect = None
        self._handles = []
        self._size_id = None

        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-alpha", 0.42)
        except tk.TclError:
            pass
        self.top.geometry("%dx%d%+d%+d" % (sw, sh, self._sx, self._sy))

        self.canvas = tk.Canvas(self.top, bg="#0b0b0d", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # 顶部提示胶囊
        tip = "拖拽框选识别区域  ·  Enter 确认  ·  Esc 取消"
        tw = len(tip) * 9 + 40
        self.canvas.create_rectangle(
            sw // 2 - tw // 2, 16, sw // 2 + tw // 2, 52, radius=16,
            fill="#1c1c1e", outline="", width=0)
        self.canvas.create_text(sw // 2, 34, fill="#f2f2f7",
                                font=("Segoe UI", 13), text=tip)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Escape>", lambda e: self.cancel())
        self.top.bind("<Return>", lambda e: self._confirm_current())
        self.top.focus_force()

    def _redraw_frame(self, x1, y1, x2, y2):
        for item in self._handles + [self._rect]:
            if item:
                self.canvas.delete(item)
        self._handles = []
        self._rect = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline=ACCENT, width=2)
        for (hx, hy) in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            self._handles.append(self.canvas.create_rectangle(
                hx - 4, hy - 4, hx + 4, hy + 4, fill=ACCENT, outline=""))

    def _on_press(self, event):
        self._start = (event.x, event.y)
        self._draw(event.x, event.y, event.x, event.y)

    def _draw(self, x1, y1, x2, y2):
        self._redraw_frame(x1, y1, x2, y2)
        self._show_size(x1, y1, x2, y2)

    def _on_move(self, event):
        if not self._start:
            return
        x1, y1 = self._start
        self._draw(x1, y1, event.x, event.y)

    def _show_size(self, x1, y1, x2, y2):
        if self._size_id:
            self.canvas.delete(self._size_id)
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        label = " %d × %d " % (w, h)
        lx, ly = min(x1, x2), min(y1, y2)
        self._size_id = self.canvas.create_text(
            lx + 4, ly - 16, anchor="w", fill="#ffffff",
            font=("Consolas", 11, "bold"), text=label,
            bbox=[lx - 4, ly - 30, lx + 4 + len(label) * 8, ly - 4],
            bg="#6c5ce7")

    def _bbox(self, x1, y1, x2, y2):
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        return (self._sx + left, self._sy + top, width, height)

    def _on_release(self, event):
        if not self._start:
            return
        x1, y1 = self._start
        width, height = abs(event.x - x1), abs(event.y - y1)
        self._start = None
        if width < 8 or height < 8:
            self.cancel()
            return
        bbox = self._bbox(x1, y1, event.x, event.y)
        self.close()
        self.on_select(bbox)

    def _confirm_current(self):
        # Enter 直接确认当前已选区域
        coords = self.canvas.coords(self._rect) if self._rect else None
        if not coords:
            self.cancel()
            return
        bbox = self._bbox(coords[0], coords[1], coords[2], coords[3])
        self.close()
        if bbox[2] >= 8 and bbox[3] >= 8:
            self.on_select(bbox)
        else:
            self.cancel()

    def cancel(self):
        self.close()
        if self.on_cancel:
            self.on_cancel()

    def close(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
