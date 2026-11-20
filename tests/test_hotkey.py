"""Hotkey parsing and registration smoke test (does not press any key)."""

import sys
import time

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip.hotkey import MOD_ALT, MOD_CONTROL, HotkeyManager, parse_hotkey


def main():
    mods, vk = parse_hotkey("ctrl+alt+o")
    assert mods == (MOD_CONTROL | MOD_ALT), mods
    assert vk == ord("O"), vk
    print("parse ctrl+alt+o -> mods=%d vk=%d" % (mods, vk))

    # Try a few specs: the default combo may be held by a running StarSnip
    # instance, that is not a code defect.
    for spec in ("ctrl+alt+shift+F10", "ctrl+shift+F10", "ctrl+alt+shift+F9"):
        fired = []
        manager = HotkeyManager(spec, lambda: fired.append(1))
        ok = manager.start()
        print("register %-20s -> %s" % (spec, "OK" if ok else "FAILED (%s)" % manager.error))
        time.sleep(0.2)
        manager.stop()
        if ok:
            break
    else:
        raise AssertionError("could not register any test hotkey")
    print("fired=%d (expected 0: no key pressed)" % len(fired))
    print("test_hotkey OK")


if __name__ == "__main__":
    main()
