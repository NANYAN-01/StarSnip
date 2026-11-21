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
.venv\Scripts\python -m starsnip --settings   # 直接打开设置窗口（逐界面体检用）
.venv\Scripts\python -m starsnip --history    # 直接打开历史记录
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
- 离线纯逻辑：`test_png` `test_tablefmt` `test_writers` `test_history` `test_logger` `test_imgconv` `test_model_filter` `test_single_instance` `test_autostart` `test_update` `test_startup`。
  - `test_startup` 只做只读校验（**绝不在测试里写 HKCU Run**，否则会改到跑测试的人自己的登录启动项）；真机验证用 `startup.enable/disable` 手动跑一遍。
- 界面结构自检：`test_ui_smoke`（逐个窗口校验字段已布局、按钮回调连通、Toast 文字不越界、遮罩压暗块坐标、贴图/美化），`test_overlay` `test_toast` `test_history_ui` `test_hotkey_settings`。
- 静态自检：`tools\_check_undefined.py` 扫 `self.xxx` 被引用但未定义/未赋值（含 `on_export=self._export_file` 这类回调传参），能抓出「启动即崩/按钮点了报错」类缺陷；元组拆包赋值（`self.a, self.b = ...`）会误报，需人工确认。
- `test_capture`/`test_clipboard` 走 GDI/剪贴板，不弹窗；剪贴板偶发 `clipboard busy` 属外部占用，运行时有 try/except 兜底，非缺陷。
- **DPI 铁律**：`capture.enable_dpi_awareness()` 必须在创建 Tk 根窗口**之前**调用（`__main__._run_gui` 已做）。否则 Tk 按虚拟化坐标工作（150% 时把 2560×1600 当 1707×1067），全屏遮罩、Toast 定位、鼠标与截图坐标全部错位。
- **Tk 单线程铁律**：任何后台线程都不得直接调 `after()/configure()/insert()`；一律 `queue.Queue` 丢结果、主线程 `after` 轮询消费（设置里的模型列表、OCR 结果都是这个模式）。跨线程调用会抛 `RuntimeError: main thread is not in main loop`。
- **配置文件 BOM**：读取一律 `encoding="utf-8-sig"`。记事本/PowerShell 写出的 BOM 会让 `json.load` 抛错，配合兜底就会被静默丢弃（表现为「本地配置整段失效」）。
- **主题即时生效**：`theme.apply_theme()` 会通知 `theme.on_theme_change()` 注册的回调；`ttk.Treeview` 不跟随 CTk 外观模式，窗口创建时要注册重刷（结果窗口 / 历史窗口已做）。
- **CTk 布局坑**：`CTkScrollableFrame` 内部会套一层 Frame+Canvas，取子控件要用递归查找；`tk.Canvas` 的 `create_rectangle` 不支持 `radius=`，`create_text` 不支持 `bbox`/`bg`（要圆角用 `create_polygon(smooth=True)`，要底色另画矩形）——写错会直接抛 TclError，导致「按热键没反应」。
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
  - 图标经 `theme.icon_ico()/icon_png()/logo_image()/thumb_image()`，路径由 `paths.app_root()/_MEIPASS` 解析。
