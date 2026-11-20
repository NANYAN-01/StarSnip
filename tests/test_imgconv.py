"""截图 <-> Pillow 转换（纯逻辑）：来回转换后颜色必须一致。

回归背景：Pillow 13 的 frombytes("RGBA", ..., "BGRX") 会抛
ValueError: unknown raw mode -> 贴图 / 美化 / 取景遮罩铺底全部失效。
"""

import os
import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from PIL import Image

from starsnip import capture, imgconv


def make_image(width, height, colors):
    """按 colors 逐像素填充 BGRA 缓冲区（模拟 GDI 输出，alpha 字节为 0）。"""
    buf = bytearray()
    for y in range(height):
        for x in range(width):
            r, g, b = colors[(x + y) % len(colors)]
            buf.extend((b, g, r, 0))
    return capture.Image(width, height, bytes(buf), (0, 0))


def main():
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (18, 52, 86)]
    img = make_image(4, 3, colors)

    pil = imgconv.to_pil(img)
    assert pil.mode == "RGB", pil.mode
    assert pil.size == (4, 3), pil.size
    for y in range(3):
        for x in range(4):
            want = colors[(x + y) % len(colors)]
            got = pil.getpixel((x, y))
            assert got == want, (x, y, got, want)
    print("to_pil BGRA->RGB 颜色正确（%d 像素）" % (4 * 3))

    data, w, h = imgconv.to_bgra(pil)
    assert (w, h) == (4, 3), (w, h)
    assert len(data) == 4 * 3 * 4, len(data)
    back = capture.Image(w, h, data, (0, 0))
    pil2 = imgconv.to_pil(back)
    for y in range(3):
        for x in range(4):
            assert pil2.getpixel((x, y)) == pil.getpixel((x, y)), (x, y)
    print("to_pil / to_bgra 往返一致")

    # 真实 PNG 走一遍：读 -> BGRA -> PIL，尺寸与内容保持
    here = os.path.dirname(os.path.abspath(__file__))
    fixture = os.path.normpath(os.path.join(here, "..", "fixtures", "ocr_test.png"))
    if os.path.isfile(fixture):
        src = Image.open(fixture).convert("RGB")
        d, w, h = imgconv.to_bgra(src)
        again = imgconv.to_pil(capture.Image(w, h, d, (0, 0)))
        assert again.size == src.size, (again.size, src.size)
        diff = max(abs(a - b) for a, b in
                   zip(again.tobytes(), src.tobytes()))
        assert diff <= 1, diff
        print("PNG 往返最大色差 = %d" % diff)

    print("test_imgconv OK")


if __name__ == "__main__":
    main()
