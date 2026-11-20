"""Toast test: appears, then auto-dismisses."""

import sys
import tkinter as tk

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip.toast import Toast


def main():
    root = tk.Tk()
    root.withdraw()
    toast = Toast(root, ms=400)
    toast.show("已保存")
    root.update()
    win = toast._win
    assert win is not None and win.winfo_exists()
    print("toast shown:", win.geometry())

    def wait_gone():
        root.update()
        assert toast._win is None, "toast should auto-dismiss"
        print("toast auto-dismissed")
        root.destroy()
        print("test_toast OK")

    root.after(700, wait_gone)
    root.mainloop()


if __name__ == "__main__":
    main()