- **设置中心版式（DeskBox 风格，2026-11 改版）**：`settings_ui.py` 是「214px 左导航轨 + 右内容列」两栏，
  五个分页（常规 / 快捷与交互 / 识别与后端 / 存储与导出 / 关于）都挂在同一个 `CTkScrollableFrame` 里，
  切页只 pack/forget 页面帧；每个设置项是一张 `_SettingsRow`（最小 64px 高、radius 6、1px 描边、
  20px 图标 + 14px 标题 + 12px 描述、控件右对齐），卡片之间用 4px 缝而不是分割线。
  令牌在 `theme.py`：`BG / CARD_STROKE / INPUT_BG / NAV_SEL / ROW_GAP / ROW_H / NAV_W / RADIUS_CARD`，
  字阶 `Fonts.display/section/card/desc/caption/glyph`（Tk 只认 normal|bold，没有真半粗）。
  - 布尔项用自绘 `_Toggle`（40×20 胶囊、滑块内嵌 2px）：CTkSwitch 的滑块骑在轨道右端有一半露在外面，
    浅色下白滑块和白卡片糊成一片，看起来像轨道被咬掉一块。
  - 图标一律 Segoe Fluent Icons 字形（`theme.glyph_font()`，Win11 回落 Win10 的 MDL2），不打包图标资源。
  - **空 CTkFrame 默认请求 200×200**：没有控件的「控件槽」放进 grid 会把整行撑到 200 高，必须显式给 `width=1, height=1`。
  - **CTkEntry 的 `insert("")` 会撤销占位文字且不再恢复**：值为空时不要调 insert，占位文字才会显示。
  - 内容不超出视口时 `_sync_scrollbar()` 会收起滚动条（WinUI 的做法），别把它当成「滚动条消失」的 bug。
- `ocr_core.pick_mode`：模型名含 `unlimited-ocr` 走 `/api/chat`，其余 `/api/generate`，勿写死。
- **OCR 候选模型**：设置「模型接入」里按当前角色拉列表——Ollama 走 `ocr_core.list_ocr_models()`（`is_ocr_model` = 名字含 ocr + 支持 vision，`/api/tags` 无 capabilities 时只看名字；没有 OCR 模型时依次退回视觉模型 / 全部），云端走 `GET {base_url}/models`（不过滤，按需选）。交叉校验仍用「当前 OCR 模型 + `verify_models` 里一个不同模型」。
- **表格识别**：模型对表格可能给 Markdown 管道表，也可能给 `<tr><td>` HTML 片段（glm-ocr 常见，甚至没有 `<table>` 包裹）。`ocr_core.clean_grounding()` 先用 `tablefmt.html_to_markdown()` 统一成 Markdown；`tablefmt.parse_table()` 同时认 Markdown / HTML / 空格对齐，跨行合并单元格当标题、多表不同列宽取第一张。导出时 `ai_writer.export` 用 `tablefmt.structured_table()` 判定：已结构化就本地生成、**不调模型**（避免改数字/并错列）；只有散文才走 AI 排版。表格视图重识别只发起一次（`ResultWindow._table_requested = bool(prefer_table)`），否则解析失败会无限重识别。
- AI 排版/翻译：`ai_writer.llm_layout` / `translate` 都收 `profile`（缺省时把旧 `model/url` 参数当 Ollama 角色，兼容旧调用与测试）；Ollama 分支**必须保留 `think:False`**（qwen3.5 默认思考会让排版 ~4s 变 ~65s）。翻译自动判中↔英，用「主 LLM」角色（没配模型时退回排版角色）；导出走 `App._export_file` → `ai_writer.export`（后台线程 + event 回主线程，排版失败回退原文）。
- 新功能模块：`pin.py`（贴图，tk+PIL 帧）、`beautify.py`（圆角/阴影/留白分享图，Pillow）、`imgconv.py`（截图↔Pillow，raw `BGRX`/`BGRX` 编解码）、`settings_ui.py`（设置中心）、`startup.py`（开机启动三机制）、`update.py`（版本检查与自动更新）、`providers.py`（预置厂商）、`llm.py`（统一模型调用层）。
- **三模型接入（2026-11）**：`cfg["models"]` 是唯一事实源，三个角色 `main/ocr/layout` **各自独立**配 provider / base_url / api_key / model / timeout / stream / auth_header / auth_prefix。`config.normalize_models()` 把只有 `ollama_url/default_model/layout_model` 的老配置迁移成三个 Ollama profile；`config.model_profile(cfg, role)` 取某角色。
  - 云端一律走 OpenAI 兼容 `POST {base_url}/chat/completions`（`llm.chat`，支持 SSE 流式）；Ollama 继续走原生 `/api/generate`、`/api/chat`（`llm.generate` 内部按 provider 分支，OCR 的 unlimited-ocr 仍走 chat 模式）。
  - 预置厂商 BaseURL 在 `providers.PROVIDERS`（下拉顺序即列表顺序，最后一项是「自定义 API」）；选厂商自动填 BaseURL，输入框始终可编辑。阿里百炼预置的是标准 `dashscope.aliyuncs.com/compatible-mode/v1`，`llm-xxx.maas.aliyuncs.com` 属于专属部署，走自定义。
  - **API Key 只写 config.local.json**（`config.save_models`，同时同步 `default_model/layout_model/translate_model` 旧键），绝不进受版本控制的 config.json。
  - 界面按厂商降噪：**鉴权头 / 流式只在「自定义 API」显示**，Ollama 连 API Key 行都隐藏（内网无鉴权也一样）；预置厂商一律标准 Bearer + 非流式，普通用户不用理解这两项。
  - **自测工具** `tools/probe_providers.py`：读你的 API 表格（序号/归属/名称/服务商/Base URL/API Key/包含模型），逐条跑一次 chat 并打码输出；`--vision` 额外发一张带文字的图片验证 OCR 角色。需要 openpyxl（只有这个工具要）。Ollama 走 11434 端口时工具会自动补 `/v1` 重试——**自定义 API 填 Ollama 必须带 /v1**，选「Ollama（本地）」预设改地址则走原生接口、不用 /v1。
  - OCR 云端需要支持图片输入的模型（`image_url` data URL）；本地视觉模型不受影响。
