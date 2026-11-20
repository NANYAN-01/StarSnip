"""capture.Image(BGRA 字节) 与 Pillow 图像互转（贴图/美化功能用 Pillow）。"""

from PIL import Image as PILImage


def to_pil(img):
    """capture.Image -> Pillow RGBA（不透明）。"""
    return PILImage.frombytes("RGBA", (img.width, img.height),
                              img.bgra, "raw", "BGRX")


def to_bgra(pil):
    """Pillow RGB/RGBA -> (bgra bytes, w, h)，供剪贴板 CF_DIB 使用。

    走 Pillow 的 raw 编码器（C 速度），每像素输出 B,G,R,pad。
    """
    rgb = pil.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes("raw", "BGRX")
    return data, w, h
