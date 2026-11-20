"""开机启动（计划任务）离线测试：任务 XML / 动作命令 / 退出码链路，不触发 UAC。"""

import os
import sys
import xml.etree.ElementTree as ET

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import autostart  # noqa: E402

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def main():
    exe, args, workdir = autostart.action()
    assert os.path.isabs(exe) and os.path.isfile(exe), exe
    if not getattr(sys, "frozen", False):
        assert args == "-m starsnip", args
        assert workdir.endswith(os.sep + "src") and os.path.isdir(workdir), workdir
    print("action:", exe, "|", args, "|", workdir)

    # 打包版（sys.frozen）应直接指向 exe，无参数、工作目录为 exe 所在目录
    old_frozen = getattr(sys, "frozen", None)
    old_exe = sys.executable
    try:
        sys.frozen = True
        sys.executable = r"C:\Fake\StarSnip.exe"
        fexe, fargs, fdir = autostart.action()
        assert fexe == old_exe or fexe.endswith("StarSnip.exe"), fexe
        assert fargs == ""
        assert fdir == os.path.dirname(fexe)
        print("frozen action:", fexe, "|", fargs, "|", fdir)
    finally:
        if old_frozen is None:
            del sys.frozen
        else:
            sys.frozen = old_frozen
        sys.executable = old_exe

    xml = autostart.task_xml(exe, args, workdir)
    root = ET.fromstring(xml.encode("utf-16"))
    cmd = root.find(".//t:Exec/t:Command", NS)
    assert cmd is not None and cmd.text == exe, cmd
    arg = root.find(".//t:Exec/t:Arguments", NS)
    assert (arg.text if arg is not None else "") == args
    work = root.find(".//t:Exec/t:WorkingDirectory", NS)
    assert (work.text if work is not None else "") == workdir
    assert root.find(".//t:LogonTrigger", NS) is not None
    principal = root.find(".//t:Principal", NS)
    assert principal.find("t:LogonType", NS).text == "InteractiveToken"
    assert principal.find("t:RunLevel", NS).text == "LeastPrivilege"
    print("task xml OK")

    assert isinstance(autostart.is_enabled(), bool)
    print("is_enabled query OK:", autostart.is_enabled())

    # ShellExecuteEx 的等待/退出码链路（verb=None 不弹 UAC）
    code, err = autostart._shell_execute(None, "cmd.exe", "/c exit 7")
    assert (code, err) == (7, 0), (code, err)
    print("shell execute exit code OK:", code)

    # 任务不存在时 disable 直接成功（无需提权）；存在则跳过，避免动真实任务
    if not autostart.is_enabled():
        ok, msg = autostart.disable()
        assert ok, msg
        print("disable when absent:", msg)
    print("test_autostart OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
