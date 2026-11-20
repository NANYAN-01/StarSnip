# M1 计划与验证记录(ScreenOCR)

日期:2026-11-20 · 状态:**已完成**(托盘 / 历史 / 表格模式)

## 任务

| # | 任务 | 结果 |
|---|---|---|
| M1-A | 系统托盘(Shell_NotifyIcon + 右键菜单) | ✅ |
| M1-B | 历史记录(SQLite + 缩略图 + 搜索窗口) | ✅ |
| M1-C | 表格模式(双视图 + 专用提示词重识别 + TSV/Markdown 导出) | ✅ |
| M1-D | 集成 / 测试 / 文档 | ✅ |

## 实现要点

### 托盘(`tray.py`)
- 纯 ctypes 调 `Shell_NotifyIconW`,无 pystray/Pillow 依赖;
- 独立线程创建隐藏窗口 + 消息循环;`WM_TRAY` 处理左键单击(截图)与右键菜单;
- 菜单:截图识别 / 历史记录 / 打开配置文件 / 退出;
- 回调只做 `queue.put`,由 Tk 主线程消费。

### 历史(`history.py` + `history_ui.py`)
- SQLite 表:时间、来源(hotkey/file)、模式(text/table)、模型、耗时、文本、缩略图路径、meta;
- 缩略图存 `%APPDATA%\ScreenOCR\thumbs\`(或 `SCREENOCR_HOME`),删除记录时同步删文件;
- 保留条数可配(默认 500),插入后自动淘汰最旧;
- 历史窗口:关键词搜索(文本/模型)、Treeview 列表、详情预览 + 缩略图、复制/删除/清空全部、双击复制。

### 表格模式(`tablefmt.py` + `ui.py` + `app.py`)
- 解析器支持 Markdown 表格与"2+ 空格/制表符对齐"的文本;
- 结果窗口有 文本/表格 单选视图,表格视图用 Treeview(首行当表头);
- **关键发现**:glm-ocr 普通提示词输出是**单空格分隔**(`7995.00需预订`),无法可靠解析;因此点"表格"若解析失败,会自动用 `table_prompt` 重新识别一次(Markdown 表格),再渲染;
- 一键复制 TSV(粘贴到 Excel)/ Markdown;
- 表格识别结果以 `mode=table` 入库。

## 验证记录

| 测试 | 结果 |
|---|---|
| `test_tablefmt.py` | Markdown/对齐两种格式解析、TSV/MD 导出正确 |
| `test_history.py` | 增/查(关键词+模型)/删/清空/淘汰(keep=20)全通过,缩略图文件同步删除 |
| `test_history_ui.py` | 列表、详情、双击复制、搜索过滤正常 |
| `test_tray.py` | 托盘图标添加/移除无异常,回调未误触发 |
| `test_ocr_core.py` | 文本 0.6s 全对;表格提示词输出 7 行×7 列,合计 34615.50 在结果中 |
| `test_e2e.py` | 文件识别 → 文本视图 → 触发表格重识别 → Treeview 6 行 → 历史 2 条(text/table) |

全量套件:10/10 通过。

## 过程中修掉的问题

1. `ttk.PanedWindow.pack()` 不支持 `padding` → 改 `padx/pady`;
2. 托盘 `DefWindowProcW` 未声明 argtypes,LPARAM 溢出(64 位)→ 显式声明全套 Win32 原型(含 `CreateWindowExW.restype=HWND`,避免句柄截断);
3. `--file` 模式未启动事件轮询 → 增加 `_ensure_poll()`;
4. 表格模式初版只做文本解析,真实输出单空格不可解析 → 改为"专用提示词重识别"方案。

## 留待 M2+

- 托盘自定义图标(当前系统默认);
- 设置界面(现在改 `config.json`);
- 剪贴板监听、拖拽图片/PDF、反色/放大预处理;
- 打包 exe 与内网分发;
- 热键冲突检测(同实例二次启动提示)。
