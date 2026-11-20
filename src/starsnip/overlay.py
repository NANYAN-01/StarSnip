"""全屏取景遮罩：拖拽框选识别区域（tkinter Canvas，多显示器/DPI 感知）。

视觉：截屏按原样铺满整个虚拟屏幕，选区外再叠一层点阵压暗，因此遮罩窗口
本身不需要改 alpha——取景边框、四角手柄、尺寸标签、顶部提示都清晰锐利。
保持原有交互契约（on_select(bbox) / on_cancel）。
"""

import tkinter as tk

ACCENT = "#6C5CE7"
STIPPLE = "gray50"          # tk 没有真 alpha，用点阵近似半透明压暗


def _rounded_rect(canvas, x0, y0, x1, y1, r, **kw):
    """用平滑多边形近似圆角矩形（Canvas 的 rectangle 不支持 radius）。"""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
           x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
           x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


class SelectionOverlay:
    def __init__(self, master, screen_bbox, on_select, on_cancel=None,
                 image=None, confirm=False):
        self._sx, self._sy, sw, sh = screen_bbox
        self._sw, self._sh = sw, sh
        self.on_select = on_select
        self.on_cancel = on_cancel
        self.confirm = confirm          # True: 拖完停留，等用户点 ✓/✕
        self._start = None
        self._rect = None
        self._handles = []
        self._toolbar = []              # 确认工具条的 canvas item id
        self._pending_bbox = None

        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.geometry("%dx%d%+d%+d" % (sw, sh, self._sx, self._sy))

        self.canvas = tk.Canvas(self.top, bg="#0b0b0d", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # 背景：优先铺截屏（不压暗），失败则退回纯深色
        self._bg_photo = self._to_photo(image, sw, sh)
        if self._bg_photo is not None:
            self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)
        else:
            self.canvas.create_rectangle(0, 0, sw, sh, fill="#0b0b0d",
                                         outline="")

        # 选区外的压暗层（4 块，随选区实时更新）
        self._dims = [self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#000000", outline="", stipple=STIPPLE)
            for _ in range(4)]
        self._dim_outside(0, 0, 0, 0)   # 初始：整屏压暗

        # 顶部提示胶囊
        if self.confirm:
            tip = "拖拽框选  ·  松开后点 ✓ 保存 / ✕ 取消"
        else:
            tip = "拖拽框选识别区域  ·  Enter 确认  ·  Esc 取消"
        tw = 12 * len(tip) + 48
        _rounded_rect(self.canvas, sw // 2 - tw // 2, 16,
                      sw // 2 + tw // 2, 54, 19,
                      fill="#1c1c1e", outline="")
        self.canvas.create_text(sw // 2, 35, fill="#f2f2f7",
                                font=("Segoe UI", 12), text=tip)

        # 尺寸标签（矩形底 + 文字，随拖拽移动）
        self._size_bg = self.canvas.create_rectangle(
            0, 0, 0, 0, fill=ACCENT, outline="", state="hidden")
        self._size_tx = self.canvas.create_text(
            0, 0, fill="#ffffff", font=("Consolas", 11, "bold"), text="",
            state="hidden")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Escape>", lambda e: self.cancel())
        self.top.bind("<Return>", lambda e: self._confirm_current())
        self.top.focus_force()

    # ---------- 背景 ----------
    @staticmethod
    def _to_photo(image, sw, sh):
        """截屏 -> PhotoImage（对齐虚拟屏幕尺寸）；失败返回 None。"""
        if image is None:
            return None
        try:
            from PIL import Image as PILImage
            from PIL import ImageTk

            from . import imgconv
            pil = imgconv.to_pil(image).convert("RGB")
            if pil.size != (sw, sh):
                pil = pil.resize((sw, sh), PILImage.LANCZOS)
            return ImageTk.PhotoImage(pil)
        except Exception:  # noqa: BLE001 - 退回纯色底
            return None

    # ---------- 绘制 ----------
    def _dim_outside(self, x1, y1, x2, y2):
        left, top = min(x1, x2), min(y1, y2)
        right, bottom = max(x1, x2), max(y1, y2)
        sw, sh = self._sw, self._sh
        boxes = [(0, 0, sw, top),          # 上
                 (0, bottom, sw, sh),      # 下
                 (0, top, left, bottom),   # 左
                 (right, top, sw, bottom)]
        for rect, box in zip(self._dims, boxes):
            self.canvas.coords(rect, *box)


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
        self._clear_toolbar()          # 重新框选：先撤掉上一次的 ✓/✕
        self._start = (event.x, event.y)
        self._draw(event.x, event.y, event.x, event.y)

    def _draw(self, x1, y1, x2, y2):
        self._dim_outside(x1, y1, x2, y2)
        self._redraw_frame(x1, y1, x2, y2)
        self._show_size(x1, y1, x2, y2)

    def _on_move(self, event):
        if not self._start:
            return
        x1, y1 = self._start
        self._draw(x1, y1, event.x, event.y)

    def _show_size(self, x1, y1, x2, y2):
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w < 2 and h < 2:
            self.canvas.itemconfigure(self._size_bg, state="hidden")
            self.canvas.itemconfigure(self._size_tx, state="hidden")
            return
        label = "%d × %d" % (w, h)
        lx, ly = min(x1, x2), min(y1, y2)
        tw, th = 8 * len(label) + 16, 20
        tx, ty = lx + 6, ly - th - 6
        if ty < 62:                       # 不要压住顶部提示胶囊
            ty = ly + 6
        tx = min(max(4, tx), self._sw - tw - 4)
        ty = min(max(4, ty), self._sh - th - 4)
        self.canvas.coords(self._size_bg, tx, ty, tx + tw, ty + th)
        self.canvas.coords(self._size_tx, tx + tw / 2, ty + th / 2)
        self.canvas.itemconfigure(self._size_tx, text=label)
        self.canvas.itemconfigure(self._size_bg, state="normal")
        self.canvas.itemconfigure(self._size_tx, state="normal")

    def _bbox(self, x1, y1, x2, y2):
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        return (self._sx + left, self._sy + top, width, height)

    # ---------- 确认工具条（仅截图模式）----------
    def _clear_toolbar(self):
        for item in self._toolbar:
            try:
                self.canvas.delete(item)
            except tk.TclError:
                pass
        self._toolbar = []
        self._pending_bbox = None

    def _show_toolbar(self, x1, y1, x2, y2):
        """在选区下方画 ✓ / ✕ 圆钮，停留等用户确认。"""
        self._clear_toolbar()
        self._pending_bbox = self._bbox(x1, y1, x2, y2)
        left, top = min(x1, x2), min(y1, y2)
        right, bottom = max(x1, x2), max(y1, y2)

        r, gap = 16, 10
        panel_w = r * 4 + gap * 2 + 78
        panel_h = r * 2 + 18
        px = right - panel_w
        py = bottom + 12
        if py + panel_h > self._sh - 8:      # 下方放不下就放到选区上方
            py = top - panel_h - 12
        px = max(8, min(px, self._sw - panel_w - 8))
        py = max(8, min(py, self._sh - panel_h - 8))

        self._toolbar.append(_rounded_rect(
            self.canvas, px, py, px + panel_w, py + panel_h, panel_h // 2,
            fill="#1c1c1e", outline="#3a3a3e"))
        ok_cx = px + 10 + r
        no_cx = ok_cx + r * 2 + gap
        cy = py + panel_h / 2
        for cx, color, glyph, tag in ((ok_cx, "#16A34A", "✓", "btn_ok"),
                                      (no_cx, "#DC2626", "✕", "btn_no")):
            self._toolbar.append(self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r, fill=color, outline="",
                tags=(tag,)))
            self._toolbar.append(self.canvas.create_text(
                cx, cy, text=glyph, fill="#ffffff",
                font=("Segoe UI", 14, "bold"), tags=(tag,)))
        self._toolbar.append(self.canvas.create_text(
            no_cx + r + 10, cy, text="Enter／Esc", anchor="w",
            fill="#8e8e93", font=("Segoe UI", 9)))

        self.canvas.tag_bind("btn_ok", "<Button-1>", lambda e: self._accept())
        self.canvas.tag_bind("btn_no", "<Button-1>", lambda e: self.cancel())
        self.top.focus_force()               # 拖完就能直接回车确认

    def _accept(self):
        bbox = self._pending_bbox
        self._clear_toolbar()
        if not bbox:
            self.cancel()
            return
        self.close()
        self.on_select(bbox)

    def _on_release(self, event):
        if not self._start:
            return
        x1, y1 = self._start
        width, height = abs(event.x - x1), abs(event.y - y1)
        self._start = None
        if width < 8 or height < 8:
            self.cancel()
            return
        if self.confirm:
            self._show_toolbar(x1, y1, event.x, event.y)
            return
        bbox = self._bbox(x1, y1, event.x, event.y)
        self.close()
        self.on_select(bbox)

    def _confirm_current(self):
        # Enter：有确认工具条时直接确认该选区，否则按当前矩形确认
        if self._pending_bbox:
            self._accept()
            return
        coords = self.canvas.coords(self._rect) if self._rect else None
        if not coords:
            self.cancel()
            return
        bbox = self._bbox(coords[0], coords[1], coords[2], coords[3])
        if bbox[2] < 8 or bbox[3] < 8:
            self.cancel()
            return
        self.close()
        self.on_select(bbox)

    def cancel(self):
        self.close()
        if self.on_cancel:
            self.on_cancel()

    def close(self):
        self._bg_photo = None
        self._toolbar = []
        try:
            self.top.destroy()
        except tk.TclError:
            pass
