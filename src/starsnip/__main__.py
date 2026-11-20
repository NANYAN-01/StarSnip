"""星剪 StarSnip 命令行入口。"""

import argparse
import json
import sys
import time
import traceback
import urllib.request

import customtkinter as ctk

from . import __version__, capture, config, single_instance
from .app import App


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fatal(exc: BaseException) -> None:
    """GUI 启动失败兜底：写日志 + 弹窗。

    打包成窗口程序（console=False）后没有 stderr，异常会静默消失，
    表现就是「双击 exe 毫无反应」，所以这里必须留下可查的痕迹。
    """
    from .logger import Logger
    log = Logger()
    try:
        log.info("FATAL %s: %s" % (type(exc).__name__, exc))
        log.info("".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__)))
    except Exception:  # noqa: BLE001
        pass
    try:
        import tkinter.messagebox as mb
        mb.showerror("星剪 StarSnip 启动失败",
                     "%s: %s\n\n日志：%s" % (type(exc).__name__, exc, log.path))
    except Exception:  # noqa: BLE001
        pass


def _run_gui(cfg: dict, args) -> int:
    """GUI 模式：以 customtkinter 根窗口驱动（隐藏，由托盘/热键唤起）。

    DPI 感知必须在创建 Tk 根窗口之前声明：否则 Tk 会按「虚拟化」坐标工作
    （例如 150% 缩放时把 2560×1600 当成 1707×1067），全屏遮罩与 Toast 定位
    都会偏；截图坐标也会和鼠标坐标不一致。
    """
    capture.enable_dpi_awareness()
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    root.title("星剪 StarSnip")
    root.withdraw()
    app = App(root, cfg)

    if args.history:
        app.open_history()
        root.mainloop()
        return 0

    if args.settings:
        app.open_settings()
        root.mainloop()
        return 0

    if args.file:
        app.busy = True
        app.open_file(args.file)
        root.mainloop()
        return 0

    app.start()
    print("星剪 StarSnip 已启动：按 %s 截图识别，Esc 取消，托盘右键可设置。"
          % cfg["hotkey"])
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if app.hotkey:
            app.hotkey.stop()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="starsnip",
        description="星剪 StarSnip：截图 OCR 识别 / 翻译 / 贴图 / 美化导出")
    parser.add_argument("--file", help="直接识别一张图片并显示结果窗口")
    parser.add_argument("--capture-test", metavar="PNG",
                        help="截取整个虚拟屏幕保存为 PNG（验证截图链路）")
    parser.add_argument("--check", action="store_true",
                        help="检查 Ollama 服务连通性并列出模型")
    parser.add_argument("--models", action="store_true",
                        help="列出后端模型，并标出可作为 OCR 模型的那些")
    parser.add_argument("--history", action="store_true",
                        help="直接打开历史记录窗口")
    parser.add_argument("--settings", action="store_true",
                        help="直接打开设置窗口")
    parser.add_argument("--mcp", action="store_true",
                        help="以 MCP stdio 服务运行（需 mcp<2）")
    parser.add_argument("--tray-test", action="store_true",
                        help="测试托盘图标能否创建（结果写入日志）")
    parser.add_argument("--diagnose", action="store_true",
                        help="诊断托盘/热键/后端并写入日志")
    parser.add_argument("--model", help="覆盖默认模型")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.model:
        cfg["default_model"] = args.model

    if args.mcp:
        try:
            from .mcp_server import run as run_mcp
        except ImportError as exc:  # noqa: BLE001
            print('MCP 依赖缺失，请先执行: python -m pip install "mcp<2"\n%s' % exc)
            return 2
        run_mcp()
        return 0

    if args.tray_test:
        from . import theme
        from .logger import Logger
        from .tray import SystemTray
        log = Logger()
        tray = SystemTray(lambda: None, lambda: None, lambda: None,
                          lambda: None, tooltip="星剪 tray test",
                          log=log.info, icon_path=theme.icon_ico("starsnip.ico"))
        ok = tray.start()
        rect = tray.wait_rect(2.0)
        log.info("tray-test: started=%s rect=%s" % (ok, rect))
        print("tray-test: started=%s rect=%s\nlog: %s" % (ok, rect, log.path))
        tray.stop()
        return 0 if (ok and rect) else 3

    if args.diagnose:
        from .logger import Logger
        from .hotkey import HotkeyManager
        from .tray import SystemTray
        log = Logger()
        lines = ["diagnose @ %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
                 "config: %s" % config.CONFIG_PATH,
                 "log: %s" % log.path]
        try:
            ver = _http_json(cfg["ollama_url"] + "/api/version")
            lines.append("ollama: %s (%s)" % (ver.get("version"), cfg["ollama_url"]))
        except Exception as exc:  # noqa: BLE001
            lines.append("ollama: FAIL %s" % exc)
        tray = SystemTray(lambda: None, lambda: None, lambda: None,
                          lambda: None, tooltip="星剪 diagnose", log=log.info)
        tray_ok = tray.start()
        rect = tray.wait_rect(2.0)
        tray.stop()
        lines.append("tray: started=%s rect=%s" % (tray_ok, rect))
        hk = HotkeyManager("ctrl+alt+shift+F8", lambda: None)
        hk_ok = hk.start()
        hk.stop()
        lines.append("hotkey(register test): %s %s"
                     % (hk_ok, "" if hk_ok else hk.error))
        report = "\n".join(lines)
        log.info(report)
        print(report)
        return 0 if (tray_ok and hk_ok) else 3

    if args.models:
        from . import ocr_core
        url = cfg["ollama_url"]
        items = ocr_core.list_models_detail(url)
        if not items:
            print("无法从 %s 获取模型列表（后端不可用？）" % url)
            return 2
        ocr_names = ocr_core.list_ocr_models(url)
        print("后端 %s 共 %d 个模型；设置里只列 OCR 模型（%d 个）："
              % (url, len(items), len(ocr_names)))
        for item in items:
            caps = ",".join(item["capabilities"])
            ocr = "OCR" if item["name"] in ocr_names else "   "
            print("  [%s] %-44s %s" % (ocr, item["name"], caps))
        return 0

    if args.check:
        try:
            version = _http_json(cfg["ollama_url"] + "/api/version")
            tags = _http_json(cfg["ollama_url"] + "/api/tags")
        except Exception as exc:  # noqa: BLE001
            print("后端不可用：%s" % exc)
            return 2
        print("Ollama %s @ %s" % (version.get("version"), cfg["ollama_url"]))
        for item in tags.get("models", []):
            caps = ",".join(item.get("capabilities") or [])
            print("  %-46s %8.1fMB  %s" % (
                item.get("name"), item.get("size", 0) / 1e6, caps))
        print("默认模型：%s" % cfg["default_model"])
        return 0

    if args.capture_test:
        capture.enable_dpi_awareness()
        img = capture.capture_screen()
        capture.save_png(img, args.capture_test)
        print("saved %s (%dx%d) origin=%s" % (args.capture_test, img.width,
                                              img.height, img.origin))
        return 0

    # 常驻模式（无 --history/--settings/--file）只允许一个实例：
    # 已有实例就通知它弹个「已在运行」，自己退出，避免两个托盘/热键互抢。
    resident = not (args.history or args.settings or args.file)
    if resident and not single_instance.acquire():
        single_instance.notify_running()
        from .logger import Logger
        Logger().info("second instance: another one is running; notified it"
                      " and exited")
        return 0

    # GUI 模式：以 customtkinter 根窗口驱动（隐藏，由托盘/热键唤起）
    try:
        return _run_gui(cfg, args)
    except Exception as exc:  # noqa: BLE001
        _fatal(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
