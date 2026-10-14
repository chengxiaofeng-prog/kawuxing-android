# -*- coding: utf-8 -*-
"""
校验子集字体是否真的可用 —— 用 GDI+ 把字渲染成位图，数黑色像素。

判定逻辑（比测量宽度更硬）：
  · GdipPrivateAddFontFile 能成功  -> 字体文件结构 / 校验和合法；
  · 每个字符渲染后黑色像素数 > 阈值 -> 真的有字形被画出来，不是空白或方框；
  · 不同字符的像素数不同            -> 不是全部退化成同一个 .notdef 方框。

为什么用 GDI+：沙箱装不上 Pillow / fontTools，本机 Tk 8.6.9 不支持 -file。
GDI+ 是独立的 TrueType 解析器，跟 Android 上 Kivy 用的 FreeType 互为旁证。
"""
import ctypes
import os
import sys
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FONT = os.path.join(HERE, "..", "fonts", "NotoSansSC-Regular.ttf")

SAMPLES = (
    "卡五星胡杠碰吃听牌自摸亮倒点炮和局中西北白筒条万"
    "游戏开始继续重开退出你左家右家分数庄家"
    "东南西北中发白一二三四五六七八九"
    "暗明补抢杠上开花荒庄听推演托管下一局"
    "0123456789ABCabc，。！？：；、（）"
)

SIZE = 48          # 字号（像素）
CANVAS = 96        # 画布边长


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", wintypes.BOOL),
        ("SuppressExternalCodecs", wintypes.BOOL),
    ]


class RectF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float),
                ("Width", ctypes.c_float), ("Height", ctypes.c_float)]


class GdiplusBitmapData(ctypes.Structure):
    _fields_ = [
        ("Width", ctypes.c_uint32),
        ("Height", ctypes.c_uint32),
        ("Stride", ctypes.c_int),
        ("PixelFormat", ctypes.c_int),
        ("Scan0", ctypes.c_void_p),
        ("Reserved", ctypes.c_void_p),
    ]


def render_ink(g, family, ch):
    """把一个字符渲染到 32bpp 位图，返回墨迹像素数（按 alpha 通道统计）。"""
    bitmap = ctypes.c_void_p()
    # PixelFormat32bppARGB = 0x0026200A
    if g.GdipCreateBitmapFromScan0(CANVAS, CANVAS, 0, 0x0026200A, None,
                                   ctypes.byref(bitmap)) != 0:
        return -1

    try:
        graphics = ctypes.c_void_p()
        if g.GdipGetImageGraphicsContext(bitmap, ctypes.byref(graphics)) != 0:
            return -1
        try:
            # 全透明底：这样只要数 alpha != 0 的像素就是墨迹，不受底色干扰
            g.GdipGraphicsClear(graphics, ctypes.c_uint32(0x00000000))

            font = ctypes.c_void_p()
            if g.GdipCreateFont(family, ctypes.c_float(SIZE), 0, 2,
                                ctypes.byref(font)) != 0:
                return -1
            try:
                brush = ctypes.c_void_p()
                g.GdipCreateSolidFill(ctypes.c_uint32(0xFF000000), ctypes.byref(brush))
                try:
                    fmt = ctypes.c_void_p()
                    g.GdipCreateStringFormat(0, 0, ctypes.byref(fmt))
                    try:
                        # 禁用字体回退：缺字不会被悄悄换成方框
                        g.GdipSetStringFormatFlags(fmt, 0x00004000)
                        layout = RectF(0.0, 0.0, float(CANVAS), float(CANVAS))
                        g.GdipDrawString(graphics, ctypes.c_wchar_p(ch), 1, font,
                                         ctypes.byref(layout), fmt, brush)
                    finally:
                        g.GdipDeleteStringFormat(fmt)
                finally:
                    g.GdipDeleteBrush(brush)
            finally:
                g.GdipDeleteFont(font)
        finally:
            g.GdipDeleteGraphics(graphics)

        # 锁定位图，只读（ImageLockModeRead = 1）
        data = GdiplusBitmapData()
        rect = (ctypes.c_int * 4)(0, 0, CANVAS, CANVAS)
        if g.GdipBitmapLockBits(bitmap, rect, 1, 0x0026200A,
                                ctypes.byref(data)) != 0:
            return -1
        try:
            buf = ctypes.string_at(data.Scan0, data.Stride * CANVAS)
        finally:
            g.GdipBitmapUnlockBits(bitmap, ctypes.byref(data))

        # 32bppARGB 内存布局为 BGRA，alpha 在第 4 字节
        ink = 0
        for i in range(3, len(buf), 4):
            if buf[i] > 8:
                ink += 1
        return ink
    finally:
        g.GdipDisposeImage(bitmap)


def main():
    font_path = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(DEFAULT_FONT)
    if not os.path.exists(font_path):
        print("[FAIL] 字体文件不存在: %s" % font_path)
        return 1

    print("字体文件: %s" % font_path)
    print("大小    : %.1f KB" % (os.path.getsize(font_path) / 1024.0))

    g = ctypes.windll.gdiplus
    token = ctypes.c_void_p()
    si = GdiplusStartupInput()
    si.GdiplusVersion = 1
    if g.GdiplusStartup(ctypes.byref(token), ctypes.byref(si), None) != 0:
        print("[FAIL] GDI+ 初始化失败")
        return 1

    try:
        coll = ctypes.c_void_p()
        g.GdipNewPrivateFontCollection(ctypes.byref(coll))
        try:
            st = g.GdipPrivateAddFontFile(coll, ctypes.c_wchar_p(font_path))
            if st != 0:
                print("[FAIL] GDI+ 无法解析该字体文件（状态码 %d）" % st)
                return 1

            count = ctypes.c_int()
            g.GdipGetFontCollectionFamilyCount(coll, ctypes.byref(count))
            if count.value == 0:
                print("[FAIL] 字体文件里没有字体族")
                return 1

            fams = (ctypes.c_void_p * count.value)()
            got = ctypes.c_int()
            g.GdipGetFontCollectionFamilyList(coll, count.value, fams,
                                              ctypes.byref(got))
            name = ctypes.create_unicode_buffer(256)
            g.GdipGetFamilyName(fams[0], name, 0)
            print("字体族  : %s" % name.value)

            inks, blanks = {}, []
            for ch in SAMPLES:
                n = render_ink(g, fams[0], ch)
                if n < 0:
                    print("[FAIL] 渲染 %r 时出错" % ch)
                    return 1
                inks[ch] = n
                if n < 20:            # 少于 20 个墨迹像素基本等于空白
                    blanks.append(ch)
        finally:
            g.GdipDeletePrivateFontCollection(ctypes.byref(coll))
    finally:
        g.GdiplusShutdown(token)

    total = len(SAMPLES)
    distinct = len(set(inks.values()))
    print("测试字符: %d   墨迹像素种类: %d" % (total, distinct))

    if blanks:
        print("[FAIL] %d 个字符渲染为空白: %s" % (len(blanks), "".join(blanks)))
        return 1
    if distinct < 10:
        print("[FAIL] 字形墨迹高度雷同，可能全部退化成了方框")
        return 1

    print("[OK] 全部 %d 个字符都能正常渲染出字形" % total)
    print("     样例墨迹像素: " + ", ".join(
        "%s=%d" % (c, inks[c]) for c in "卡五星胡杠碰听牌" if c in inks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
