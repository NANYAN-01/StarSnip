"""Hotkey dialog helpers: spec building + config persistence + UI smoke."""

import json
import os
import sys
import tempfile
import tkinter as tk

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import config
from starsnip.hotkey_ui import HotkeyDialog, build_spec


def main():
    # pure helpers
    assert build_spec("control_l") is None
    assert build_spec("unknown_key") is None
    print("build_spec neutral keys -> None")

    # config persistence
    tmp = os.path.join(tempfile.mkdtemp(prefix="starsnip_cfg_"), "config.json")
    config.save_setting("hotkey", "ctrl+alt+f8", path=tmp)
    with open(tmp, encoding="utf-8") as f:
        data = json.load(f)
    assert data["hotkey"] == "ctrl+alt+f8"
    config.save_setting("default_model", "glm-ocr:latest", path=tmp)
    with open(tmp, encoding="utf-8") as f:
        data = json.load(f)
    assert data["hotkey"] == "ctrl+alt+f8" and data["default_model"]
    print("save_setting preserves other keys")

    root = tk.Tk()
    root.withdraw()
    saved = []
    dlg = HotkeyDialog(root, "ctrl+alt+o", on_save=saved.append)
    root.update()
    assert dlg.display.get() == "ctrl+alt+o"
    dlg.spec = "ctrl+alt+f9"
    dlg._save()
    assert saved == ["ctrl+alt+f9"], saved
    print("dialog save ->", saved)
    root.destroy()
    print("test_hotkey_settings OK")


if __name__ == "__main__":
    main()
