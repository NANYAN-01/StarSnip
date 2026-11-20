"""M2 integration test: screenshot save + clipboard + toast side effects."""

import os
import sys
import tempfile
import tkinter as tk

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import config
from starsnip.app import App
from starsnip.capture import Image
from starsnip.clipboard_image import user32

IMG_DIR = tempfile.mkdtemp(prefix="starsnip_img_")
HIST_HOME = tempfile.mkdtemp(prefix="starsnip_hist_")
os.environ["STARSNIP_HOME"] = HIST_HOME


def main():
    cfg = config.load()
    cfg["image_dir"] = IMG_DIR
    cfg["toast_ms"] = 500
    root = tk.Tk()
    root.withdraw()
    app = App(root, cfg)
    shown = []
    original = app.toast.show
    app.toast.show = lambda text, ms=None: (shown.append(text), original(text, ms))

    img = Image(64, 48, bytes([255, 0, 0, 255]) * (64 * 48))
    app.crop_img = img
    app._save_side_effects()
    root.update()

    files = [f for f in os.listdir(IMG_DIR) if f.endswith(".png")]
    assert files, "screenshot png not saved"
    assert os.path.getsize(os.path.join(IMG_DIR, files[0])) > 0
    print("saved:", files[0])

    assert user32.IsClipboardFormatAvailable(8), "image not on clipboard"
    print("clipboard has CF_DIB")

    assert "已保存" in shown, shown
    assert app.toast._win is not None
    print("toast shown:", shown)

    root.destroy()
    print("test_m2_integration OK")


if __name__ == "__main__":
    main()
