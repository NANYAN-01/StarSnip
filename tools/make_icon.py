"""星剪 StarSnip 品牌图标生成器（PIL，纯程序化、无水印、可缩放）。

概念：取景框四角括号 + 五角星 + 一点闪光，置于紫→蓝渐变圆角徽标上。
输出：
  assets/starsnip.ico   多尺寸托盘/窗口/exe 图标
  assets/starsnip.png   256px 窗口图标
  assets/logo.png       1024px 品牌主图（README / 关于页）
  assets/logo_dark.png  透明底纯字形版（浅色场景备用）

运行： python tools/make_icon.py
"""

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

VIOLET = (108, 92, 231)     # #6C5CE7
BLUE = (0, 168, 232)        # #00A8E8
WHITE = (255, 255, 255, 255)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(size, top_left=VIOLET, bottom_right=BLUE):
    """对角线性渐变背景（RGBA）。"""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    span = 2 * (size - 1)
    for y in range(size):
        for x in range(size):
            t = (x + y) / span
            r, g, b = _lerp(top_left, bottom_right, t)
            px[x, y] = (r, g, b, 255)
    return img


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=radius,
                                           fill=255)
    return mask


def star_points(cx, cy, r_outer, r_inner, rotation=-90.0):
    """五角星 10 顶点（外/内半径交替），rotation 度，-90=一尖朝上。"""
    pts = []
    rot = math.radians(rotation)
    for i in range(10):
        ang = rot + i * math.pi / 5
        rad = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def _bracket_lines(size, inset, thickness):
    """返回四条角括号线段（每条由两线段组成）用于 rounded 端点绘制。"""
    a, b = inset, size - inset
    half = thickness / 2.0
    seg = int(size * 0.16)  # 角臂长度
    return [
        ((a + half, a + half), (a + half + seg, a + half)), ((a + half, a + half), (a + half, a + half + seg)),
        ((b - half, a + half), (b - half - seg, a + half)), ((b - half, a + half), (b - half, a + half + seg)),
        ((a + half, b - half), (a + half + seg, b - half)), ((a + half, b - half), (a + half, b - half - seg)),
        ((b - half, b - half), (b - half - seg, b - half)), ((b - half, b - half), (b - half, b - half - seg)),
    ]


def make_glyph(size, glyph_color=WHITE):
    """绘制居中字形层（取景括号 + 星 + 闪光），返回 RGBA 透明底图。"""
    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(glyph)
    inset = int(size * 0.16)
    thickness = max(3, int(size * 0.055))
    for (x1, y1), (x2, y2) in _bracket_lines(size, inset, thickness):
        d.line([x1, y1, x2, y2], fill=glyph_color, width=thickness, joint="curve")
    cx = cy = size / 2.0
    d.polygon(star_points(cx, cy, size * 0.30, size * 0.145), fill=glyph_color)
    # 闪光：位于星尖右上方内侧（避开角括号，完整呈现）
    sx, sy = cx + size * 0.185, cy - size * 0.195
    sr = size * 0.062
    si = size * 0.016
    d.polygon(star_points(sx, sy, sr, si, rotation=-90.0), fill=glyph_color)
    return glyph


def build_app_icon(size, glyph_color=WHITE, transparent=False):
    glyph = make_glyph(size, glyph_color)
    if transparent:
        return glyph
    bg = gradient_bg(size)
    bg.putalpha(rounded_mask(size, int(size * 0.223)))
    bg = Image.composite(bg, Image.new("RGBA", (size, size), (0, 0, 0, 0)), bg)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(bg)
    out.alpha_composite(glyph)
    return out


def main():
    os.makedirs(ASSETS, exist_ok=True)
    icon = build_app_icon(1024)
    icon.save(os.path.join(ASSETS, "logo.png"))
    icon_1024 = icon.resize((256, 256), Image.LANCZOS)
    icon_1024.save(os.path.join(ASSETS, "starsnip.png"))
    glyph_white = make_glyph(1024, WHITE)
    glyph_white.resize((512, 512), Image.LANCZOS).save(
        os.path.join(ASSETS, "logo_dark.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon.save(os.path.join(ASSETS, "starsnip.ico"),
              sizes=[(s, s) for s in sizes])
    print("图标已生成于", ASSETS)
    for f in ("starsnip.ico", "starsnip.png", "logo.png", "logo_dark.png"):
        p = os.path.join(ASSETS, f)
        print("  %-16s %6.1f KB" % (f, os.path.getsize(p) / 1024))


if __name__ == "__main__":
    main()
