"""星剪 StarSnip 命令行入口。"""

import argparse
import json
import sys
import time
import urllib.request

import customtkinter as ctk

from . import __version__, capture, config
from .app import App


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="starsnip",
        description="星剪 StarSnip：截图 OCR 识别 / 翻译 / 贴图 / 美化导出")
    parser.add_argument("--file", help="直接识别一张图片并显示结果窗口")
    parser.add_argument("--capture-test", metavar="PNG",
                        help="截取整个虚拟屏幕保存为 PNG（验证截图链路）")
    parser.add_argument("--check", action="store_true",
                        help="检查 Ollama 服务连通性并列出模型")
    parser.add_argument("--history", action="store_true",
                        help="直接打开历史记录窗口")
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

    # GUI 模式：以 customtkinter 根窗口驱动（隐藏，由托盘/热键唤起）
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    root.title("星剪 StarSnip")
    root.withdraw()
    app = App(root, cfg)

    if args.history:
        app.open_history()
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


if __name__ == "__main__":
    sys.exit(main())
