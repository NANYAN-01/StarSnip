"""Selection overlay logic test: synthetic drag -> expected screen bbox."""

import sys
import types
import tkinter as tk

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip.overlay import SelectionOverlay


def main():
    root = tk.Tk()
    root.withdraw()
    got = {"bbox": None, "cancelled": 0}
    overlay = SelectionOverlay(
        root, (0, 0, 800, 600),
        on_select=lambda bbox: got.update(bbox=bbox),
        on_cancel=lambda: got.update(cancelled=got["cancelled"] + 1))

    def ev(x, y):
        return types.SimpleNamespace(x=x, y=y)

    overlay._on_press(ev(100, 80))
    overlay._on_move(ev(220, 160))
    overlay._on_release(ev(300, 200))
    root.update()
    print("selected bbox:", got["bbox"])
    assert got["bbox"] == (100, 80, 200, 120), got["bbox"]

    # tiny drag = treat as misclick -> cancel
    overlay2 = SelectionOverlay(
        root, (0, 0, 800, 600),
        on_select=lambda bbox: got.update(bbox=bbox),
        on_cancel=lambda: got.update(cancelled=got["cancelled"] + 1))
    overlay2._on_press(ev(10, 10))
    overlay2._on_release(ev(12, 12))
    root.update()
    print("cancelled:", got["cancelled"])
    assert got["cancelled"] == 1
    print("test_overlay OK")
    root.destroy()


if __name__ == "__main__":
    main()
