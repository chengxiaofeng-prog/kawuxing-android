# -*- coding: utf-8 -*-
"""
字体子集化 —— 纯标准库实现，不依赖 fontTools。

用途：把本机的中文字体裁成"只含游戏用字"的小字体（体积从 9MB 降到 1MB 以内），
提交进仓库，这样云端打包不需要再从境外 CDN 下载字体 —— 那是之前最容易失败的一步。

做法：
  1. 解析 cmap，得到"码位 -> 字形ID"；
  2. 只保留用到的字形 ID，重建 glyf / loca / hmtx / cmap / maxp / head / hhea / hmtx 等表；
  3. 其它可选表（GSUB/GPOS/DSIG/kern…）全部丢弃 —— 麻将界面用不到，丢掉能省一大半体积。

输出是合法的 TrueType（glyf）字体，Kivy / FreeType 能正常加载。
注意：只支持 glyf 轮廓的 TrueType；CFF（.otf）字体不支持。
"""
import os
import struct
import sys

# ---------------------------------------------------------------- 表解析

def read_sfnt(f):
    f.seek(0)
    head = f.read(12)
    if head[:4] == b"ttcf":
        num_fonts = struct.unpack(">I", head[8:12])[0]
        offsets = [struct.unpack(">I", f.read(4))[0] for _ in range(num_fonts)]
        f.seek(offsets[0])
        head = f.read(12)
    sfnt_version, num_tables = struct.unpack(">IH", head[:6])
    tables = {}
    order = []
    for _ in range(num_tables):
        tag, _cks, off, ln = struct.unpack(">4sIII", f.read(16))
        name = tag.decode("latin1")
        tables[name] = (off, ln)
        order.append(name)
    return sfnt_version, tables


def load_cmap(f, off, ln):
    """返回 {码位: 字形ID}，只取一个可用的 Unicode 子表。"""
    f.seek(off)
    # 老中易字体（SimHei/SimSun 等）的 cmap 头里 length 字段常常没把
    # glyphIdArray 算进去，按声明长度读会把 glyphIdArray 截掉。
    # 多读 64KB 兜底（后面是别的表的数据，多读无害，解析按逻辑结构走）。
    buf = f.read(ln + 65536)
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
    base = subs[0][2]
    fmt = struct.unpack(">H", buf[base:base + 2])[0]
    m = {}
    if fmt == 4:
        seg_x2 = struct.unpack(">H", buf[base + 6:base + 8])[0]
        seg = seg_x2 // 2
        end_o = base + 14
        start_o = end_o + seg_x2 + 2      # +2 是 endCode 与 startCode 之间的 reservedPad
        delta_o = start_o + seg_x2        # 注意：这里没有 pad！
        range_o = delta_o + seg_x2
        for i in range(seg):
            if range_o + i * 2 + 2 > len(buf):
                # cmap 表被裁短 / 结构异常，剩下的段直接放弃
                break
            e = struct.unpack(">H", buf[end_o + i * 2:end_o + i * 2 + 2])[0]
            s = struct.unpack(">H", buf[start_o + i * 2:start_o + i * 2 + 2])[0]
            delta = struct.unpack(">h", buf[delta_o + i * 2:delta_o + i * 2 + 2])[0]
            ro = struct.unpack(">H", buf[range_o + i * 2:range_o + i * 2 + 2])[0]
            if s > e or s == 0xFFFF:
                continue
            for c in range(s, e + 1):
                if ro == 0:
                    g = (c + delta) & 0xFFFF
                else:
                    gi = range_o + i * 2 + ro + (c - s) * 2
                    if gi + 2 > len(buf):
                        continue
                    g = struct.unpack(">H", buf[gi:gi + 2])[0]
                    if g:
                        g = (g + delta) & 0xFFFF
                if g:
                    m[c] = g
    elif fmt == 12:
        ng = struct.unpack(">I", buf[base + 12:base + 16])[0]
        for i in range(ng):
            s, e, g = struct.unpack(">III", buf[base + 16 + i * 12:base + 28 + i * 12])
            for k, c in enumerate(range(s, e + 1)):
                m[c] = g + k
    return m


