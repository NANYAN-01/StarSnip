"""美化分享图导出：给截图加圆角、柔和投影与留白背景，一键适合分享。

借鉴 macshot / mark-shot 的「beautify export」：圆角 + 阴影 + 呼吸感留白，
背景可选纯白或品牌渐变。纯 Pillow 实现，无需外部图片库。
"""

import io

from PIL import Image, ImageDraw, ImageFilter

VIOLET = (108, 92, 231)
BLUE = (0, 168, 232)


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                            radius=radius, fill=255)
    return mask


def _gradient(size):
    w, h = size
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(VIOLET[i] + (BLUE[i] - VIOLET[i]) * t) for i in range(3))
    return base.resize((w, h))


def render(pil, cfg=None):
    """返回美化后的 PIL.Image（RGBA）。"""
    cfg = cfg or {}
    img = pil.convert("RGB")
    w, h = img.size
    pad_ratio = float(cfg.get("beautify_pad_ratio", 0.08))
    pad = max(28, int(min(w, h) * pad_ratio))
    radius = max(10, int(min(w, h) * float(cfg.get("beautify_radius_ratio", 0.025))))
    bg = cfg.get("beautify_bg", "white")
    out_w, out_h = w + pad * 2, h + pad * 2

    if bg == "gradient":
        canvas = _gradient((out_w, out_h)).convert("RGBA")
    else:
        canvas = Image.new("RGBA", (out_w, out_h), (248, 248, 250, 255))

    # 柔和投影
    shadow_pad = pad
    blur = max(6, pad // 3)
    off_y = max(3, pad // 5)
    smask = Image.new("L", (out_w, out_h), 0)
    ImageDraw.Draw(smask).rounded_rectangle(
        [pad, pad + off_y, pad + w, pad + off_y + h], radius=radius, fill=170)
    smask = smask.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", (out_w, out_h), (15, 15, 25, 255))
    canvas = Image.composite(shadow, canvas, smask)

    # 圆角截图
    rounded = img.convert("RGBA")
    rounded.putalpha(_rounded_mask((w, h), radius))
    canvas.alpha_composite(rounded, (pad, pad))
    return canvas


def png_bytes(im):
    """把渲染结果编码为 PNG 字节。"""
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
