"""静态自检：找出类中 self.xxx 被引用但既未定义、也未赋值的成员。

用法： .venv\\Scripts\\python tools\\_check_undefined.py
比只查 self.xxx() 调用更严格：以回调形式传参（如 on_export=self._export_file）
同样会被抓出来。父类/框架动态属性会有误报，输出需人工确认。
"""

import ast
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src", "starsnip")

# 基类（tkinter / customtkinter）提供的属性，无需在类内定义
WHITELIST = {
    "master", "tk", "_w", "_root", "children", "_last_child_ids", "after",
    "after_cancel", "after_idle", "destroy", "configure", "config", "pack",
    "pack_forget", "grid", "grid_forget", "grid_remove", "place", "place_forget",
    "wm", "wait_window", "wait_visibility", "grab_set", "grab_release",
    "transient", "update", "update_idletasks", "clipboard_clear",
    "clipboard_append", "clipboard_get", "title", "geometry", "resizable",
    "minsize", "maxsize", "report_callback_exception", "mainloop",
    "focus_force", "focus_set", "lift", "lower", "iconbitmap", "iconphoto",
    "attributes", "overrideredirect", "winfo_x", "winfo_y", "winfo_width",
    "winfo_height", "winfo_screenwidth", "winfo_screenheight", "winfo_exists",
    "winfo_rootx", "winfo_rooty", "winfo_children", "winfo_reqwidth",
    "bind", "bind_all", "unbind", "protocol", "state", "deiconify",
    "withdraw", "bell", "quit", "event_generate", "winfo_toplevel",
    "class_get", "cget", "set", "get",
}


def _is_self(node):
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
        and node.value.id == "self"


def _assigned_names(target, out):
    """收集赋值目标里的 self.xxx（含 `self.a, self.b = ...` 元组拆包）。"""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
            and target.value.id == "self":
        out.add(target.attr)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _assigned_names(elt, out)
    elif isinstance(target, ast.Starred):
        _assigned_names(target.value, out)


def check(path):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        defined = set()
        for item in ast.walk(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(item.name)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    _assigned_names(t, defined)
            elif isinstance(item, (ast.AnnAssign, ast.AugAssign)):
                _assigned_names(item.target, defined)
            elif isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
                defined.add(item.id)
        used = set()
        for item in ast.walk(node):
            if _is_self(item) and isinstance(item.ctx, ast.Load):
                used.add(item.attr)
        missing = sorted(a for a in used if a not in defined and a not in WHITELIST)
        if missing:
            problems.append((node.name, missing))
    return problems


def main():
    total = 0
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(ROOT, name)
        for cls, missing in check(path):
            total += len(missing)
            print("%s :: %s -> %s" % (name, cls, ", ".join(missing)))
    print("\n可能未定义的 self 成员引用：%d 处" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
