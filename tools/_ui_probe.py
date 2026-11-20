"""一次性 UI 探针：用样例数据渲染各窗口，截取客户区供视觉验收。

不联网、不注册全局热键、不截全屏遮罩；逐个窗口 lift+update 后截图并销毁。
产物： tools/_shots/*.png
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402

from starsnip import capture, theme  # noqa: E402
from starsnip.history import History  # noqa: E402
from starsnip.ui import ResultWindow, VerifyWindow  # noqa: E402
from starsnip.history_ui import HistoryWindow  # noqa: E402
from starsnip.settings_ui import SettingsWindow  # noqa: E402
from starsnip.hotkey_ui import HotkeyDialog  # noqa: E402
from starsnip.toast import Toast  # noqa: E402

SHOTS = os.path.join(HERE, "_shots")
os.makedirs(SHOTS, exist_ok=True)

SAMPLE = ("项目\t预算\t状态\n"
          "星剪 1.0\t12 万\t已完成\n"
          "登录系统\t3 万\t进行中\n"
          "移动端\t8 万\t未开始")

TABLE_MD = ("| 序号 | 商品 | 单价 | 数量 | 金额 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | 笔记本 | 6899.00 | 2 | 13798.00 |\n"
            "| 2 | 鼠标 | 649.00 | 8 | 5192.00 |\n"
            "| 合计 |  |  |  | 18990.00 |")

CFG = {"hotkey": "ctrl+alt+o", "default_model": "glm-ocr:latest",
       "layout_model": "qwen3.5:4b", "ollama_url": "http://127.0.0.1:11434",
       "verify_models": ["glm-ocr:latest", "richardyoung/unlimited-ocr:latest"],
       "theme": "dark", "beautify_bg": "gradient", "joint_enabled": False,
       "history_enabled": True, "image_dir": "", "export_dir": ""}


def shot(win, name):
    win.update_idletasks()
    # 必须置顶再截图：否则截到的是被别的窗口遮住的桌面内容
    try:
        win.attributes("-topmost", True)
        win.deiconify()
        win.lift()
        win.focus_force()
    except Exception:  # noqa: BLE001
        pass
    for _ in range(6):
        win.update()
    capture.enable_dpi_awareness()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    full = capture.capture_screen()
    crop = full.crop(x - full.origin[0], y - full.origin[1], w, h)
    out = os.path.join(SHOTS, name + ".png")
    with open(out, "wb") as f:
        f.write(crop.to_png())
    print("saved", out, "%dx%d" % (w, h))
    win.destroy()
    win.update_idletasks()


def main():
    appearance = "dark"
    capture.enable_dpi_awareness()   # 与真实启动一致：建根窗口前声明 DPI 感知
    theme.apply_theme(appearance)
    root = ctk.CTk()
    root.withdraw()

    # 1) ResultWindow 文本视图（深色）
    r = ResultWindow(root)
    r.geometry("+120+80")
    r.show_result({"ok": True, "model": "glm-ocr:latest", "mode": "generate",
                   "elapsed_ms": 452, "text": SAMPLE})
    shot(r, "01_result_text_dark")

    # 2) ResultWindow 表格视图（浅色）
    theme.apply_theme("light")
    r2 = ResultWindow(root)
    r2.geometry("+120+80")
    r2.show_result({"ok": True, "model": "glm-ocr:latest", "mode": "generate",
                    "elapsed_ms": 511, "text": TABLE_MD})
    r2.seg.set("表格")
    r2._switch_view("表格")
    shot(r2, "02_result_table_light")
    theme.apply_theme("dark")

    # 3) VerifyWindow 交叉校验
    results = [
        {"model": "glm-ocr:latest", "ok": True, "text": "第一行一致\n第二行只有主模型有\n合计 100"},
        {"model": "unlimited-ocr", "ok": True, "text": "第一行一致\n合计 100"},
    ]
    v = VerifyWindow(root, results, {1})
    v.geometry("+160+120")
    shot(v, "03_verify_dark")

    # 4) HistoryWindow
    base = tempfile.mkdtemp(prefix="probe_hist_")
    th = os.path.join(base, "thumbs")
    os.makedirs(th, exist_ok=True)
    thumb = Image.new("RGB", (300, 200), (245, 244, 250))
    thumb_fp = os.path.join(base, "t.png")
    thumb.save(thumb_fp)
    with open(thumb_fp, "rb") as f:
        thumb_bytes = f.read()
    hist = History(base_dir=base, keep=500)
    for i in range(6):
        hist.add(source="hotkey", mode="text", model="glm-ocr:latest",
                 elapsed_ms=400 + i * 11,
                 text="示例记录 %d：星剪识别的一条文字内容，可用于搜索与预览。" % i,
                 thumb_png=thumb_bytes)
    hw = HistoryWindow(root, hist)
    hw.geometry("+100+60")
    hw.tree.selection_set("1")
    hw._on_select()
    shot(hw, "04_history_dark")

    # 5) SettingsWindow
    st = SettingsWindow(root, CFG, lambda v: None, lambda var: None)
    st.geometry("+260+40")
    shot(st, "05_settings_dark")

    # 6) HotkeyDialog
    hk = HotkeyDialog(root, "ctrl+alt+o", lambda s: None)
    hk.geometry("+360+160")
    shot(hk, "06_hotkey_dark")

    # 7) 取景遮罩：铺截屏 + 压暗 + 选区 + 尺寸标签
    from starsnip.overlay import SelectionOverlay
    ov_img = capture.capture_screen()
    ov = SelectionOverlay(root, (120, 90, 760, 460),
                          on_select=lambda b: None, on_cancel=lambda: None,
                          image=ov_img)

    def drag():
        import types
        ov._on_press(types.SimpleNamespace(x=80, y=90))
        ov._on_move(types.SimpleNamespace(x=520, y=300))

    for _ in range(4):
        root.update()
    drag()
    for _ in range(4):
        root.update()
    cap = capture.capture_screen()
    x, y = ov.top.winfo_rootx(), ov.top.winfo_rooty()
    w, h = ov.top.winfo_width(), ov.top.winfo_height()
    crop = cap.crop(x - cap.origin[0], y - cap.origin[1], w, h)
    out = os.path.join(SHOTS, "07_overlay_dark.png")
    with open(out, "wb") as f:
        f.write(crop.to_png())
    print("saved", out, "%dx%d" % (w, h))
    ov.close()

    # 8) Toast（深色 HUD）
    toast = Toast(root, 3000)
    toast.show("星剪已启动 · 截图已保存到剪贴板")
    root.update()
    cap = capture.capture_screen()
    tw = toast._win
    x, y = tw.winfo_rootx(), tw.winfo_rooty()
    w, h = tw.winfo_width(), tw.winfo_height()
    crop = cap.crop(x - cap.origin[0], y - cap.origin[1], w, h)
    out = os.path.join(SHOTS, "08_toast_dark.png")
    with open(out, "wb") as f:
        f.write(crop.to_png())
    print("saved", out, "%dx%d" % (w, h))
    toast._destroy()

    root.update()
    root.destroy()
    print("DONE")


if __name__ == "__main__":
    main()
