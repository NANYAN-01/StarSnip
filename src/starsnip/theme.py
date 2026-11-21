"""星剪 StarSnip 设计系统。

集中配色、字体、间距与外观模式，所有界面从这里取令牌，保证统一：
- 浅色 / 深色随系统自动切换，也可在设置里手动指定；
- 单一品牌强调色（紫罗兰 #6C5CE7），圆角、留白、字重遵循现代简约原则；
- 提供图标路径与 CTkImage 便捷构造，避免各处重复加载。
"""

import os

import customtkinter as ctk
from PIL import Image

from . import paths

# ---------- 外观 ----------
# 设置项 theme 取值："system" / "light" / "dark"
_MODE_MAP = {"system": "system", "light": "light", "dark": "dark"}

# ---------- 调色板（强调色在浅/深模式下微调，保证对比度） ----------
ACCENT = ("#6C5CE7", "#7D6CF0")           # 主强调
ACCENT_HOVER = ("#5A4BD1", "#8E7FF5")     # 强调悬停
ACCENT_TEXT = "#FFFFFF"

DANGER = ("#DC2626", "#F87171")

# 语义中性色（用于文字 / 边框 / 分隔）：以 (light, dark) 给 CTk 控件
FG = ("#1C1C1E", "#F2F2F7")
FG_SECONDARY = ("#6E6E73", "#AEAEB2")
SEPARATOR = ("#D9D9DE", "#3A3A3E")

# CTk 控件用的表面色（(light, dark) 元组，CTk 随模式自动切换）
SURFACE = ("#FFFFFF", "#1E1E22")          # 内容卡背景
SURFACE_SOFT = ("#F5F5F7", "#232329")     # 次级背景 / 幽灵按钮
SEL = ("#D7CEFF", "#3A3364")              # 选中

# 供内部 tk.Text（非 CTk 控件）使用的实色，按当前模式取
TEXT_FG = {"light": "#1C1C1E", "dark": "#F2F2F7"}
TEXT_BG = {"light": "#FFFFFF", "dark": "#1E1E22"}
TEXT_BG_SOFT = {"light": "#F5F5F7", "dark": "#232329"}
SEL_BG = {"light": "#D7CEFF", "dark": "#3A3364"}

# 圆角与尺寸令牌
RADIUS = 12
RADIUS_SM = 8
RADIUS_PILL = 999
PAD = 16
CONTROL_H = 36

# ---------- 设置中心（DeskBox 风格）令牌 ----------
# 层次完全靠「底 → 卡片 → 描边」三档明度叠出来，不用投影：
BG = ("#F4F4F7", "#141416")            # 窗口底，比卡片暗一档
CARD_STROKE = ("#E4E4EA", "#2E2E34")   # 1px 卡片描边（深色约 12% 白）
INPUT_BG = ("#F7F7FA", "#191A1D")      # 输入框 / 下拉框底
NAV_SEL = ("#ECE7FF", "#26232F")       # 导航选中底（强调色的低饱和变体）
ROW_GAP = 4                            # 卡片之间的缝（不是分割线）
ROW_H = 64                             # 设置卡最小高度
NAV_W = 214                            # 左导航轨宽度
RADIUS_CARD = 6                        # 卡片 / 按钮圆角

# 分段按钮统一配色（否则 CTk 默认主题的蓝色会和品牌紫冲突）
SEG_STYLE = {
    "selected_color": ACCENT,
    "selected_hover_color": ACCENT_HOVER,
    "unselected_color": SURFACE_SOFT,
    "unselected_hover_color": SEPARATOR,
    "text_color": FG,
}


def apply_theme(theme: str = "system") -> str:
    """设置全局外观模式，返回实际生效模式（dark/light）。

    切换后会通知已注册的监听者（tk 原生控件无法自动跟随，
    例如 ttk.Treeview 的配色要自己重刷）。
    """
    mode = _MODE_MAP.get(theme, "system")
    ctk.set_appearance_mode(mode)
    _prune_listeners()
    for fn in list(_listeners):
        try:
            fn()
        except Exception:  # noqa: BLE001 - 监听者自己出错不影响切换
            pass
    try:
        import darkdetect  # noqa: F401
        return ctk.get_appearance_mode().lower()
    except Exception:  # noqa: BLE001
        return "dark" if mode == "dark" else "light"


