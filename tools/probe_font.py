# -*- coding: utf-8 -*-
"""
探测本机字体：统计汉字覆盖数与体积，用来挑一个"裁剪后最小"的字体来源。

纯标准库实现（沙箱里装不上 fontTools），只读 cmap 表。
"""
import os
import struct
import sys


def read_sfnt(f):
    """返回 {表名: (偏移, 长度)}，兼容 ttc（取第一个子字体）。"""
    f.seek(0)
    head = f.read(12)
    if head[:4] == b"ttcf":
        num_fonts = struct.unpack(">I", head[8:12])[0]
        offsets = [struct.unpack(">I", f.read(4))[0] for _ in range(num_fonts)]
        f.seek(offsets[0])
        head = f.read(12)
    _, num_tables = struct.unpack(">IH", head[:6])
    tables = {}
    for _ in range(num_tables):
        tag, _cks, off, ln = struct.unpack(">4sIII", f.read(16))
        tables[tag.decode("latin1")] = (off, ln)
    return tables


def read_cmap_codepoints(f, off, ln):
    f.seek(off)
    buf = f.read(ln)
    _, num = struct.unpack(">HH", buf[:4])
    subs = []
    for i in range(num):
        pid, eid, so = struct.unpack(">HHI", buf[4 + i * 8:12 + i * 8])
        subs.append((pid, eid, so))

    def score(s):
        pid, eid, _ = s
        if (pid, eid) == (3, 10):
            return 3
        if (pid, eid) == (3, 1):
            return 2
        if pid == 0:
            return 1
        return 0

    subs.sort(key=lambda s: -score(s))
    chosen = subs[0]
    base = chosen[2]
    fmt = struct.unpack(">H", buf[base:base + 2])[0]
    cps = set()

    if fmt == 4:
        seg_x2 = struct.unpack(">H", buf[base + 6:base + 8])[0]
        seg = seg_x2 // 2
        end_o = base + 14
        start_o = end_o + seg_x2 + 2
        for i in range(seg):
            e = struct.unpack(">H", buf[end_o + i * 2:end_o + i * 2 + 2])[0]
            s = struct.unpack(">H", buf[start_o + i * 2:start_o + i * 2 + 2])[0]
            if s <= e and s != 0xFFFF:
                cps.update(range(s, e + 1))
    elif fmt == 12:
        ng = struct.unpack(">I", buf[base + 12:base + 16])[0]
        for i in range(ng):
            s, e, _g = struct.unpack(">III", buf[base + 16 + i * 12:base + 28 + i * 12])
            cps.update(range(s, e + 1))
    return chosen, cps


CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/Deng.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simfang.ttf",
    "C:/Windows/Fonts/simyou.ttf",
]


def main():
    print("%-16s %9s %8s %8s %9s" % ("字体", "总大小", "字形数", "常用汉字", "CJK基本区"))
    print("-" * 60)
    for p in CANDIDATES:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as f:
                tables = read_sfnt(f)
                chosen, cps = read_cmap_codepoints(f, *tables["cmap"])
                num_glyphs = 0
                if "maxp" in tables:
                    f.seek(tables["maxp"][0] + 4)
                    num_glyphs = struct.unpack(">H", f.read(2))[0]
            cjk = sum(1 for c in cps if 0x4E00 <= c <= 0x9FFF)
            common = sum(1 for c in cps if 0x4E00 <= c <= 0x9FA5)
            print("%-16s %8.1fMB %8d %8d %9d  (%s)" % (
                os.path.basename(p), os.path.getsize(p) / 1048576.0,
                num_glyphs, common, cjk, chosen))
        except Exception as exc:  # noqa: BLE001
            print("%-16s  读取失败: %s" % (os.path.basename(p), exc))


if __name__ == "__main__":
    main()
