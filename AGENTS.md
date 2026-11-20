# AGENTS.md

## 项目

Windows 截图 OCR 桌面工具「星剪 StarSnip」（由旧 ScreenOCR 全面改版）：
全局热键截图 → 取景框选 → OCR → 浮窗编辑 / 翻译 / 贴图 / 美化导出 / AI 排版导出。

- GUI：**customtkinter**（不再是纯 tkinter；含 Pillow）。识别/排版/翻译走后端 Ollama（默认 `http://127.0.0.1:11434`，可改为自己的主机）。仅 Windows。
- 「零第三方依赖」是旧版铁律，**改版后已按用户决定解除**：运行时依赖 customtkinter + Pillow。
- Python 3.10+。源码包在 `src/starsnip/`（src 布局）。

## 环境与运行

仓库内置虚拟环境 `.venv`（在 E 盘，非 C 盘）。安装：`python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt`。

```powershell
$env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python -m starsnip              # 托盘 + 全局热键常驻
.venv\Scripts\python -m starsnip --check      # 检查 Ollama 并列出模型（先跑这个）
.venv\Scripts\python -m starsnip --file a.png
.venv\Scripts\python -m starsnip --diagnose   # 后端/托盘/热键体检，写日志
.venv\Scripts\python -m starsnip --mcp        # MCP stdio（需 mcp<2）
```

- `run.bat` 优先用 `.venv\Scripts\pythonw.exe` 后台启动（无控制台）；调试用上面的 `python -m starsnip`。
- 打包：`tools\build_exe.bat` → `dist\StarSnip.exe`，并把 `config.json` 与 `assets\` 复制到 exe 同目录。`StarSnip.spec` 收集 customtkinter/darkdetect 资源 + `assets/`，图标 `assets/starsnip.ico`。

## 测试（不是 pytest）

- 每个 `tests\test_*.py` 是独立脚本。`tools\rename_tests.py` 已把所有测试的硬编码旧路径
  `D:\030\screenocr\src` 改为基于 `__file__` 的鲁棒路径，并把 `screenocr`→`starsnip`。
  跑测试仍需 `$env:PYTHONPATH="src"`（或经 venv）。
  - 单个：`.venv\Scripts\python tests\test_tablefmt.py`
  - 全量：`Get-ChildItem tests\test_*.py | % { .venv\Scripts\python $_.FullName }`
- 离线纯逻辑：`test_png` `test_tablefmt` `test_writers` `test_history` `test_logger`。
- `test_capture`/`test_clipboard` 走 GDI/剪贴板，不弹窗；剪贴板偶发 `clipboard busy` 属外部占用，运行时有 try/except 兜底，非缺陷。
- 需要真实桌面会话（创建窗口/注册热键，勿在他人工作中途自动跑）：`test_tray` `test_hotkey` `test_overlay` `test_toast` `test_history_ui` `test_e2e`。
- 需要 Ollama：`test_ocr_core` `test_export` `test_e2e`。
- 测试会占用 `ctrl+alt+o`；先结束正在运行的 `pythonw`/`StarSnip` 实例。

## UI 验收探针

`tools\_ui_probe.py`：用样例数据逐个渲染各 CTk 窗口/Toast 并截客户区到 `tools\_shots\`（不截全屏遮罩、不联网、不注册热键）。改完 UI 后跑它出图做视觉评审。`tools\_shots\` 已 gitignore。

## 架构要点

主链路：热键/托盘 → `overlay` 取景 → `capture`(GDI, DPI aware) → 副作用(存 PNG/剪贴板/Toast) → `ocr_core` → `ui` 结果窗口 → 翻译/贴图/美化/导出。

- **设计系统 = `theme.py`**：所有窗口从它取令牌。
  - CTk 控件用 **(light,dark) 二元组** 颜色：`ACCENT/ACCENT_HOVER/DANGER/SURFACE/SURFACE_SOFT/SEPARATOR/FG/FG_SECONDARY/SEL`（CTk 随外观模式自动切换）。
  - 给内部 `tk.Text`/Canvas/ttk 用**字典**色板 `TEXT_BG/TEXT_FG/TEXT_BG_SOFT/SEL_BG`，用 `theme._mode_key()` 取当前实色，或用 `theme.resolve((l,d))` 把二元组降为单色。
  - **字体必须在使用时建**（根窗口已存在后）：各窗口 `__init__` 里 `self._F = theme.Fonts()`，用 `self._F.title/body/label/small/mono/mono_big`。**切勿在模块导入期创建 `CTkFont`**（无默认 root 会 `RuntimeError: Too early to use font`）。
  - 图标经 `theme.icon_ico()/icon_png()/logo_image()/photo()`，路径由 `paths.app_root()/_MEIPASS` 解析。
- `ocr_core.pick_mode`：模型名含 `unlimited-ocr` 走 `/api/chat`，其余 `/api/generate`，勿写死。
- AI 排版/翻译：`ai_writer.llm_layout` 与 `ai_writer.translate` **必须保留 `think:False`**（qwen3.5 默认思考会让排版 ~4s 变 ~65s）。翻译自动判中↔英，模型用 `translate_model or layout_model`。
- 新功能模块：`pin.py`（贴图，tk+PIL 帧）、`beautify.py`（圆角/阴影/留白分享图，Pillow）、`imgconv.py`（截图↔Pillow，raw `BGRX`/`BGRX` 编解码）、`settings_ui.py`（设置中心）。
- 结果窗口导出映射：docx/txt/xlsx/md → `on_export`；png → `on_beautify`。`_translate` 在「译文」与原文间切换（依赖 `ResultWindow._orig_text/_trans_text/_showing_translation`）。
- 配置：`config.load()` 用 `DEFAULTS` 合并根 `config.json`；改单项用 `config.save_setting`（保留其它键）。新增键：`theme/translate_model/pin_alpha/beautify_bg/beautify_pad_ratio`（DEFAULTS 与 config.json 都要有）。`sys.frozen` 时配置在 exe 同目录。
- 路径集中在 `paths.py`：数据目录 `%APPDATA%\StarSnip`（`STARSNIP_HOME`，兼容旧 `SCREENOCR_HOME`；新目录不存在且旧 `ScreenOCR` 目录存在时沿用旧目录，保历史）；日志 `starsnip.log`；截图 `图片\StarSnip`；导出 `文档\StarSnip`。
- 环境变量：`OLLAMA_URL`、`OLLAMA_MODEL`、`STARSNIP_HOME`。

## 约定与坑

- 源码/文档/UI 文案均中文 UTF-8。GBK 控制台报 `UnicodeEncodeError` 设 `PYTHONIOENCODING=utf-8`。
- 无 lint/formatter/typecheck/CI；风格：4 空格、`%` 格式化、有意兜底异常标 `# noqa: BLE001`。
- MCP 需 `mcp<2`，按需导入。应用 MCP 是 `src/starsnip/mcp_server.py`；`ocr/` 目录是早期 PRD/压测/另一旧 MCP，非运行时。
- 同一用户不能同时跑两个实例（全局热键冲突）。
- 品牌：中文「星剪」，英文/代码名「StarSnip」，包名 `starsnip`。`docs/开发计划.md`、`docs/工作日志.md` 含历史 `D:\030\screenocr` 路径，与代码冲突时以代码/README 为准。
