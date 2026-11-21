"""全界面结构化冒烟测试：逐个窗口真实创建、检查控件已布局、按钮回调可用。

覆盖：设置 / 结果 / 交叉校验 / 历史 / 快捷键对话框 / Toast / 取景遮罩 / 贴图 / 美化。
需要真实桌面会话（会短暂创建置顶窗口），不联网、不注册全局热键。

回归背景：设置窗口的字段忘了 pack（界面全空）、遮罩用了非法 Canvas 选项
（按热键直接抛 TclError）、Toast 文字用相对 move（文字被裁到边外）。
"""

import os
import sys
import tempfile
import time
import types

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402

from starsnip import beautify, capture, config, theme  # noqa: E402
from starsnip.history import History  # noqa: E402
from starsnip.history_ui import HistoryWindow  # noqa: E402
from starsnip.hotkey_ui import HotkeyDialog  # noqa: E402
from starsnip.overlay import SelectionOverlay  # noqa: E402
from starsnip.pin import PinWindow  # noqa: E402
from starsnip.settings_ui import SettingsWindow  # noqa: E402
from starsnip.toast import Toast  # noqa: E402
from starsnip.ui import ResultWindow  # noqa: E402

TABLE_MD = ("| 序号 | 商品 | 金额 |\n| --- | --- | --- |\n"
            "| 1 | 笔记本 | 13798.00 |\n| 2 | 鼠标 | 5192.00 |")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  ✗ %s" % msg)
    else:
        print("  ✓ %s" % msg)


def mapped_children(widget):
    return [c for c in widget.winfo_children() if c.winfo_manager()]


def find_widget(widget, cls_name):
    """递归找第一个类名为 cls_name 的子控件（CTk 内部会套多层 canvas）。"""
    for child in widget.winfo_children():
        if type(child).__name__ == cls_name:
            return child
        found = find_widget(child, cls_name)
        if found is not None:
            return found
    return None