- **开机启动（2026-11 重做）**：`startup.py` 默认写 **HKCU\...\Run**（免 UAC、在「设置→应用→启动」和任务管理器里可见），被组策略 `DisableCurrentUserRun` 拦住时回落 **启动文件夹 .lnk**；`autostart.py` 的计划任务只作为「高级：需管理员/延迟启动」保留。**源码模式必须走启动文件夹**（Run 键没有工作目录，`-m starsnip` 会找不到包）。状态判断要同时看 StartupApproved（12 字节，`02`/`04`＝启用，`03+FILETIME`＝被关掉），只看键是否存在会误报；`startup.enable()` 会在写完后自动修回 `02`。登录启动带 `--startup`，`__main__` 里延迟 1.2s 再挂热键/托盘。
- **版本与更新**：版本号单源 `__init__.__version__`，发版用 `tools/set_version.py X.Y.Z` 同步到 `version.json` 与 `StarSnip.version`（exe 属性页），再跑 `tools/release.ps1`（打包 + SHA256 + 回填下载地址，`-Push` 才提交/打 tag/建 Release）。更新检查三源：`update_url`（config.local.json 自填）→ GitHub Releases API → raw `version.json`；24h 缓存（`%APPDATA%\StarSnip\update.json`）。自动更新流程：静默检查 → 后台下载 → 校验 SHA256 → **退出时**用 `MoveFileExW` 把 exe 改成 `.old`、放新的、再用临时 .cmd 等 2 秒重启（不能直接 Popen：单实例互斥体还没释放）。`update_auto=false` 时只提示不下载。
- 结果窗口导出映射：docx/txt/xlsx/md → `on_export`（已解析出表格时本地直出，普通文本才先 AI 排版）；png → `on_beautify`。`_translate` 在「译文」与原文间切换（依赖 `ResultWindow._orig_text/_trans_text/_showing_translation`）。
- 配置：`config.load()` 用 `DEFAULTS` 合并根 `config.json`；改单项用 `config.save_setting`（保留其它键）。新增键：`theme/translate_model/pin_alpha/beautify_bg/beautify_pad_ratio/beautify_radius_ratio/save_image`（DEFAULTS 与 config.json 都要有）。提示词 `prompt/table_prompt` 的默认值单源在 `ocr_core` 常量（config.DEFAULTS 引用它），config.json 里可覆盖。已删键：`auto_ocr`（两热键分工替代）、`joint_enabled/joint_models`（与「校验双模型」重复，保留 `verify_models`）。`sys.frozen` 时配置在 exe 同目录。
- **隐私铁律**：仓库里的 `config.json` 只放占位值（`ollama_url` 为 `http://127.0.0.1:11434`）。真实内网地址/个人路径写 `config.local.json`（已 gitignore，与 `config.json` 同目录，加载时覆盖它；`save_setting` 也会写它）。**任何提交前先 `git grep -n 172.16` 自查，禁止把内网 IP、主机名、机构信息写进受版本控制的文件。**
- 路径集中在 `paths.py`：数据目录 `%APPDATA%\StarSnip`（`STARSNIP_HOME`，兼容旧 `SCREENOCR_HOME`；新目录不存在且旧 `ScreenOCR` 目录存在时沿用旧目录，保历史）；日志 `starsnip.log`；截图 `图片\StarSnip`；导出 `文档\StarSnip`。
- 环境变量：`OLLAMA_URL`、`OLLAMA_MODEL`、`STARSNIP_HOME`。

