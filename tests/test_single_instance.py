"""单实例锁与「已在运行」通知消息测试（离线，不建窗口）。"""

import os
import subprocess
import sys
import time

import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
SRC = _os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from starsnip import single_instance  # noqa: E402

NAME = "Local\\StarSnip.Test.%d" % os.getpid()

HOLDER = (
    "import sys, time\n"
    "sys.path.insert(0, %r)\n"
    "from starsnip import single_instance\n"
    "print('ACQUIRED' if single_instance.acquire(%r) else 'BUSY', flush=True)\n"
    "time.sleep(4)\n" % (SRC, NAME)
)
SECOND = (
    "import sys\n"
    "sys.path.insert(0, %r)\n"
    "from starsnip import single_instance\n"
    "print('ACQUIRED' if single_instance.acquire(%r) else 'BUSY')\n"
    % (SRC, NAME)
)


def run_second():
    out = subprocess.run([sys.executable, "-c", SECOND],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def main():
    holder = subprocess.Popen([sys.executable, "-c", HOLDER],
                              stdout=subprocess.PIPE, text=True)
    try:
        first = holder.stdout.readline().strip()
        assert first == "ACQUIRED", first
        second = run_second()
        assert second == "BUSY", second
        print("holder owns mutex; second process ->", second)
    finally:
        holder.terminate()
        holder.wait(timeout=10)

    time.sleep(0.4)                     # 等进程句柄释放互斥体
    released = run_second()
    assert released == "ACQUIRED", released
    print("lock released after holder exits ->", released)

    # 广播消息由托盘 WndProc 处理（不启动托盘线程）
    from starsnip.tray import SystemTray
    hits = []
    tray = SystemTray(lambda: None, lambda: None, lambda: None, lambda: None,
                      on_activate=lambda: hits.append(1))
    rc = tray._wnd_proc(0, single_instance.ACTIVATE_MESSAGE, 0, 0)
    assert rc == 0 and hits == [1], (rc, hits)
    assert isinstance(single_instance.notify_running(), bool)
    print("activate message handled by tray wndproc")
    print("test_single_instance OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