def test_settings(root):
    print("[设置窗口]")
    cfg = config.load()
    saved = {}
    themes = []
    win = SettingsWindow(root, cfg, lambda v: saved.update(v),
                         lambda var: None, on_theme=themes.append)
    root.update()

    scroll = find_widget(win, "CTkScrollableFrame")
    check(scroll is not None, "设置窗口有可滚动内容区")
    # 版式改成了「左导航 + 行式设置卡」，断言从 _Field 改为 _SettingsRow
    rows = [r for page in win._rows.values() for r in page]
    check(len(rows) >= 14, "设置卡数量 ≥ 14（实际 %d）" % len(rows))
    check(all(r.winfo_manager() for r in rows), "所有设置卡都已布局（非空窗口）")
    check(all(r.winfo_height() > 10 for r in win._rows[win._active]),
          "当前页设置卡有实际高度")
    check(len(win._pages) == 5, "五个分页（实际 %d）" % len(win._pages))

    # 分页：切页后只有当前页在布局，标题跟着变
    win._show_page("keys")
    root.update()
    check(win._active == "keys" and win._title.cget("text") == "快捷与交互",
          "切到「快捷与交互」页")
    check(bool(win._pages["keys"].winfo_manager())
          and not win._pages["general"].winfo_manager(),
          "切页后只有当前页在布局")
    win._show_page("general")
    root.update()

    # 搜索：按标题/描述过滤本页设置卡
    before = len([r for r in win._rows["general"] if r.winfo_manager()])
    win._search.entry.insert(0, "剪贴板")
    win._filter()
    root.update()
    hits = [r.title_text for r in win._rows["general"] if r.winfo_manager()]
    check(before > len(hits) == 1 and "剪贴板" in hits[0],
          "搜索过滤生效（命中 %s）" % (hits,))
    win._search.clear()
    win._filter()
    root.update()

    # 模型必须是可下拉的 Combobox（之前是纯输入框，用户无法选择）
    check(type(win.model_e).__name__ == "CTkComboBox", "OCR 模型是可下拉框")
    check(hasattr(win, "refresh_models"), "支持从后端刷新模型列表")
    check(not hasattr(win, "layout_e"), "排版模型不再提供选择（固定用默认模型）")

    check(win.model_e.get().strip() != "", "OCR 角色有模型名（%s）"
          % win.model_e.get())
    check(win.url_e.get().startswith("http"), "OCR 角色有 BaseURL（%s）"
          % win.url_e.get())
    check(len(win._models) == 3, "三个角色各有一份配置")
    check(win._role == "ocr", "默认编辑 OCR 角色")
    check(win._hotkey_var.get() == cfg.get("hotkey"), "快捷键显示与配置一致")

    # 主题：点一下立即生效（不需要再点保存）
    win._pick_theme("dark")
    root.update()
    check(ctk.get_appearance_mode() == "Dark", "主题即时切换为 Dark")
    check(themes and themes[-1] == "dark", "主题变化回传给 App 落盘")
    win._pick_theme("light")
    root.update()
    check(ctk.get_appearance_mode() == "Light", "主题可切回 Light")

    # 选预置厂商 → BaseURL 自动填；切角色 → 字段跟着换
    win._pick_provider("DeepSeek")
    check(win.url_e.get() == "https://api.deepseek.com",
          "选 DeepSeek 自动填 BaseURL（%s）" % win.url_e.get())
    check(win._auth_row.hidden and win._stream_row.hidden,
          "预置厂商不显示「鉴权头 / 流式」")
    win._pick_provider("自定义 API")
    root.update()
    check(not win._auth_row.hidden and not win._stream_row.hidden,
          "自定义 API 才显示「鉴权头 / 流式」")
    check(bool(win._auth_row.winfo_manager()) and
          bool(win._stream_row.winfo_manager()), "高级项显示后确实在布局里")
    win._pick_provider("DeepSeek")
    win._pick_role("主 LLM")
    check(win._role == "main", "切到主 LLM 角色")
    win._pick_role("OCR 模型")
    check(win._role == "ocr" and win.url_e.get() == "https://api.deepseek.com",
          "切回 OCR 角色后配置还在")
    win._pick_provider("Ollama（本地）")
    check(win.url_e.get().startswith("http://127.0.0.1"),
          "切回 Ollama 自动填本地地址")

    win._save()
    expect = {"models", "theme", "image_dir",
              "export_dir", "save_image", "clipboard_image",
              "history_enabled", "beautify_bg"}
    check(isinstance(saved.get("models"), dict)
          and set(saved["models"]) == {"main", "ocr", "layout"},
          "保存回传了三个角色的模型配置")
    check(expect <= set(saved), "保存回传了全部设置键")
    check("layout_model" not in saved, "保存不会改动排版模型（界面不提供）")

    # 关于页：版本 + 检查更新 + 仓库入口
    win._show_page("about")
    root.update()
    titles = [r.title_text for r in win._rows["about"]]
    check("版本" in titles and "GitHub 仓库" in titles,
          "关于页有版本与 GitHub 入口（%s）" % titles)
    check(win.update_btn.cget("text") == "检查更新", "关于页有「检查更新」按钮")
    repo_row = [r for r in win._rows["about"] if r.title_text == "GitHub 仓库"][0]
    check("github.com/NANYAN-01/StarSnip" in repo_row.desc_text,
          "仓库地址写对了")
    win._show_page("general")
    root.update()

    # 开机启动：等初始体检结束，再用桩跑开启/关闭（不碰真实注册表）
    deadline = time.time() + 5
    while time.time() < deadline and win._autostart_busy:
        root.update()
        time.sleep(0.02)
    check(not win._autostart_busy, "开机启动初始状态检查完成")
    check(hasattr(win, "autostart_cb"), "开机启动开关已布局")
    check(hasattr(win, "startup_menu"), "启动方式下拉已布局")

    from starsnip import startup as startup_mod
    state = {"on": False}

    def _fake_status():
        return {"enabled": state["on"], "effective": state["on"],
                "mode": "run" if state["on"] else "none", "warnings": [],
                "policy": [], "task": False, "command": "",
                "run": {"present": state["on"], "current": True,
                        "approved": "enabled", "command": ""},
                "folder": {"present": False, "approved": "unset", "path": ""}}

    def _fake_enable(mode="auto"):
        state["on"] = True
        return True, "已启用：登录 Windows 后自动启动（注册表启动项）"

    def _fake_disable(clean_task=True):
        state["on"] = False
        return True, "已关闭开机启动"

    saved_fns = (startup_mod.status, startup_mod.enable, startup_mod.disable)
    startup_mod.status = _fake_status
    startup_mod.enable = _fake_enable
    startup_mod.disable = _fake_disable
    try:
        win.autostart_cb.select()
        win._toggle_autostart()
        deadline = time.time() + 3
        while time.time() < deadline and win._autostart_busy:
            root.update()
            time.sleep(0.02)
        check(state["on"] and "已启用" in win.autostart_status.cget("text"),
              "开启后写入启动项：%s" % win.autostart_status.cget("text"))
        win.autostart_cb.deselect()
        win._toggle_autostart()
        deadline = time.time() + 3
        while time.time() < deadline and win._autostart_busy:
            root.update()
            time.sleep(0.02)
        check(not state["on"] and "已关闭" in win.autostart_status.cget("text"),
              "关闭后移除启动项：%s" % win.autostart_status.cget("text"))
    finally:
        (startup_mod.status, startup_mod.enable,
         startup_mod.disable) = saved_fns
    win.destroy()