## 约定与坑

- 源码/文档/UI 文案均中文 UTF-8。GBK 控制台报 `UnicodeEncodeError` 设 `PYTHONIOENCODING=utf-8`。
- 无 lint/formatter/typecheck/CI；风格：4 空格、`%` 格式化、有意兜底异常标 `# noqa: BLE001`。
- MCP 需 `mcp<2`，按需导入。应用 MCP 是 `src/starsnip/mcp_server.py`；`ocr/` 目录是早期 PRD/压测/另一旧 MCP，非运行时。
- **开机启动**：`autostart.py` 用任务计划程序（任务名 `StarSnip`，`LogonTrigger` + `InteractiveToken` + `LeastPrivilege`）。非提权时用 `ShellExecuteExW("runas")` 提权跑 schtasks（UAC）；取消返回 1223，设置里红字回滚。源码模式任务动作是 `pythonw.exe -m starsnip`、工作目录 `src`（`-m` 会把 cwd 加进 sys.path）；打包版直接跑 exe。任务 XML 写成 UTF-16 临时文件再 `schtasks /Create /XML`。
- **单实例**：常驻模式（无 `--history/--settings/--file`）启动前抢 `single_instance` 命名互斥体（`Local\StarSnip.SingleInstance`）；已有实例时广播 `StarSnip.Activate`，托盘 WndProc 转成 `{"type":"activate"}` 事件 → Toast「已在运行」，新进程记日志后退出。`--file/--history/--settings/--mcp/--check` 不抢锁（不注册热键，可并发）。互斥体随进程退出释放，没有锁文件；改这块注意不要用端口/防火墙。
- **两个全局热键**：`hotkey`（默认 `ctrl+2`，截图+识别）与 `hotkey_capture_only`（默认 `ctrl+1`，仅截图）。`App._start_hotkey` 各起一个 `HotkeyManager`（独立线程，热键 id 互不冲突）；仅截图走 `SelectionOverlay(confirm=True)`，拖完停留、点 ✓/回车才交付。改热键用 `_apply_hotkey(spec, "ocr"|"capture")`。
- **托盘菜单不重复设置入口**：快捷键只在设置窗口改（`App._open_hotkey_dialog` 复用同一个 `HotkeyDialog`），托盘不再有「设置快捷键…」；`hotkey_dialog` 由 App 持有，避免叠出多个对话框。
- 品牌：中文「星剪」，英文/代码名「StarSnip」，包名 `starsnip`。`docs/开发计划.md`、`docs/工作日志.md` 含历史 `D:\030\screenocr` 路径，与代码冲突时以代码/README 为准。