def read_loca(f, tables, num_glyphs):
    off, ln = tables["loca"]
    f.seek(off)
    raw = f.read(ln)
    head_off = tables["head"][0]
    f.seek(head_off + 50)
    index_to_loc_format = struct.unpack(">h", f.read(2))[0]
    loca = []
    if index_to_loc_format == 0:
        for i in range(num_glyphs + 1):
            loca.append(struct.unpack(">H", raw[i * 2:i * 2 + 2])[0] * 2)
    else:
        for i in range(num_glyphs + 1):
            loca.append(struct.unpack(">I", raw[i * 4:i * 4 + 4])[0])
    return loca, index_to_loc_format


# ---------------------------------------------------------------- 表构造

def build_loca(offsets, long_format):
    out = bytearray()
    for o in offsets:
        out += struct.pack(">I", o) if long_format else struct.pack(">H", o // 2)
    return bytes(out)


def checksum(data, pad=True):
    if pad and len(data) % 4:
        data = data + b"\0" * (4 - len(data) % 4)
    s = 0
    for i in range(0, len(data), 4):
        s = (s + struct.unpack(">I", data[i:i + 4])[0]) & 0xFFFFFFFF
    return s


def build_cmap_format4(pairs):
    """pairs: 已按码位排序的 [(code, gid)]，用简单段构建 format 4。"""
    # 连续且 gid 递增的码位合成一段
    segs = []
    for code, gid in pairs:
        if segs:
            pc, pg, cnt = segs[-1]
            if code == pc + cnt and gid == pg + cnt:
                segs[-1] = (pc, pg, cnt + 1)
                continue
        segs.append((code, gid, 1))

    seg_count = len(segs) + 1        # 末尾加 0xFFFF 段
    end_codes = [s[0] + s[2] - 1 for s in segs] + [0xFFFF]
    start_codes = [s[0] for s in segs] + [0xFFFF]
    id_deltas, id_range_offsets, glyph_ids = [], [], []
    for code, gid, cnt in segs:
        delta = (gid - code) & 0xFFFF
        # 若同段内 gid 与 code 偏移一致，可用 delta；否则必须用 glyphIdArray
        if all(((code + i) + delta) & 0xFFFF == gid + i for i in range(cnt)):
            id_deltas.append(delta)
            id_range_offsets.append(0)
        else:
            off = 2 * len(glyph_ids) + 2      # +2 因为先跳过一个 dummy 项
            id_range_offsets.append(off)
            id_deltas.append(0)
            glyph_ids.append(0)
            for i in range(cnt):
                glyph_ids.append(gid + i)
    id_deltas.append(1)
    id_range_offsets.append(0)

    seg_x2 = seg_count * 2
    length = 16 + seg_x2 * 4 + len(glyph_ids) * 2
    buf = bytearray()
    buf += struct.pack(">HHHHHHH", 4, length, 0, seg_x2, 0, 0, 0)
    # 实际上 format4 头是 format(2) length(2) language(2) segCountX2(2) searchRange(2) entrySelector(2) rangeShift(2)
    buf = bytearray(struct.pack(">HHHHHHH", 4, length, 0, seg_x2, 2 * (2 ** (seg_count.bit_length() - 1)), seg_count.bit_length() - 1, seg_x2 - 2 * (2 ** (seg_count.bit_length() - 1))))
    for v in end_codes:
        buf += struct.pack(">H", v)
    buf += struct.pack(">H", 0)
    for v in start_codes:
        buf += struct.pack(">H", v)
    for v in id_deltas:
        buf += struct.pack(">H", v)
    for v in id_range_offsets:
        buf += struct.pack(">H", v)
    for v in glyph_ids:
        buf += struct.pack(">H", v)
    assert len(buf) == length, (len(buf), length)
    return bytes(buf)


def build_sfnt(sfnt_version, new_tables):
    """new_tables: {tag: bytes}，已算好各表数据。返回完整字体文件字节。"""
    tags = sorted(new_tables.keys())
    num = len(tags)
    entry_selector = max(0, num.bit_length() - 1)
    search_range = 16 * (2 ** entry_selector)
    header = struct.pack(">IHHHH", sfnt_version, num, search_range, entry_selector, num * 16 - search_range)

    offset = 12 + num * 16
    dir_records = bytearray()
    payload = bytearray()
    for tag in tags:
        data = new_tables[tag]
        padded = data + b"\0" * ((4 - len(data) % 4) % 4)
        dir_records += struct.pack(">4sIII", tag.encode("latin1"), checksum(data), offset, len(data))
        payload += padded
        offset += len(padded)
    return bytes(header + dir_records + payload)


# ---------------------------------------------------------------- 主流程

def subset(src_path, chars, dst_path):
    with open(src_path, "rb") as f:
        sfnt_version, tables = read_sfnt(f)

        if "glyf" not in tables:
            raise SystemExit("源字体不是 glyf 轮廓（可能是 CFF/OTF），本脚本不支持：%s" % src_path)

        # maxp / 字形总数
        f.seek(tables["maxp"][0])
        maxp_data = bytearray(f.read(tables["maxp"][1]))
        num_glyphs = struct.unpack(">H", maxp_data[4:6])[0]

        cmap_map = load_cmap(f, *tables["cmap"])
        loca, long_format = read_loca(f, tables, num_glyphs)

        glyf_off, _glyf_len = tables["glyf"]
        hmtx_off, hmtx_len = tables["hmtx"]
        hhea_off = tables["hhea"][0]
        f.seek(hhea_off + 34)
        num_h_metrics = struct.unpack(">H", f.read(2))[0]

        f.seek(hmtx_off)
        hmtx_raw = f.read(hmtx_len)

        def advance(gid):
            if gid < num_h_metrics:
                return struct.unpack(">H", hmtx_raw[gid * 4:gid * 4 + 2])[0], \
                       struct.unpack(">h", hmtx_raw[gid * 4 + 2:gid * 4 + 4])[0]
            return struct.unpack(">H", hmtx_raw[(num_h_metrics - 1) * 4:(num_h_metrics - 1) * 4 + 2])[0], 0

        # 需要的字形：0(.notdef) + 命中的字形
        wanted = {0}
        pairs = []
        for ch in sorted(set(chars)):
            gid = cmap_map.get(ord(ch))
            if gid:
                wanted.add(gid)
                pairs.append((ord(ch), gid))

        # 重新编号（保持 0 -> 0）
        ordered = sorted(wanted)
        remap = {old: new for new, old in enumerate(ordered)}
        pairs = [(c, remap[g]) for c, g in pairs]
        pairs.sort()

        # glyf + loca
        new_glyf = bytearray()
        new_loca = [0]

        def rewrite_composites(chunk, remap):
            """复合字形里的 component glyphIndex 要跟着新编号改写。"""
            out = bytearray(chunk)
            pos = 10  # 跳过 numberOfContours(2) xMin(2) yMin(2) xMax(2)
            if len(out) < 10:
                return bytes(out)
            nc = struct.unpack(">h", out[0:2])[0]
            if nc >= 0:
                return bytes(out)          # 简单字形，无需处理
            while pos + 4 <= len(out):
                flags = struct.unpack(">H", out[pos:pos + 2])[0]
                gidx = struct.unpack(">H", out[pos + 2:pos + 4])[0]
                new_g = remap.get(gidx, 0)
                struct.pack_into(">H", out, pos + 2, new_g)
                pos += 4
                if flags & 0x0001:          # ARG_1_AND_2_ARE_WORDS
                    pos += 4
                else:
                    pos += 2
                if flags & 0x0008:          # WE_HAVE_A_SCALE
                    pos += 2
                elif flags & 0x0040:        # X_AND_Y_SCALE
                    pos += 4
                elif flags & 0x0080:        # 2x2 MATRIX
                    pos += 8
                if flags & 0x0020:          # MORE_COMPONENTS
                    continue
                if flags & 0x0100:          # WE_HAVE_INSTRUCTIONS
                    pos += 2                # numInstructions 先跳过（后面统一处理）
                break
            return bytes(out)

        for old in ordered:
            if old + 1 < len(loca):
                start, end = loca[old], loca[old + 1]
            else:
                start = end = loca[-1]
            chunk = b""
            if end > start:
                f.seek(glyf_off + start)
                chunk = f.read(end - start)
                chunk = rewrite_composites(chunk, remap)
            new_glyf += chunk
            if len(new_glyf) % 4:
                new_glyf += b"\0" * (4 - len(new_glyf) % 4)
            new_loca.append(len(new_glyf))

        n_new = len(ordered)
        # 新的 maxp
        new_maxp = bytearray(maxp_data)
        struct.pack_into(">H", new_maxp, 4, n_new)

        # 新的 hmtx：先算出有多少个"尾随"字形可以走压缩
        metrics = [advance(g) for g in ordered]
        new_hmtx = bytearray()
        last_aw = None
        for aw, lsb in metrics:
            new_hmtx += struct.pack(">Hh", aw, lsb)
            last_aw = aw
        # 简化：全部写成完整记录（Kivy 不在意这几十字节）

        # 新的 hhea：numberOfHMetrics 改为等于字形数
        f.seek(hhea_off)
        hhea_data = bytearray(f.read(tables["hhea"][1]))
        struct.pack_into(">H", hhea_data, 34, n_new)

        # 新的 head：indexToLocFormat 统一改成长格式（省心，体积只多 2 字节/字形）
        f.seek(tables["head"][0])
        head_data = bytearray(f.read(tables["head"][1]))
        struct.pack_into(">h", head_data, 50, 1)
        struct.pack_into(">I", head_data, 8, 0)      # checkSumAdjustment 先置 0

        new_tables = {
            "head": bytes(head_data),
            "hhea": bytes(hhea_data),
            "maxp": bytes(new_maxp),
            "hmtx": bytes(new_hmtx),
            "loca": build_loca(new_loca, True),
            "glyf": bytes(new_glyf),
            "cmap": build_cmap_table(pairs),
        }
        # 保留有用的可选表
        for tag in ("name", "OS/2", "post"):
            if tag in tables:
                f.seek(tables[tag][0])
                data = bytearray(f.read(tables[tag][1]))
                if tag == "post":
                    # post 表 format 2 会带一大堆字形名，改成 format 3（无名字）
                    data = bytearray(data[:32])
                    struct.pack_into(">I", data, 0, 0x00030000)
                new_tables[tag] = bytes(data)

    out = build_sfnt(sfnt_version, new_tables)
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    with open(dst_path, "wb") as w:
        w.write(out)
    return len(pairs), n_new, len(out)


def build_cmap_table(pairs):
    """构造只有一个 (3,1) format4 子表的 cmap。"""
    sub = build_cmap_format4(pairs)
    # cmap 头：version=0, numTables=1，然后一条 encoding record
    # 平台 3 / 编码 1（Windows BMP），偏移 = 4 + 8 = 12
    header = struct.pack(">HHHHI", 0, 1, 3, 1, 12)
    return header + sub


def main():
    if len(sys.argv) < 4:
        print("用法: python subset_font.py <源字体.ttf> <字符集文件.txt> <输出.ttf>")
        return 1
    src, charset_file, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(charset_file, encoding="utf-8") as f:
        chars = f.read()
    n_hit, n_glyph, size = subset(src, chars, dst)
    print("命中字符 %d 个，子集字形 %d 个，输出 %.2f MB -> %s"
          % (n_hit, n_glyph, size / 1048576.0, dst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
