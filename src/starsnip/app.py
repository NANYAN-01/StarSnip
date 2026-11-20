"""星剪 StarSnip 应用装配：热键/托盘 → 截图 → 选区 → OCR → UI → 翻译/贴图/美化/导出。

相对旧版的主要变化：
- 界面全面切换到 customtkinter（设计系统见 theme.py）；
- 新增：一键翻译（Ollama 通用模型）、贴图钉屏、美化分享图 PNG；
- 设置窗口取代「只能改配置文件」，常用配置可在 UI 中修改。
"""

import os
import queue
import threading
import traceback

import customtkinter as ctk
from tkinter import messagebox

from . import (ai_writer, beautify, capture, clipboard_image, config, imgconv,
               ocr_core, screenfiles, theme)
from .history import History
from .history_ui import HistoryWindow
from .hotkey import HotkeyManager
from .hotkey_ui import HotkeyDialog
from .logger import Logger
from .overlay import SelectionOverlay
from .pin import PinWindow
from .settings_ui import SettingsWindow
from .toast import Toast
from .tray import SystemTray
from .ui import ResultWindow, VerifyWindow

APP_LABEL = "星剪 StarSnip"


class App:
    def __init__(self, root: ctk.CTk, cfg: dict):
        self.root = root
        self.cfg = cfg
        self.events = queue.Queue()
        self.busy = False
        self.image = None
        self.crop_img = None
        self.png = None
        self.thumb_png = None
        self.result = None
        self.window = None
        self.history_window = None
        self.settings_window = None
        self.hotkey = None
        self.tray = None
        self.hotkey_dialog = None
        self._pins = []
        self._pin_seq = 0
        self.last_source = "hotkey"
        self._polling = False
        self.history = (History(keep=int(cfg.get("history_keep", 500)))
                        if cfg.get("history_enabled", True) else None)
        self.toast = Toast(root, int(cfg.get("toast_ms", 2000)))
        self.last_export = None
        self.log = Logger()
        self.log.info("App created (config=%s, hotkey=%s, model=%s, theme=%s)"
                      % (config.CONFIG_PATH, cfg.get("hotkey"),
                         cfg.get("default_model"), cfg.get("theme")))
        self.root.report_callback_exception = self._on_tk_error
        theme.apply_theme(cfg.get("theme", "system"))
        self._set_window_icon()

    # ---------- 生命周期 ----------
    def _set_window_icon(self):
        ico = theme.icon_ico("starsnip.ico")
        if ico:
            try:
                self.root.iconbitmap(default=ico)
                return
            except Exception:  # noqa: BLE001
                pass
        png = theme.icon_png("starsnip.png")
        if os.path.isfile(png):
            try:
                from PIL import Image, ImageTk
                # 必须持有引用，否则被 GC 后窗口图标会丢
                self._icon_photo = ImageTk.PhotoImage(
                    Image.open(png).convert("RGBA"))
                self.root.iconphoto(True, self._icon_photo)
            except Exception:  # noqa: BLE001
                pass

    def _on_tk_error(self, exc_type, exc_value, tb) -> None:
        """Tk 回调异常统一兜底：写日志 + 轻提示，避免界面静默失效。

        由 __init__ 注册到 root.report_callback_exception；不注册的话
        tkinter 只把异常打到 stderr，而打包后的窗口模式没有 stderr。
        """
        try:
            self.log.info("TK-ERROR %s: %s"
                          % (getattr(exc_type, "__name__", exc_type), exc_value))
            self.log.info("".join(
                traceback.format_exception(exc_type, exc_value, tb)))
        except Exception:  # noqa: BLE001
            pass
        try:
            self.toast.show("出错了：%s" % exc_value)
        except Exception:  # noqa: BLE001
            pass

    def start(self) -> None:
        capture.enable_dpi_awareness()
        self._start_hotkey()
        self._start_tray()
        self._ensure_poll()
        if self.cfg.get("tray_toast", True):
            self.root.after(900, lambda: self.toast.show(
                "%s · %s 截图识别 · %s 仅截图" % (
                    APP_LABEL, self.cfg.get("hotkey"),
                    self.cfg.get("hotkey_capture_only", "")),
                int(self.cfg.get("toast_ms", 2000))))

    def _ensure_poll(self) -> None:
        if not self._polling:
            self._polling = True
            self.root.after(60, self._poll)

    def _start_hotkey(self) -> None:
        """注册两个全局热键：识别（hotkey）与仅截图（hotkey_capture_only）。"""
        self.hotkey = None
        self.hotkey_only = None
        try:
            self.hotkey = HotkeyManager(
                self.cfg["hotkey"], lambda: self.events.put({"type": "hotkey"}))
            ok = self.hotkey.start()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("热键解析失败",
                                 "%s\n\n请检查 config.json 的 hotkey 字段" % exc)
            return
        if not ok:
            messagebox.showwarning(
                "热键注册失败",
                "无法注册 %s（可能被其他程序占用）。\n"
                "可在设置中修改快捷键后重启。" % self.cfg["hotkey"])
        # 第二个热键（仅截图）失败不打扰用户，只记日志
        only_spec = self.cfg.get("hotkey_capture_only") or ""
        if only_spec:
            try:
                self.hotkey_only = HotkeyManager(
                    only_spec,
                    lambda: self.events.put({"type": "capture_only"}))
                if self.hotkey_only.start():
                    self.log.info("capture-only hotkey: %s" % only_spec)
                else:
                    self.log.info("capture-only hotkey failed: %s (%s)"
                                  % (only_spec, self.hotkey_only.error))
            except Exception as exc:  # noqa: BLE001
                self.log.info("capture-only hotkey parse error: %s" % exc)

    def _start_tray(self) -> None:
        self.tray = SystemTray(
            on_capture=lambda: self.events.put({"type": "hotkey"}),
            on_history=lambda: self.events.put({"type": "history"}),
            on_config=lambda: self.events.put({"type": "config"}),
            on_exit=lambda: self.events.put({"type": "exit"}),
            tooltip="%s · %s 识别 · %s 仅截图" % (
                APP_LABEL, self.cfg["hotkey"],
                self.cfg.get("hotkey_capture_only", "")),
            log=self.log.info,
            on_log=lambda: self.events.put({"type": "log"}),
            on_settings=lambda: self.events.put({"type": "settings"}),
            icon_path=theme.icon_ico("starsnip.ico"),
            on_capture_only=lambda: self.events.put({"type": "capture_only"}),
            on_activate=lambda: self.events.put({"type": "activate"}))
        if not self.tray.start():
            self.log.info("tray start failed: %s" % self.tray.error)
            messagebox.showwarning("托盘初始化失败",
                                   "系统托盘不可用：%s\n详见日志：%s"
                                   % (self.tray.error, self.log.path))
            return
        rect = self.tray.wait_rect(1.5)
        self.log.info("tray started, rect=%s" % (rect,))
        if rect is None:
            self.root.after(400, lambda: self.toast.show(
                "托盘图标已在通知区域；若看不到请点时钟旁的 ^ 展开"))

    def shutdown(self) -> None:
        for hk in (self.hotkey, getattr(self, "hotkey_only", None)):
            if hk:
                hk.stop()
        if self.tray:
            self.tray.stop()
        if self.history:
            self.history.close()
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ---------- 事件循环 ----------
    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _handle(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "hotkey":
            self._trigger_capture()
        elif kind == "capture_only":
            self._trigger_capture(ocr=False)
        elif kind == "history":
            self.open_history()
        elif kind == "settings":
            self.open_settings()
        elif kind == "config":
            self._open_config()
        elif kind == "log":
            self._open_log()
        elif kind == "activate":
            # 第二次启动被单实例锁拦下，广播消息到这里：告诉用户已在运行
            self.log.info("second launch detected: already running")
            self.toast.show("星剪已在运行 · %s 截图识别"
                            % self.cfg.get("hotkey", ""),
                            int(self.cfg.get("toast_ms", 2000)))
        elif kind == "exit":
            self.shutdown()
        elif kind == "ocr_done":
            self.busy = False
            result = event["result"]
            self.log.info("ocr: model=%s %dms" % (
                result.get("model"), result.get("elapsed_ms", 0)))
            self._show_result(result)
        elif kind == "table_done":
            self.busy = False
            self._show_table_result(event["result"])
        elif kind == "verify_done":
            self._show_verify(event["results"])
        elif kind == "export_done":
            self.busy = False
            self.last_export = event["path"]
            self.log.info("export %s: %s" % (event.get("fmt", ""),
                                             event["path"]))
            if self.window:
                self.window.status_note("已导出：%s"
                                        % os.path.basename(event["path"]))
            self.toast.show("已导出：%s" % os.path.basename(event["path"]))
        elif kind == "export_error":
            self.busy = False
            if self.window:
                self.window.status_note("导出失败")
            self.toast.show("导出失败")
            messagebox.showerror("导出失败", event.get("message", ""))
        elif kind == "translate_done":
            self.busy = False
            self._apply_translate(event["text"], event["target"])
        elif kind == "error":
            self.busy = False
            msg = event.get("message", "未知错误")
            self.log.info("ERROR %s" % msg.replace("\n", " | "))
            # 截图已经保存/进剪贴板；识别失败不再弹模态框打断操作
            short = msg.splitlines()[0][:60] if msg else "未知错误"
            self.toast.show("识别失败：%s（图片已保留）" % short,
                            int(self.cfg.get("toast_ms", 2000)) + 1500)
            if self.window is not None and self.window.winfo_exists():
                self.window.status_note("识别失败：%s" % short)

    # ---------- 快捷键 / 配置 / 设置 ----------
    def _apply_hotkey(self, spec: str, which: str = "ocr") -> None:
        """which="ocr" 改识别热键；which="capture" 改仅截图热键。"""
        key = "hotkey" if which == "ocr" else "hotkey_capture_only"
        old = self.cfg.get(key)
        event = "hotkey" if which == "ocr" else "capture_only"
        try:
            new_manager = HotkeyManager(
                spec, lambda: self.events.put({"type": event}))
            ok = new_manager.start()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("快捷键无效", str(exc))
            return
        if not ok:
            messagebox.showerror(
                "快捷键注册失败",
                "%s 可能被其他程序占用，请换一个组合。\n%s"
                % (spec, new_manager.error or ""))
            return
        if which == "ocr":
            if self.hotkey:
                self.hotkey.stop()
            self.hotkey = new_manager
        else:
            if getattr(self, "hotkey_only", None):
                self.hotkey_only.stop()
            self.hotkey_only = new_manager
        self.cfg[key] = spec
        config.save_setting(key, spec)
        if self.tray:
            self.tray.update_tooltip("%s · %s 识别 · %s 仅截图" % (
                APP_LABEL, self.cfg.get("hotkey"),
                self.cfg.get("hotkey_capture_only", "")))
        self.log.info("hotkey changed: %s -> %s (%s)" % (old, spec, which))
        self.toast.show("快捷键已更新：%s" % spec.upper())

    def _open_config(self) -> None:
        try:
            os.startfile(config.CONFIG_PATH)
        except OSError as exc:
            messagebox.showerror("打开配置", str(exc))

    def _open_log(self) -> None:
        try:
            if not os.path.isfile(self.log.path):
                self.log.info("log opened from tray")
            os.startfile(self.log.path)
        except OSError as exc:
            messagebox.showerror("打开日志", str(exc))

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(
            self.root, self.cfg, self._apply_settings,
            self._hotkey_from_settings, on_theme=self._apply_theme_live,
            on_hotkey_only=self._hotkey_only_from_settings)

    def _apply_theme_live(self, value: str) -> None:
        """设置窗口里点主题分段按钮时立即落盘（不需要再点保存）。"""
        self.cfg["theme"] = value
        try:
            config.save_setting("theme", value)
        except OSError as exc:
            self.log.info("save theme failed: %s" % exc)

    def _hotkey_from_settings(self, var):
        self._open_hotkey_dialog(var, "ocr")

    def _hotkey_only_from_settings(self, var):
        self._open_hotkey_dialog(var, "capture")

    def _open_hotkey_dialog(self, var, which: str = "ocr") -> None:
        """两个快捷键共用同一个录入对话框，已开着就抬起来，避免叠出多个。"""
        if self.hotkey_dialog is not None and self.hotkey_dialog.winfo_exists():
            self.hotkey_dialog.lift()
            return

        def apply_(spec):
            self._apply_hotkey(spec, which)
            var.set(spec)

        self.hotkey_dialog = HotkeyDialog(self.root, var.get(), apply_)

    def _apply_settings(self, values: dict) -> None:
        for k, v in values.items():
            self.cfg[k] = v
            try:
                config.save_setting(k, v)
            except OSError as exc:
                messagebox.showerror("保存设置", "%s: %s" % (k, exc))
                return
        if "theme" in values:
            theme.apply_theme(values.get("theme", "system"))
        if "history_enabled" in values:
            self._apply_history_enabled(bool(values["history_enabled"]))
        self.toast.show("设置已保存")

    def _apply_history_enabled(self, enabled: bool) -> None:
        """历史开关即时生效（否则关掉后要重启才不记账，用户会以为没保存）。"""
        if enabled and self.history is None:
            self.history = History(keep=int(self.cfg.get("history_keep", 500)))
            self.log.info("history enabled")
        elif not enabled and self.history is not None:
            if (self.history_window is not None
                    and self.history_window.winfo_exists()):
                self.history_window.destroy()
                self.history_window = None
            self.history.close()
            self.history = None
            self.log.info("history disabled")

    # ---------- 截图与 OCR ----------
    def _trigger_capture(self, ocr: bool = True) -> None:
        """开始截图取景。ocr=False 走「仅截图」（停留等 ✓/✕ 确认）。"""
        if self.busy:
            return
        self._ocr_after_capture = ocr
        self.busy = True
        try:
            self.image = capture.capture_screen()
        except Exception as exc:  # noqa: BLE001
            self.busy = False
            messagebox.showerror("截图失败", str(exc))
            return
        bbox = (self.image.origin[0], self.image.origin[1],
                self.image.width, self.image.height)
        self._bbox = bbox
        try:
            SelectionOverlay(self.root, bbox,
                             on_select=self._on_selection,
                             on_cancel=self._on_cancel,
                             image=self.image,
                             confirm=not ocr)   # 仅截图：停留等 ✓/✕ 确认
        except Exception as exc:  # noqa: BLE001 - 取景框起不来也要能再按热键
            self.busy = False
            self.log.info("overlay failed: %s: %s" % (type(exc).__name__, exc))
            messagebox.showerror(
                "取景框启动失败",
                "%s: %s\n\n详见日志：%s" % (type(exc).__name__, exc, self.log.path))

    def _on_cancel(self) -> None:
        self.busy = False

    def _on_selection(self, bbox) -> None:
        x, y, w, h = bbox
        self._sel_pos = (x, y)
        try:
            self.crop_img = self.image.crop(x - self.image.origin[0],
                                            y - self.image.origin[1], w, h)
            self.png = self.crop_img.to_png_scaled(int(self.cfg["max_side_px"]))
            self.thumb_png = self.crop_img.to_png_scaled(320)
        except Exception as exc:  # noqa: BLE001
            self.busy = False
            messagebox.showerror("图像处理失败", str(exc))
            return
        self._save_side_effects()
        self.last_source = "hotkey"
        self.log.info("capture: bbox=%s size=%s"
                      % (bbox, self.png and len(self.png)))
        if not getattr(self, "_ocr_after_capture", True):
            self.busy = False
            self.toast.show("已截图（未识别）")
            self.log.info("capture only: skip OCR")
            return
        self._run_ocr()

    def _save_side_effects(self) -> None:
        cfg = self.cfg
        img = self.crop_img
        if img is None:
            return
        if cfg.get("save_image", True):
            try:
                screenfiles.save_png(img, cfg.get("image_dir") or None)
                self.toast.show("已保存", int(cfg.get("toast_ms", 2000)))
            except Exception as exc:  # noqa: BLE001
                self.toast.show("保存失败：%s" % exc)
        if cfg.get("clipboard_image", True):
            try:
                clipboard_image.copy_image(img.bgra, img.width, img.height)
            except Exception:  # noqa: BLE001
                self.toast.show("图片未能写入剪贴板")

    def _run_ocr(self, prompt_override=None, event_type="ocr_done") -> None:
        png = self.png
        model = self.cfg.get("default_model") or ""
        url = self.cfg["ollama_url"]
        prompt = prompt_override or self.cfg.get("prompt", ocr_core.DEFAULT_PROMPT)
        timeout = float(self.cfg.get("timeout_s", 60))
        keep_alive = self.cfg.get("keep_alive", "30m")

        def work():
            try:
                result = ocr_core.call(png, model, url, prompt=prompt,
                                       timeout=timeout, keep_alive=keep_alive)
            except Exception as exc:  # noqa: BLE001
                self.events.put({"type": "error", "message": str(exc)})
                return
            if not result.get("ok"):
                self.events.put({"type": "error",
                                 "message": result.get("error") or "识别失败"})
                return
            self.events.put({"type": event_type, "result": result})

        threading.Thread(target=work, daemon=True).start()

    # ---------- 结果窗口 ----------
    def _show_result(self, result: dict) -> None:
        self.result = result
        if self.window is None or not self.window.winfo_exists():
            self.window = ResultWindow(
                self.root, on_verify=self._verify, on_retry=self._retry,
                on_close=self._window_closed, on_table=self._request_table,
                on_export=self._export_file, on_translate=self._translate,
                on_pin=self._pin, on_beautify=self._beautify)
        self.window.deiconify()
        self.window.lift()
        self.window.show_result(result)
        self._record_history(result, mode="text")

    def _show_table_result(self, result: dict) -> None:
        if not self.window or not result.get("ok"):
            return
        self.window.show_result(result, prefer_table=True)
        self._record_history(result, mode="table")

    def _request_table(self, _window) -> None:
        if not self.png or self.busy:
            return
        self.busy = True
        self._run_ocr(prompt_override=self.cfg.get("table_prompt",
                                                   ocr_core.TABLE_PROMPT),
                      event_type="table_done")

    def _record_history(self, result: dict, mode: str = "text") -> None:
        if not self.history or not result.get("ok"):
            return
        try:
            size = [self.crop_img.width, self.crop_img.height] if self.crop_img else None
            self.history.add(
                source=self.last_source, mode=mode, model=result["model"],
                elapsed_ms=result["elapsed_ms"], text=result["text"],
                thumb_png=self.thumb_png, meta={"size": size})
        except Exception:  # noqa: BLE001
            pass

    def _window_closed(self) -> None:
        self.window = None

    def _retry(self, _window) -> None:
        if not self.png or self.busy:
            return
        self.busy = True
        self._run_ocr()

    def _verify(self, _window) -> None:
        if not self.png or self.busy:
            return
        # 主模型用当前选中的 OCR 模型，再补一个不同的模型做对照；
        # 否则改过 OCR 模型后「校验」仍拿老模型跑，结果对不上。
        models = [self.cfg.get("default_model") or ""]
        for model in (self.cfg.get("verify_models") or []):
            if model and model not in models:
                models.append(model)
        models = [m for m in models if m][:2]
        if len(models) < 2:
            messagebox.showinfo(
                "交叉校验",
                "需要两个不同模型：请在 config.json 的 verify_models 里"
                "填一个与当前 OCR 模型不同的模型。")
            return
        self.busy = True
        png = self.png
        url = self.cfg["ollama_url"]
        prompt = self.cfg.get("prompt", ocr_core.DEFAULT_PROMPT)
        timeout = float(self.cfg.get("timeout_s", 60))

        def work():
            results = ocr_core.call_many(png, models, url, prompt=prompt,
                                         timeout=timeout)
            self.events.put({"type": "verify_done", "results": results})

        threading.Thread(target=work, daemon=True).start()

    def _show_verify(self, results: list) -> None:
        self.busy = False
        ok = [r for r in results if r.get("ok")]
        if not ok:
            messagebox.showerror("交叉校验失败",
                                 "\n".join(r.get("error") or "" for r in results))
            return
        primary = ok[0]
        others = [r["text"] for r in ok[1:]]
        diff = ocr_core.disagreements(primary["text"], others)
        VerifyWindow(self.root, ok, diff)

    # ---------- 翻译 ----------
    def _translate(self, _window) -> None:
        if not self.window:
            return
        if self.window._showing_translation:
            self._apply_translate(self.window._orig_text,
                                  "restore")
            return
        text = self.window._content()
        if not text.strip():
            messagebox.showinfo("翻译", "没有可翻译内容")
            return
        if self.busy:
            return
        self.busy = True
        model = (self.cfg.get("translate_model")
                 or self.cfg.get("layout_model")
                 or config.DEFAULTS["layout_model"])
        url = self.cfg["ollama_url"]
        timeout = float(self.cfg.get("layout_timeout", 120))
        keep_alive = self.cfg.get("keep_alive", "30m")
        self.window.status_note("翻译中…")

        def work():
            try:
                out, tgt = ai_writer.translate(text, model, url, "auto",
                                               timeout=timeout,
                                               keep_alive=keep_alive)
                self.events.put({"type": "translate_done",
                                 "text": out, "target": tgt})
            except Exception as exc:  # noqa: BLE001
                self.busy = False
                self.events.put({"type": "error",
                                 "message": "翻译失败：%s" % exc})

        threading.Thread(target=work, daemon=True).start()

    def _apply_translate(self, text: str, target: str) -> None:
        w = self.window
        if not w:
            return
        if target == "restore":
            w._showing_translation = False
            w.text.delete("1.0", "end")
            w.text.insert("1.0", w._orig_text)
            w.status_note("已还原原文")
            return
        w._trans_text = text
        w._showing_translation = True
        w.text.delete("1.0", "end")
        w.text.insert("1.0", text)
        w.status_note("译文 · %s" % ("中文" if target == "zh" else "English"))

    # ---------- 贴图钉屏 ----------
    def _pin(self, _window) -> None:
        if self.crop_img is None:
            self.toast.show("贴图仅在截图模式可用")
            return
        try:
            pil = imgconv.to_pil(self.crop_img)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("贴图失败", str(exc))
            return
        pos = getattr(self, "_sel_pos", None) or (120, 120)
        alpha = float(self.cfg.get("pin_alpha", 1.0))
        self._pin_seq += 1

        pin = PinWindow(self.root, pil, screen_pos=pos, alpha=alpha,
                        on_close=self._unpin)
        self._pins.append(pin)
        self.log.info("pin added #%d (%dx%d) at %s"
                      % (self._pin_seq, pil.width, pil.height, pos))

    def _unpin(self, pin) -> None:
        try:
            self._pins.remove(pin)
        except ValueError:
            pass

    # ---------- 美化导出 ----------
    def _beautify(self, _window) -> None:
        if self.crop_img is None:
            self.toast.show("美化分享图仅在截图模式可用")
            return
        try:
            pil = imgconv.to_pil(self.crop_img)
            rendered = beautify.render(pil, self.cfg)
            data = beautify.png_bytes(rendered)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("美化失败", str(exc))
            return
        try:
            path = screenfiles.save_bytes(
                data, self.cfg.get("export_dir") or None, "png",
                prefix="StarSnip_share")
            try:
                bgra, w, h = imgconv.to_bgra(rendered)
                clipboard_image.copy_image(bgra, w, h)
            except Exception:  # noqa: BLE001
                pass
            self.toast.show("已生成分享图：%s" % os.path.basename(path))
            self.last_export = path
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc))

    # ---------- 导出（AI 排版） ----------
    def _export_file(self, window, fmt: str) -> None:
        """AI 排版后导出 docx / xlsx / md / txt。

        LLM 只负责把 OCR 文本整理成规范 Markdown（ai_writer.llm_layout），
        二进制文件仍由本地 writers 生成；排版失败时 ai_writer 回退原文，
        导出不会中断。排版模型固定用 config 的 layout_model，界面不提供选择。
        """
        text = (window._content() if window is not None else "") or ""
        if not text.strip():
            messagebox.showinfo("导出", "没有可导出的内容")
            return
        if self.busy:
            return
        self.busy = True
        model = self.cfg.get("layout_model") or config.DEFAULTS["layout_model"]
        url = self.cfg["ollama_url"]
        timeout = float(self.cfg.get("layout_timeout", 120))
        keep_alive = self.cfg.get("keep_alive", "30m")
        directory = self.cfg.get("export_dir") or None
        if window is not None:
            window.status_note("AI 排版中…")

        def work():
            try:
                path, _md = ai_writer.export(
                    text, fmt, model, url, directory=directory,
                    timeout=timeout, keep_alive=keep_alive)
            except Exception as exc:  # noqa: BLE001
                self.events.put({"type": "export_error",
                                 "message": "%s: %s"
                                            % (type(exc).__name__, exc)})
                return
            self.events.put({"type": "export_done", "path": path, "fmt": fmt})

        threading.Thread(target=work, daemon=True).start()

    # ---------- 历史窗口 ----------
    def open_history(self) -> None:
        if not self.history:
            messagebox.showinfo("历史记录", "当前配置已禁用历史记录")
            return
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.lift()
            self.history_window.reload()
            return
        self.history_window = HistoryWindow(self.root, self.history)

    # ---------- 直接文件 OCR ----------
    def open_file(self, path: str) -> None:
        with open(path, "rb") as f:
            self.png = f.read()
        self.thumb_png = None
        self.crop_img = None
        self.last_source = "file"
        self.busy = True
        self._ensure_poll()
        self._run_ocr()
