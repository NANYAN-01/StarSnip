"""startup.py 离线单测：StartupApproved 解析 / 命令行 / 状态结构。

不在测试里真的写注册表：写入口令会改到跑测试的人自己的登录启动项。
真机验证用 tools/check_startup.py（手动跑，跑完自动还原）。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from starsnip import startup  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  x %s" % msg)
    else:
        print("  v %s" % msg)


def test_approved():
    print("[StartupApproved 解析]")
    check(startup.parse_approved(None) == "unset", "没有记录 = unset")
    check(startup.parse_approved(bytes([0x02] + [0] * 11)) == "enabled",
          "02 + 11 个 0 = 启用")
    check(startup.parse_approved(bytes([0x04] + [0] * 11)) == "enabled",
          "04 也算启用")
    check(startup.parse_approved(bytes([0x03] + [0] * 11)) == "disabled",
          "03 + FILETIME = 被禁用")


def test_command_line():
    print("[启动命令行]")
    line = startup.command_line()
    check(line.startswith('"') and line.endswith("--startup"),
          "带引号且以 --startup 结尾：%s" % line)
    exe, args, workdir = startup.launch_target()
    check(os.path.isabs(exe), "程序路径是绝对路径")
    check(os.path.isdir(workdir), "工作目录存在：%s" % workdir)


def test_describe():
    print("[状态文案]")
    off = {"enabled": False, "policy": [], "warnings": [], "mode": "none"}
    check("未启用" in startup.describe(off), "关着的时候说清楚")
    blocked = {"enabled": False, "policy": ["组策略已禁止当前用户的注册表启动项"],
               "warnings": [], "mode": "none"}
    check("组策略" in startup.describe(blocked), "被策略拦住时给出原因")
    on = {"enabled": True, "policy": [], "warnings": [], "mode": "run"}
    check("注册表启动项" in startup.describe(on), "启用时说明用的是哪种方式")
    warned = {"enabled": True, "policy": [], "mode": "run",
              "warnings": ["注册表启动项被 Windows 启动管理禁用了"]}
    check("禁用" in startup.describe(warned), "被系统禁用时提示修复")
    disabled = {"enabled": False, "policy": [], "mode": "none",
                "warnings": ["注册表启动项被 Windows 启动管理禁用了"]}
    check("修复" in startup.describe(disabled),
          "关着但被禁用时也要说清原因（不能只说未启用）")


def test_mode_labels():
    print("[启动方式]")
    check(len(startup.MODE_LABELS) == 4, "四种方式都有中文名")
    for key, label in startup.MODE_LABELS.items():
        check(startup.MODE_KEYS[label] == key, "标签可反查：%s" % label)


def test_status_shape():
    print("[状态结构]")
    st = startup.status()
    for key in ("run", "folder", "task", "policy", "warnings", "enabled",
                "effective", "mode", "command"):
        check(key in st, "status 含 %s" % key)
    check(st["mode"] in ("run", "folder", "task", "none"), "mode 取值合法")
    check(isinstance(st["warnings"], list), "warnings 是列表")


def main():
    test_approved()
    test_command_line()
    test_describe()
    test_mode_labels()
    test_status_shape()
    if failures:
        print("\nFAILED %d 项：" % len(failures))
        for item in failures:
            print("  -", item)
        return 1
    print("\ntest_startup OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