def test_result(root):
    print("[结果窗口]")
    calls = []
    w = ResultWindow(root, on_verify=lambda x: calls.append("verify"),
                     on_retry=lambda x: calls.append("retry"),
                     on_close=lambda: calls.append("close"),
                     on_table=lambda x: calls.append("table"),
                     on_export=lambda x, f: calls.append("export:" + f),
                     on_translate=lambda x: calls.append("translate"),
                     on_pin=lambda x: calls.append("pin"),
                     on_beautify=lambda x: calls.append("beautify"))
    root.update()
    w.show_result({"ok": True, "model": "glm-ocr:latest", "elapsed_ms": 300,
                   "text": TABLE_MD})
    root.update()
    check(w._content().startswith("| 序号"), "文本内容已载入")
    check("glm-ocr" in w.pill.cget("text"), "状态胶囊显示模型与耗时：%s"
          % w.pill.cget("text"))

    for label, want in (("导出 Word .docx", "export:docx"),
                        ("导出 TXT", "export:txt"),
                        ("导出 XLSX", "export:xlsx"),
                        ("导出 Markdown .md", "export:md"),
                        ("导出 美化分享图 PNG", "beautify")):
        w._on_export_pick(label)
        check(calls[-1] == want, "%s -> %s" % (label, want))
    check(w.export_menu.get() == "导出", "导出菜单复位为占位文案")

    w.copy_all()
    check(w._content() in w.clipboard_get(), "复制全部写入剪贴板")

    w._switch_view("表格")
    root.update()
    rows = w.tree.get_children()
    check(len(rows) == 2, "表格视图解析出 2 行（实际 %d）" % len(rows))
    check(w._rows is not None, "解析结果缓存在 _rows（表格视图复用）")

    w._verify(); w._retry(); w._translate(); w._pin()
    w._on_export_pick("导出 美化分享图 PNG")   # 美化走 on_beautify，无独立方法
    for name in ("verify", "retry", "translate", "pin", "beautify"):
        check(name in calls, "按钮 %s 回调已触发" % name)

    # 表格重识别仍解析不出表格时，不能再次自动发起识别（旧实现会无限重识别）
    calls.clear()
    w.show_result({"ok": True, "model": "glm-ocr:latest", "elapsed_ms": 10,
                   "text": "纯文本，没有表格结构"}, prefer_table=True)
    root.update()
    check(calls.count("table") == 0, "表格解析失败后不再自动重复识别")
    check(w.seg.get() == "文本", "解析失败自动回到文本视图（%s）" % w.seg.get())

    w._close()
    check("close" in calls, "关闭回调已触发")


def test_history(root):
    print("[历史窗口]")
    base = tempfile.mkdtemp(prefix="smoke_hist_")
    thumb = Image.new("RGB", (300, 200), (240, 238, 250))
    tmp = os.path.join(base, "t.png")
    thumb.save(tmp)
    with open(tmp, "rb") as f:
        thumb_bytes = f.read()
    hist = History(base_dir=base, keep=100)
    for i in range(3):
        hist.add(source="hotkey", mode="text", model="glm-ocr:latest",
                 elapsed_ms=300 + i, text="冒烟记录 %d 内容" % i,
                 thumb_png=thumb_bytes)
    win = HistoryWindow(root, hist)
    root.update()
    check(len(win.tree.get_children()) == 3, "历史列表载入 3 条")
    win.tree.selection_set("1")
    win._on_select()
    root.update()
    check("冒烟记录" in win.detail.get("1.0", "end-1c"), "详情显示所选记录")
    check(win.thumb.cget("image") != "", "缩略图已加载为 CTkImage")
    win.search_entry.delete(0, "end")
    win.search_entry.insert(0, "2")
    win.reload()
    check(len(win.tree.get_children()) == 1, "搜索过滤生效")
    rows = win.tree.get_children()
    if rows:
        win.tree.selection_set(rows[0])
    win._delete()
    check(len(hist.search()) == 2, "删除记录生效")
    win.destroy()
    hist.close()


