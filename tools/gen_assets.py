# -*- coding: utf-8 -*-
"""生成安卓 icon.png / presplash.png（纯 Python，无第三方依赖）。
图标 = 深绿底 + 金色圆角方 + 五筒（5 颗红饼点），呼应「卡五星」。"""
import struct, zlib, os

def write_png(path, w, h, pixel_fn):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            r, g, b = pixel_fn(x, y)
            raw += bytes((r, g, b))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    print("wrote", path, os.path.getsize(path), "bytes")

GREEN_BG = (10, 62, 40)
GREEN_DK = (7, 48, 31)
GOLD = (230, 190, 70)
GOLD_DK = (190, 152, 44)
RED = (200, 42, 36)
RED_DK = (150, 26, 22)
WHITE = (247, 243, 231)

def rounded(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    dx = max(x0 + r - x, x - (x1 - r), 0)
    dy = max(y0 + r - y, y - (y1 - r), 0)
    return dx * dx + dy * dy <= r * r

def dot(cx, cy, rad, x, y):
    d2 = (x - cx) ** 2 + (y - cy) ** 2
    if d2 <= rad * rad:
        return RED if d2 > (rad * 0.62) ** 2 else WHITE
    return None

def icon_pixel(x, y, W, H):
    m = min(W, H)
    if rounded(x, y, W*0.06, H*0.06, W*0.94, H*0.94, m*0.16):
        # 五筒：5 颗饼点
        r = m * 0.105
        pts = [(0.5, 0.28), (0.27, 0.5), (0.73, 0.5), (0.5, 0.72)]
        # 排成梅花：上1 中2 下… 改成标准五点
        pts = [(0.5, 0.30), (0.28, 0.50), (0.72, 0.50), (0.28, 0.72), (0.72, 0.72)]
        for nx, ny in pts:
            c = dot(nx*W, ny*H, r, x, y)
            if c:
                # 描边
                d2 = (x-nx*W)**2 + (y-ny*H)**2
                if d2 >= (r*0.94)**2:
                    return RED_DK
                return c
        if rounded(x, y, W*0.10, H*0.10, W*0.90, H*0.90, m*0.14):
            return GREEN_BG
        return GOLD
    return GREEN_DK

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
write_png(os.path.join(here, "icon.png"), 512, 512,
          lambda x, y: icon_pixel(x, y, 512, 512))
write_png(os.path.join(here, "presplash.png"), 1024, 600,
          lambda x, y: icon_pixel(x, y, 1024, 600))
