"""capture.Image(BGRA 字节) 与 Pillow 图像互转（贴图/美化功能用 Pillow）。"""

from PIL import Image as PILImage


def to_pil(img):
    """capture.Image(BGRA/BGRX) -> Pillow RGB 图像。

    注意：Pillow 13 的 ``frombytes("RGBA", ..., "raw", "BGRX")`` 会抛
    ``ValueError: unknown raw mode for given image mode``（旧版本能跑，升级后必崩）。
    这里改成目标是 RGB、rawmode 用 "BGRX"：既能正确换回 RGB，又顺手丢掉
    GDI 里恒为 0 的 alpha 字节（否则会得到一张全透明图）。
    """
    return PILImage.frombytes("RGB", (img.width, img.height),
                              img.bgra, "raw", "BGRX")


def to_bgra(pil):
    """Pillow RGB/RGBA -> (bgra bytes, w, h)，供剪贴板 CF_DIB 使用。

    走 Pillow 的 raw 编码器（C 速度），每像素输出 B,G,R,pad。
    """
    rgb = pil.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes("raw", "BGRX")
    return data, w, h