def test_hotkey_dialog(root):
    print("[快捷键对话框]")
    got = []
    dlg = HotkeyDialog(root, "ctrl+alt+o", got.append)
    root.update()
    check(dlg.display.get() == "ctrl+alt+o", "初始显示当前快捷键")
    dlg._on_key(types.SimpleNamespace(keysym="F9"))
    check(dlg.spec == "f9", "单独按 F9 被接受（无修饰键也行）")
    dlg.spec = "ctrl+alt+f9"
    dlg._save()
    check(got == ["ctrl+alt+f9"], "保存回调收到新组合键")


def test_toast(root):
    print("[Toast]")
    toast = Toast(root, 4000)
    toast.show("星剪已启动 · 截图识别已就绪")
    root.update()
    win = toast._win
    check(win is not None, "Toast 窗口已创建")
    canvas = win.winfo_children()[0]
    label = [i for i in canvas.find_all() if canvas.type(i) == "text"][0]
    lx0, ly0, lx1, ly1 = canvas.bbox(label)
    cw, ch = canvas.winfo_width(), canvas.winfo_height()
    check(cw > 40 and ch > 20, "Toast 画布尺寸合理（%dx%d）" % (cw, ch))
    check(0 < lx0 and lx1 < cw, "文字水平居中未被裁切（%d..%d / %d）"
          % (lx0, lx1, cw))
    check(0 < ly0 and ly1 < ch, "文字垂直居中未被裁切（%d..%d / %d）"
          % (ly0, ly1, ch))
    toast._destroy()
    check(toast._win is None, "Toast 可关闭")


def test_overlay(root):
    print("[取景遮罩]")
    # 合成截屏（避免读取真实桌面）
    w, h = 320, 200
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            buf.extend((x % 256, y % 256, 128, 255))
    img = capture.Image(w, h, bytes(buf), (0, 0))
    got = {}
    ov = SelectionOverlay(root, (0, 0, w, h),
                          on_select=lambda b: got.update(b=b),
                          on_cancel=lambda: got.update(cancel=1),
                          image=img)
    root.update()
    check(ov._bg_photo is not None, "截屏成功铺底（Pillow 转换可用）")
    ov._on_press(types.SimpleNamespace(x=20, y=30))
    ov._on_move(types.SimpleNamespace(x=160, y=140))
    root.update()
    check(ov._size_tx and ov.canvas.itemcget(ov._size_tx, "text") ==
          "140 × 110", "尺寸标签文字: %s" % ov.canvas.itemcget(ov._size_tx, "text"))
    # 选区外应被 4 块压暗覆盖（上/下/左/右）
    boxes = [ov.canvas.coords(r) for r in ov._dims]
    check(boxes[0] == [0, 0, w, 30], "上方压暗块坐标 %s" % (boxes[0],))
    check(boxes[1] == [0, 140, w, h], "下方压暗块坐标 %s" % (boxes[1],))
    ov._on_release(types.SimpleNamespace(x=160, y=140))
    check(got.get("b") == (20, 30, 140, 110), "选区 bbox: %s" % (got.get("b"),))

    ov2 = SelectionOverlay(root, (0, 0, w, h),
                           on_select=lambda b: None,
                           on_cancel=lambda: got.update(cancel=1))
    root.update()
    check(ov2._bg_photo is None, "无截屏时退回纯色底")
    ov2._on_press(types.SimpleNamespace(x=5, y=5))
    ov2._on_release(types.SimpleNamespace(x=6, y=6))
    check(got.get("cancel") == 1, "过小拖动视为取消")