_listeners = []


def on_theme_change(fn) -> None:
    """注册「主题切换后要重刷的控件」。窗口销毁后回调需自行判存在。"""
    if fn not in _listeners:
        _listeners.append(fn)


def _prune_listeners() -> None:
    """丢掉已销毁窗口的回调：每开一次结果/历史窗口都会注册新的绑定方法，
    不清理会无限累积（切主题时逐个调用已销毁窗口的回调）。"""
    alive = []
    for fn in _listeners:
        owner = getattr(fn, "__self__", None)
        try:
            if owner is not None and not owner.winfo_exists():
                continue
        except Exception:  # noqa: BLE001 - owner 不是窗口，原样保留
            pass
        alive.append(fn)
    _listeners[:] = alive



def _mode_key() -> str:
    return "dark" if ctk.get_appearance_mode().lower().startswith("dark") else "light"


def resolve(pair):
    """把 (light, dark) 解析为当前模式的实色；非元组原样返回。"""
    if isinstance(pair, tuple) and len(pair) == 2:
        return pair[1] if _mode_key() == "dark" else pair[0]
    return pair


def font(size: int = 14, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    family = "Cascadia Mono" if mono else "Segoe UI"
    return ctk.CTkFont(family=family, size=size, weight=weight)


# Segoe Fluent Icons（Win11）→ Segoe MDL2 Assets（Win10）→ 系统默认字体
_GLYPH_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")


def glyph_font(size: int = 18) -> ctk.CTkFont:
    """图标字体：Win11/Win10 自带的 Fluent 字形，无需打包图标资源。

    没有这两套字体的机器（如精简系统）退回 Segoe UI，字形会显示成方框，
    但不影响布局与点击。
    """
    family = "Segoe UI"
    try:
        import tkinter.font as tkfont

        have = set(tkfont.families())
        for name in _GLYPH_FAMILIES:
            if name in have:
                family = name
                break
    except Exception:  # noqa: BLE001 - 拿不到字体表就用默认字体
        pass
    return ctk.CTkFont(family=family, size=size)


class Fonts:
    """在根窗口创建之后再实例化（CTkFont 需要默认 root）。

    各窗口在自己的 __init__ 里 `self._F = theme.Fonts()` 使用，避免模块导入即建字体。
    """

    def __init__(self):
        self.title = font(16, "bold")
        self.body = font(14)
        self.label = font(13)
        self.small = font(12)
        self.mono = font(13, mono=True)
        self.mono_big = font(20, "bold", mono=True)
        # 设置中心字阶：28 页面标题 / 15 小节 / 14 卡标题 / 12 描述 / 11 辅助
        # 只有 Regular 与 Bold 两档（Tk 只认 normal|bold，不做半粗）
        self.display = font(28, "bold")
        self.section = font(15, "bold")
        self.card = font(14)
        self.card_bold = font(14, "bold")
        self.desc = font(12)
        self.caption = font(11)
        self.nav = font(14)
        self.nav_bold = font(14, "bold")
        self.glyph = glyph_font(18)
        self.glyph_sm = glyph_font(15)



# ---------- 图标 ----------
def icon_png(name: str = "starsnip.png") -> str:
    return paths.resource_path(name)


def icon_ico(name: str = "starsnip.ico") -> str:
    p = paths.resource_path(name)
    return p if os.path.isfile(p) else ""


def logo_image(size: int = 22):
    """返回窗口/关于页用的小 logo CTkImage；缺文件返回 None。"""
    p = icon_png("starsnip.png")
    if not os.path.isfile(p):
        return None
    img = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def thumb_image(path: str, size):
    """缩略图专用的 CTkImage（CTkLabel 只认 CTkImage，用 ImageTk 会告警且高分屏模糊）。

    返回 (CTkImage, w, h)；文件缺失/损坏返回 (None, 0, 0)。
    """
    try:
        img = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None, 0, 0
    img.thumbnail((size[0], size[1]), Image.LANCZOS)
    return (ctk.CTkImage(light_image=img, dark_image=img, size=img.size),
            img.width, img.height)