def test_overlay_confirm(root):
    print("[仅截图的 ✓/✕ 确认]")
    w, h = 400, 260
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            buf.extend((x % 256, y % 256, 90, 255))
    img = capture.Image(w, h, bytes(buf), (0, 0))
    got = {}
    ov = SelectionOverlay(root, (0, 0, w, h),
                          on_select=lambda b: got.update(b=b),
                          on_cancel=lambda: got.update(cancel=1),
                          image=img, confirm=True)
    root.update()
    ov._on_press(types.SimpleNamespace(x=40, y=50))
    ov._on_release(types.SimpleNamespace(x=300, y=200))
    root.update()
    check(ov._pending_bbox == (40, 50, 260, 150),
          "拖完停留，待确认 bbox=%s" % (ov._pending_bbox,))
    check(len(ov._toolbar) >= 5, "出现 ✓/✕ 工具条（%d 个元素）"
          % len(ov._toolbar))
    check(got.get("b") is None, "确认前不回调（用户可先核对）")

    # 布局回归：提示文字必须完全在面板内；两个按钮不能挤在一起
    panel = ov.canvas.bbox(ov._toolbar[0])
    hint = ov.canvas.bbox(ov._toolbar[-1])
    check(hint[0] >= panel[0] and hint[2] <= panel[2] - 2,
          "提示文字在面板内（hint=%s panel=%s）" % (hint, panel))
    ok_btn = ov.canvas.bbox(ov._toolbar[1])
    no_btn = ov.canvas.bbox(ov._toolbar[3])
    check(no_btn[0] - ok_btn[2] >= 8,
          "保存/取消按钮间距 ≥ 8px（实际 %d）" % (no_btn[0] - ok_btn[2]))

    # 点 ✓ 才真正交付
    ov._accept()
    root.update()
    check(got.get("b") == (40, 50, 260, 150), "点 ✓ 后交付选区")

    # 再来一次，点 ✕ 应取消
    got.clear()
    ov3 = SelectionOverlay(root, (0, 0, w, h),
                           on_select=lambda b: got.update(b=b),
                           on_cancel=lambda: got.update(cancel=1),
                           image=img, confirm=True)
    root.update()
    ov3._on_press(types.SimpleNamespace(x=20, y=20))
    ov3._on_release(types.SimpleNamespace(x=200, y=160))
    root.update()
    ov3.cancel()
    root.update()
    check(got.get("cancel") == 1 and got.get("b") is None, "点 ✕ 取消且不交付")

    # 回车确认
    got.clear()
    ov4 = SelectionOverlay(root, (0, 0, w, h),
                           on_select=lambda b: got.update(b=b),
                           on_cancel=lambda: got.update(cancel=1),
                           image=img, confirm=True)
    root.update()
    ov4._on_press(types.SimpleNamespace(x=30, y=30))
    ov4._on_release(types.SimpleNamespace(x=230, y=180))
    ov4._confirm_current()
    root.update()
    check(got.get("b") == (30, 30, 200, 150), "Enter 也能确认")


def test_pin_and_beautify(root):
    print("[贴图 / 美化]")
    pil = Image.new("RGB", (240, 160), (90, 120, 200))
    pin = PinWindow(root, pil, screen_pos=(40, 40))
    root.update()
    check(pin._cur_w() == 240 and pin._cur_h() == 160, "贴图按原始尺寸显示")
    pin._zoom(types.SimpleNamespace(delta=120))
    check(pin._cur_w() > 240, "滚轮放大生效（%d）" % pin._cur_w())
    pin._reset()
    check(pin._cur_w() == 240, "恢复原始大小")
    pin.close()

    out = beautify.render(pil, {"beautify_bg": "gradient",
                                "beautify_pad_ratio": 0.1})
    pad = max(28, int(min(240, 160) * 0.1))
    check(out.size == (240 + pad * 2, 160 + pad * 2),
          "美化图尺寸含留白 %s" % (out.size,))
    check(len(beautify.png_bytes(out)) > 1000, "美化图可编码为 PNG")


def test_capture_only(root):
    print("[仅截图不识别]")
    from starsnip.app import App

    cfg = config.load()
    cfg["auto_ocr"] = True
    app = App(root, cfg)
    calls = []
    app._run_ocr = lambda *a, **k: calls.append("ocr")   # 桩
    app.image = capture.capture_screen()
    app._ocr_after_capture = False       # 托盘「仅截图（不识别）」走这条
    app.busy = True
    app._on_selection((60, 60, 200, 120))
    root.update()
    check(not calls, "仅截图模式下不调用 OCR")
    check(app.busy is False, "仅截图后 busy 已复位（还能继续截图）")

    # 第二次启动被单实例锁拦下后，广播消息要变成「已在运行」轻提示
    shown = []
    app.toast.show = lambda text, ms=None: shown.append(text)
    app._handle({"type": "activate"})
    check(shown and "已在运行" in shown[-1],
          "第二次启动提示：%s" % (shown[-1] if shown else "（无）"))


def main():
    capture.enable_dpi_awareness()
    theme.apply_theme("dark")
    root = ctk.CTk()
    root.withdraw()
    try:
        test_settings(root)
        test_result(root)
        test_history(root)
        test_hotkey_dialog(root)
        test_toast(root)
        test_overlay(root)
        test_overlay_confirm(root)
        test_pin_and_beautify(root)
        test_capture_only(root)
    finally:
        root.update_idletasks()
        root.destroy()

    if failures:
        print("\nFAILED %d 项：" % len(failures))
        for f in failures:
            print("  -", f)
        return 1
    print("\ntest_ui_smoke OK（全部界面已渲染且回调连通）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
