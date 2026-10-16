# -*- coding: utf-8 -*-
"""
卡五星 —— 安卓触屏版（Kivy）。

规则引擎与桌面版 / Unity 版完全同源（kawuxing/rules.py + engine.py），
本文件只负责触屏界面与整局流程驱动：

    发牌 → 摸牌 → 自身动作（自摸 / 暗杠 / 补杠）→ 出牌 → 他家响应 → 循环 → 结算

规则要点（与用户确认过的口径一致）：
    · 抢杠只限补杠（加杠），暗杠 / 明杠不可抢；
    · 亮倒者可点炮胡（含屁胡），未亮倒者屁胡只能自摸；
    · 杠后照样能听牌 / 亮倒（按结构位 3*副露 + 手牌数判断）；
    · 杠上炮只算杠后补摸打出的第一张。

触屏操作：
    · 点手牌 = 选中（同时显示听牌推演）；再点一下同一张 = 打出；
    · 胡 / 杠 / 碰 / 过 / 亮倒 / 托管 / 继续下一局 都是屏幕按钮；
    · 右上角「重开」随时重开一局。
"""

import datetime
import os
import random
import sys
import time


def _redirect_output_to_file():
    """
    把 stdout / stderr 重定向到「手机上能直接打开的位置」。

    安卓上如果启动阶段就抛异常，进程会立即退出，屏幕上什么都看不到
    （表现就是"一打开就闪退"）。重定向之后，崩溃时的 traceback 会落到
    文件里，便于排查。正常游戏不受影响。

    用 os.dup2 换的是文件描述符本身，所以连 Kivy / SDL 这些 C 层
    直接写 fd 2 的输出也能一并捕获。
    """
    candidates = [
        "/storage/emulated/0/Android/data/org.kawuxing/files/boot.log",
        "/sdcard/Android/data/org.kawuxing/files/boot.log",
        "/storage/emulated/0/Download/kawuxing_boot.log",
        "/sdcard/kawuxing_boot.log",
    ]
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here:
            candidates.append(os.path.join(here, "boot.log"))
    except Exception:
        pass
    for path in candidates:
        try:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            os.close(fd)
            return path
        except Exception:
            continue
    return None


_BOOT_LOG = _redirect_output_to_file()
print("=== KaWuXing boot %s ===" % datetime.datetime.now())
print("python  :", sys.version.replace("\n", " "))
print("platform:", sys.platform)
print("log file:", _BOOT_LOG)
try:
    sys.stdout.flush()
except Exception:
    pass

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.widget import Widget

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kawuxing.rules import (                       # noqa: E402
    KIND_COUNT, HONOR_START, ZHONG, FA, BAI,
    MeldType, ClaimType, ClaimOption, RuleConfig, tile_name,
    winning_tiles, is_ting, is_number, rank_of, suit_of,
)
from kawuxing.engine import GameEngine, SimpleAi, SEAT_COUNT   # noqa: E402

HUMAN = 0
SEAT_LABEL = {0: "你", 1: "左家", 2: "右家"}

_PENDING = object()          # 「等待玩家选择」的哨兵值

# ---------------------------------------------------------------- 配色
FELT = (0.06, 0.24, 0.15, 1)
FELT_DARK = (0.045, 0.185, 0.115, 1)
PANEL = (0.10, 0.22, 0.17, 1)
FACE = (0.973, 0.953, 0.906, 1)          # 牌面米白
FACE_EDGE = (0.55, 0.50, 0.36, 1)
BACK = (0.16, 0.17, 0.46, 1)             # 牌背蓝紫
BACK_EDGE = (0.42, 0.44, 0.85, 1)
GOLD = (0.90, 0.74, 0.25, 1)
WHITE = (1, 1, 1, 1)
INK = (0.13, 0.13, 0.15, 1)
RED = (0.78, 0.12, 0.10, 1)
GREEN = (0.10, 0.46, 0.18, 1)
BLUE = (0.10, 0.24, 0.62, 1)
SEL = (1.0, 0.82, 0.25, 1)
BTN = (0.16, 0.34, 0.27, 1)
BTN_EDGE = (0.45, 0.62, 0.50, 1)
DIM = (0.78, 0.82, 0.78, 1)
HU_RED = (0.62, 0.10, 0.08, 1)

# ---------------------------------------------------------------- 外部资源
# 与桌面版同源：textures/ 下的 JPG 替换「牌面图案 / 牌背 / 桌面」，缺哪个文件
# 就回退到程序内画的图案；sounds/ 下的 WAV 为出牌/碰/杠/胡音效，缺了就静音。
_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures")
_SND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

FACE_FILES = {}                       # tile 索引 -> 文件名（不含扩展名）
for _i in range(9):
    FACE_FILES[_i] = "tong%d" % (_i + 1)
for _i in range(9):
    FACE_FILES[9 + _i] = "tiao%d" % (_i + 1)
FACE_FILES[18] = "zhong"
FACE_FILES[19] = "fa"
FACE_FILES[20] = "bai"

_tex_cache = {}                       # name -> CoreImage 或 None（None 也缓存）


def load_tex(name):
    """加载 textures/<name>.jpg；缺失/损坏返回 None。首次绘制时懒加载。"""
    if name in _tex_cache:
        return _tex_cache[name]
    path = os.path.join(_TEX_DIR, name + ".jpg")
    img = None
    if os.path.exists(path):
        try:
            img = CoreImage(path)
        except Exception:
            img = None
    _tex_cache[name] = img
    return img


_sounds = {}                          # name -> Sound 或 None
_last_sfx = {}


def _init_sounds():
    """App.build() 时调用一次：把 sounds/ 下的 WAV 装进 SDL2_mixer。"""
    for name in ("discard", "peng", "gang", "hu"):
        path = os.path.join(_SND_DIR, name + ".wav")
        s = None
        if os.path.exists(path):
            try:
                s = SoundLoader.load(path)
            except Exception:
                s = None
        _sounds[name] = s


def sfx(name):
    """异步播放音效；同一音效 50ms 内不重复触发（防连点爆音）。"""
    s = _sounds.get(name)
    if s is None:
        return
    now = time.time()
    if now - _last_sfx.get(name, 0.0) < 0.05:
        return
    _last_sfx[name] = now
    try:
        s.play()
    except Exception:
        pass


_FONT = None


def _find_font():
    """
    找中文字体（安卓默认字体没有汉字，必须打包一个）：
    1. APK 里的 fonts/NotoSansSC-Regular.otf —— 由 GitHub Actions 云打包时
       自动下载（OFL 开源许可，可自由分发），本地仓库不用提交大字体文件；
    2. Windows 本机字体（仅电脑上预览调试用）。
    都没有就退回系统默认字体 —— 牌面是图形绘制的不受影响，只有文字可能缺字。
    """
    global _FONT
    if _FONT is not None:
        return _FONT
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("fonts/NotoSansSC-Regular.otf", "fonts/NotoSansSC-Regular.ttf"):
        p = os.path.join(here, name)
        if os.path.exists(p):
            _FONT = p
            return p
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        if os.path.exists(p):
            _FONT = p
            return p
    _FONT = ""
    return _FONT


def F(size):
    """返回带字体名的 CoreLabel 参数字典。"""
    f = _find_font()
    return {"font_name": f} if f else {}


_text_cache = {}


def text_tex(txt, size, color):
    key = (txt, int(size), tuple(color))
    tex = _text_cache.get(key)
    if tex is None:
        lbl = CoreLabel(text=txt, font_size=int(size), color=color, **F(int(size)))
        lbl.refresh()
        tex = lbl.texture
        _text_cache[key] = tex
        if len(_text_cache) > 800:
            _text_cache.clear()
    return tex


def draw_text(cv, cx, cy, txt, size, color, anchor="c"):
    tex = text_tex(txt, size, color)
    if not tex:
        return
    if anchor == "c":
        x, y = cx - tex.width / 2.0, cy - tex.height / 2.0
    elif anchor == "l":
        x, y = cx, cy - tex.height / 2.0
    else:
        x, y = cx - tex.width, cy - tex.height / 2.0
    cv.canvas.add(Color(1, 1, 1, 1))
    cv.canvas.add(Rectangle(texture=tex, pos=(x, y), size=(tex.width, tex.height)))


# 筒牌圆点排布（归一化坐标，0..1）
_DOTS = {
    1: [(0.5, 0.5)],
    2: [(0.5, 0.26), (0.5, 0.74)],
    3: [(0.24, 0.22), (0.5, 0.5), (0.76, 0.78)],
    4: [(0.28, 0.26), (0.72, 0.26), (0.28, 0.74), (0.72, 0.74)],
    5: [(0.28, 0.24), (0.72, 0.24), (0.5, 0.5), (0.28, 0.76), (0.72, 0.76)],
    6: [(0.3, 0.22), (0.7, 0.22), (0.3, 0.5), (0.7, 0.5), (0.3, 0.78), (0.7, 0.78)],
    7: [(0.22, 0.16), (0.5, 0.16), (0.78, 0.16),
        (0.3, 0.5), (0.7, 0.5), (0.3, 0.8), (0.7, 0.8)],
    8: [(0.3, 0.16), (0.7, 0.16), (0.3, 0.39), (0.7, 0.39),
        (0.3, 0.61), (0.7, 0.61), (0.3, 0.84), (0.7, 0.84)],
    9: [(0.22, 0.16), (0.5, 0.16), (0.78, 0.16),
        (0.22, 0.5), (0.5, 0.5), (0.78, 0.5),
        (0.22, 0.84), (0.5, 0.84), (0.78, 0.84)],
}

_HONOR_COLOR = {ZHONG: RED, FA: GREEN, BAI: BLUE}
_HONOR_TEXT = {ZHONG: "中", FA: "发", BAI: "白"}


def draw_tile(cv, x, y, w, h, tile, back=False, selected=False, dim=False):
    """画一张牌（x,y = 左下角）。textures/ 里有对应 JPG 就贴图，否则程序画。"""
    col = BACK if back else FACE
    edge = BACK_EDGE if back else FACE_EDGE
    if dim:
        col = (col[0] * 0.75, col[1] * 0.75, col[2] * 0.75, 1)
    cv.canvas.add(Color(*col))
    cv.canvas.add(Rectangle(pos=(x, y), size=(w, h)))

    # 外部贴图层（整张贴进牌面，白坯色块兜底；JPG 的直角由下面的圆角线收边）
    tex = None
    if back:
        tex = load_tex("tile_back")
    else:
        name = FACE_FILES.get(tile)
        tex = load_tex(name) if name else None
    if tex is not None:
        cv.canvas.add(Rectangle(texture=tex.texture, pos=(x, y), size=(w, h)))

    cv.canvas.add(Color(*edge))
    cv.canvas.add(Line(rounded_rectangle=(x + 0.5, y + 0.5, w - 1, h - 1, 6),
                       width=1.4))
    if selected:
        cv.canvas.add(Color(*SEL))
        cv.canvas.add(Line(rounded_rectangle=(x - 1, y - 1, w + 2, h + 2, 7),
                           width=2.6))
    if back:
        if tex is None:
            # 无贴图时才程序画：牌背中央的竹纹小方块
            cv.canvas.add(Color(0.30, 0.32, 0.72, 1))
            bw, bh = w * 0.52, h * 0.40
            bx, by = x + (w - bw) / 2.0, y + (h - bh) / 2.0
            cv.canvas.add(Line(rounded_rectangle=(bx, by, bw, bh, 4), width=1.2))
        return
    if tex is not None:
        return                       # 已有外部贴图，跳过程序内图案绘制
    if not (0 <= tile < KIND_COUNT):
        return
    suit = suit_of(tile)
    pad_x, pad_y = w * 0.10, h * 0.09
    bw, bh = w - 2 * pad_x, h - 2 * pad_y
    if suit == 2:
        draw_text(cv, x + w / 2.0, y + h / 2.0,
                  _HONOR_TEXT[tile], h * 0.52, _HONOR_COLOR[tile])
        return
    if suit == 0:
        r = rank_of(tile)
        rad = min(bw, bh) * (0.34 if r == 1 else (0.15 if r >= 7 else 0.17))
        for nx, ny in _DOTS[r]:
            cx, cy = x + pad_x + nx * bw, y + pad_y + ny * bh
            cv.canvas.add(Color(0.16, 0.36, 0.65, 1))
            cv.canvas.add(Ellipse(pos=(cx - rad, cy - rad), size=(rad * 2, rad * 2)))
            cv.canvas.add(Color(0.10, 0.24, 0.48, 1))
            cv.canvas.add(Line(circle=(cx, cy, rad), width=1.2))
        if r == 1:   # 一筒：点里再套一圈，像「饼」
            cx, cy = x + pad_x + 0.5 * bw, y + pad_y + 0.5 * bh
            cv.canvas.add(Color(0.10, 0.24, 0.48, 1))
            cv.canvas.add(Line(circle=(cx, cy, rad * 0.45), width=1.2))
    else:
        r = rank_of(tile)
        bars = []
        if r <= 3:
            for i in range(r):
                bars.append((0.5 - (r - 1) * 0.22 + i * 0.44, 0.5))
        else:
            # 上排 3 根 + 下排均分剩下的
            for i in range(3):
                bars.append((0.25 + i * 0.25, 0.72))
            rem = r - 3
            for i in range(rem):
                nx = 0.5 if rem == 1 else 0.25 + i * (0.5 / (rem - 1))
                bars.append((nx, 0.3))
        barmax = bh * 0.42 if r > 3 else bh * 0.6
        bwid = bw * 0.13
        for nx, ny in bars[:9]:
            cx, cy = x + pad_x + nx * bw, y + pad_y + ny * bh
            hh = min(barmax, bh * 0.52)
            cv.canvas.add(Color(*GREEN))
            cv.canvas.add(Rectangle(pos=(cx - bwid / 2.0, cy - hh / 2.0),
                                    size=(bwid, hh)))
            cv.canvas.add(Color(0.06, 0.30, 0.11, 1))
            cv.canvas.add(Line(rectangle=(cx - bwid / 2.0, cy - hh / 2.0, bwid, hh),
                               width=1.0))


def rounded_btn(cv, x, y, w, h, label, size=22, fill=BTN, edge=BTN_EDGE,
                fg=WHITE):
    cv.canvas.add(Color(*fill))
    cv.canvas.add(Rectangle(pos=(x, y), size=(w, h)))
    cv.canvas.add(Color(*edge))
    cv.canvas.add(Line(rounded_rectangle=(x, y, w, h, 10), width=1.8))
    draw_text(cv, x + w / 2.0, y + h / 2.0, label, size, fg)


def structural_slots(p):
    """结构位：杠 4 张物理牌只占 3 位（桌面版教训：别用物理张数算）。"""
    return len(p.hand) + 3 * len(p.melds)


class Board(Widget):
    """整个牌桌：单 Widget 自绘 + 触摸命中检测（与桌面版同思路）。"""

    def __init__(self, app, **kw):
        super(Board, self).__init__(**kw)
        self.app = app
        self.hand_rects = []       # (x, y, w, h, tile, index)
        self.buttons = []          # (x, y, w, h, label, value)
        self._down_pos = None
        bind = lambda _l, _v: Clock.schedule_once(lambda _dt: self.redraw(), 0)
        Window.bind(size=bind)

    # ----------------------------------------------------------------
    # 布局参数
    # ----------------------------------------------------------------

    def _metrics(self):
        W, H = self.width, self.height
        k = min(W / 1280.0, H / 720.0) * 1.05
        return W, H, k

    # ----------------------------------------------------------------
    # 绘制
    # ----------------------------------------------------------------

    def redraw(self, *_a):
        self.canvas.clear()
        self.hand_rects = []
        self.buttons = []
        app = self.app
        if not app.started:
            self._draw_title()
            return
        W, H, k = self._metrics()
        cv = self
        timg = load_tex("table")
        if timg is not None:
            cv.canvas.add(Color(1, 1, 1, 1))
            cv.canvas.add(Rectangle(texture=timg.texture, pos=(0, 0), size=(W, H)))
        else:
            cv.canvas.add(Color(*FELT))
            cv.canvas.add(Rectangle(pos=(0, 0), size=(W, H)))
            cv.canvas.add(Color(*FELT_DARK))
            cv.canvas.add(Rectangle(pos=(0, H * 0.62), size=(W, H * 0.38)))

        self._draw_topbar(W, H, k)
        self._draw_opponents(W, H, k)
        self._draw_discards(W, H, k)
        self._draw_hand(W, H, k)
        self._draw_info(W, H, k)

    def _draw_title(self):
        W, H, k = self._metrics()
        timg = load_tex("table")
        if timg is not None:
            self.canvas.add(Color(1, 1, 1, 1))
            self.canvas.add(Rectangle(texture=timg.texture, pos=(0, 0), size=(W, H)))
        else:
            self.canvas.add(Color(*FELT))
            self.canvas.add(Rectangle(pos=(0, 0), size=(W, H)))
        draw_text(self, W / 2.0, H * 0.60, "卡五星", H * 0.16, GOLD)
        draw_text(self, W / 2.0, H * 0.44, "正在准备牌局 ……", H * 0.05, DIM)

    def _draw_topbar(self, W, H, k):
        app = self.app
        eng = app.engine
        draw_text(self, W * 0.5, H - 26 * k, app.message, 24 * k, GOLD)
        # 三家分数
        sc = "  ".join("%s %d" % (SEAT_LABEL[s], eng.players[s].score)
                       for s in range(SEAT_COUNT))
        draw_text(self, 16 * k, H - 26 * k, sc, 20 * k, DIM, anchor="l")
        # 牌墙 + 重开
        draw_text(self, W - 150 * k, H - 26 * k, "牌墙 %d 张" % len(eng.wall),
                  20 * k, DIM, anchor="l")
        bw, bh = 88 * k, 36 * k
        rounded_btn(self, W - bw - 10 * k, H - bh - 8 * k, bw, bh, "重开", 20 * k)
        self.buttons.append((W - bw - 10 * k, H - bh - 8 * k, bw, bh, "重开", "restart"))

    def _draw_opponents(self, W, H, k):
        eng = self.app.engine
        for seat in (1, 2):
            left = (seat == 1)
            p = eng.players[seat]
            x0 = (W * 0.03 if left else W * 0.60)
            y0 = H - 74 * k
            anchor = "l" if left else "r"
            tx = x0 if left else W - W * 0.03
            draw_text(self, tx, y0, "%s（庄）" % SEAT_LABEL[seat] if p.is_dealer
                      else SEAT_LABEL[seat], 20 * k, DIM, anchor=anchor)
            # 手牌牌背
            tw, th = 20 * k, 28 * k
            n = len(p.hand)
            row_w = n * (tw + 2 * k)
            bx = x0 if left else W - W * 0.03 - row_w
            for i in range(n):
                draw_tile(self, bx + i * (tw + 2 * k), y0 - 40 * k, tw, th,
                          0, back=True)
            # 副露
            my = y0 - 78 * k
            mw = 26 * k
            if left:
                mx = W * 0.03
            else:
                mx = W - W * 0.03
            for meld in p.melds:
                count = meld.tile_count if meld.type != MeldType.PENG else 3
                for i in range(count):
                    if left:
                        draw_tile(self, mx + i * (mw + 2 * k), my - 36 * k,
                                  mw, 36 * k, meld.tile)
                    else:
                        draw_tile(self, mx - (i + 1) * (mw + 2 * k),
                                  my - 36 * k, mw, 36 * k, meld.tile)
                if left:
                    mx += (mw + 2 * k) * count + 8 * k
                else:
                    mx -= (mw + 2 * k) * count + 8 * k
            if p.liang_dao and not eng.round_over:
                draw_text(self, tx, my - 8 * k, "已亮倒 ×2", 17 * k, GOLD,
                          anchor=anchor)
            if self.app.reveal_all and p.hand:
                txt = " ".join(tile_name(t) for t in p.hand)
                draw_text(self, tx, my - 60 * k, txt, 16 * k, DIM, anchor=anchor)

    def _draw_discards(self, W, H, k):
        """两家的弃牌：左家画在左列，右家画在右列。"""
        eng = self.app.engine
        tw, th = 30 * k, 42 * k
        cols = 3
        for seat in (1, 2):
            left = (seat == 1)
            d = eng.players[seat].discards
            per = 7
            for i, t in enumerate(d):
                row, col = divmod(i, per)
                if left:
                    x = W * 0.03 + col * (tw + 4 * k)
                else:
                    x = W - W * 0.03 - (col + 1) * (tw + 4 * k)
                y = H * 0.52 - row * (th + 5 * k)
                draw_tile(self, x, y, tw, th, t)
        # 刚打出的那张，牌河中央金框高亮
        if eng.last_discard_tile >= 0 and not eng.round_over:
            lw, lh = 44 * k, 62 * k
            lx, ly = W * 0.5 - lw / 2.0, H * 0.46
            draw_tile(self, lx, ly, lw, lh, eng.last_discard_tile)
            self.canvas.add(Color(*GOLD))
            self.canvas.add(Line(rounded_rectangle=(lx - 2, ly - 2, lw + 4, lh + 4, 6),
                                 width=2.2))

    def _draw_hand(self, W, H, k):
        app = self.app
        eng = app.engine
        p = eng.players[HUMAN]
        tw, th = 64 * k, 90 * k
        gap = 3 * k
        n = len(p.hand)
        if n == 0:
            return
        drawn = -1
        order = list(range(n))
        if app.human_drawn >= 0 and app.human_drawn in p.hand:
            drawn = p.hand.index(app.human_drawn)
            order = [i for i in range(n) if i != drawn] + [drawn]
        total = n * (tw + gap) + (14 * k if drawn >= 0 else 0)
        x = W * 0.5 - total / 2.0
        y = 12 * k
        for idx in order:
            is_drawn = (idx == drawn)
            sel = (idx == app.selected)
            xx = x
            yy = y + 16 * k if sel else y
            draw_tile(self, xx, yy, tw, th, p.hand[idx], selected=sel)
            self.hand_rects.append((xx, yy, tw, th, p.hand[idx], idx))
            x += tw + gap + (14 * k if is_drawn else 0)

    def _draw_info(self, W, H, k):
        app = self.app
        eng = app.engine
        p = eng.players[HUMAN]
        # 亮倒/托管提示
        tips = []
        if p.liang_dao:
            tips.append("已亮倒 ×2" + ("（托管中）" if app.human_auto else ""))
        if tips:
            draw_text(self, W * 0.5, 178 * k, "　".join(tips), 18 * k, GOLD)
        # 听牌推演面板
        if app.inspect is not None:
            self._draw_ting(W, H, k, app.inspect)
        # 底部按钮
        bx, by = W * 0.5, 118 * k
        bw, bh = 108 * k, 46 * k
        gap = 14 * k
        for label, value, fill in app.button_row():
            x = bx - bw / 2.0
            rounded_btn(self, x, by, bw, bh, label, 21 * k, fill=fill)
            self.buttons.append((x, by, bw, bh, label, value))
            bx += bw + gap

    def _draw_ting(self, W, H, k, tile):
        """选中某张时的推演：打出它听什么、各剩几张。"""
        app = self.app
        eng = app.engine
        p = eng.players[HUMAN]
        rest = list(p.hand)
        if tile in rest:
            rest.remove(tile)
        if not is_ting(rest, len(p.melds)):
            draw_text(self, W * 0.5, 205 * k,
                      "打 %s：不听牌" % tile_name(tile), 19 * k, DIM)
            return
        outs = eng.outs_left(HUMAN, rest, {tile: 1})
        parts = []
        for t in sorted(outs):
            n = outs[t]
            parts.append("%s 剩%d" % (tile_name(t), n) if n else
                         "%s 已绝张" % tile_name(t))
        draw_text(self, W * 0.5, 212 * k,
                  "打 %s 听：%s" % (tile_name(tile), "　".join(parts)),
                  18 * k, DIM)

    # ----------------------------------------------------------------
    # 触摸
    # ----------------------------------------------------------------

    def on_touch_down(self, touch):
        self._down_pos = (touch.x, touch.y)
        return True

    def on_touch_up(self, touch):
        if self._down_pos is None:
            return False
        self._down_pos = None
        if abs(touch.x - touch.px) > 40 or abs(touch.y - touch.py) > 40:
            return True                      # 滑动不算点击
        self.app.on_tap(touch.x, touch.y)
        return True


class KaWuXingApp(App):
    title = "KaWuXing"

    def build(self):
        _init_sounds()
        self.board = Board(self)
        self.started = False
        self.engine = None
        self.ai = None
        self._gen = None
        self._reset_state()
        Clock.schedule_once(lambda dt: self.start_game(), 0.3)
        return self.board

    # ----------------------------------------------------------------
    # 状态
    # ----------------------------------------------------------------

    def _reset_state(self):
        self.engine = None
        self.message = "卡五星"
        self.hint = ""
        self.human_drawn = -1
        self.selected = -1
        self.wait_discard = False
        self.pending_discard = -1
        self.pending_choice = None
        self.claim_options = []
        self.self_options = []
        self._claim_result = None
        self._self_pick = None
        self.inspect = None
        self.human_auto = False
        self.discard_override = None
        self.result = None
        self.reveal_all = False
        self.score_before = [0, 0, 0]
        self.dealer = 0
        self.round_index = 1
        self._rng = random.Random()

    def start_game(self, *_a):
        self._reset_state()
        self.engine = GameEngine(seed=self._rng.randrange(1 << 30))
        self.ai = {s: SimpleAi(seed=self._rng.randrange(1 << 30))
                   for s in range(SEAT_COUNT)}
        self.started = True
        self.board.redraw()
        self._run(self._game_loop())

    # ----------------------------------------------------------------
    # 协程驱动（生成器 + Clock，等价于桌面版的 root.after 泵）
    # ----------------------------------------------------------------

    def _run(self, gen):
        self._gen = gen
        Clock.schedule_once(self._advance, 0)

    def _advance(self, dt):
        gen = self._gen
        if gen is None:
            return
        self._gen = None
        try:
            delay = next(gen)
        except StopIteration:
            return
        except Exception:
            # 出错不让界面静默卡死：显示错误并停止（按「重开」可重开一局）
            import traceback
            traceback.print_exc()
            self._gen = None
            self.message = "程序出错（点「重开」重开一局）"
            self.board.redraw()
            return
        self._gen = gen
        Clock.schedule_once(self._advance, max(0.016, float(delay or 0)))

    def _game_loop(self):
        while True:
            yield from self._play_one_round()

    def button_row(self):
        """当前该显示哪些按钮。"""
        eng = self.engine
        if self.result is not None:
            return [("继续下一局", "next", (0.55, 0.42, 0.10, 1))]
        out = []
        if self.claim_options:
            for o in self.claim_options:
                label = {ClaimType.HU: "胡", ClaimType.GANG: "杠",
                         ClaimType.PENG: "碰"}.get(o.type, "?")
                fill = HU_RED if o.type == ClaimType.HU else BTN
                out.append((label, "claim:%s:%d:%d" % (o.type, o.tile, o.from_seat), fill))
            out.append(("过", "pass", (0.25, 0.25, 0.25, 1)))
            return out
        if self.self_options:
            for o in self.self_options:
                if o.type == ClaimType.HU:
                    out.append(("自摸胡", "selfhu", HU_RED))
                elif o.type == ClaimType.GANG:
                    gang_type = ("补杠" if self.engine.players[HUMAN]
                                 .find_peng_meld(o.tile) is not None else "暗杠")
                    out.append((gang_type, "selfgang:%d" % o.tile, BTN))
            out.append(("过", "pass", (0.25, 0.25, 0.25, 1)))
            return out
        p = eng.players[HUMAN]
        if not p.liang_dao and self._can_liang_dao():
            out.append(("亮倒", "liangdao", (0.35, 0.16, 0.42, 1)))
        if p.liang_dao:
            out.append(("取消托管" if self.human_auto else "托管",
                        "toggleauto", (0.30, 0.30, 0.34, 1)))
        return out

    # ----------------------------------------------------------------
    # 整局流程（移植自桌面版 ui.py）
    # ----------------------------------------------------------------

    def _play_one_round(self):
        eng = self.engine
        for s in range(SEAT_COUNT):
            eng.players[s].name = SEAT_LABEL[s]
        self.score_before = [q.score for q in eng.players]
        self.human_drawn = -1
        self.selected = -1
        self.inspect = None
        self.human_auto = False
        self.discard_override = None
        self.result = None
        self.reveal_all = False
        self.claim_options = []
        self.self_options = []
        self.wait_discard = False
        self.pending_choice = None

        eng.start_round(self.dealer, self.round_index)
        self.message = "第 %d 局 · %s 坐庄" % (self.round_index, SEAT_LABEL[self.dealer])
        self.board.redraw()
        yield 0.5

        yield from self._round_body()
        yield from self._settle()

    def _round_body(self):
        eng = self.engine
        seat = self.dealer
        need_draw = False
        gang_flag = False
        guard = 0
        first_turn = True

        while not eng.round_over and guard < 600:
            guard += 1
            if need_draw or first_turn:
                first_turn = False
                if need_draw:
                    drawn = eng.draw_for_seat(seat)
                    after_gang = gang_flag
                    gang_flag = False
                    if drawn < 0:
                        eng.declare_draw()
                        return
                    if seat == HUMAN:
                        self.human_drawn = drawn
                    self.message = "%s 摸牌" % SEAT_LABEL[seat]
                    self.board.redraw()
                    yield 0.25
                else:
                    after_gang = False
                hai_di = (len(eng.wall) == 0)

                inner = 0
                while inner < 12:
                    inner += 1
                    opts = eng.get_self_options(seat, after_gang, hai_di)
                    if not opts:
                        break
                    if self._is_auto(seat):
                        yield 0.35
                        pick = self.ai[seat].decide_self_action(eng, seat, opts)
                    else:
                        pick = yield from self._ask_human_self(opts)
                    if pick is None or pick.type == ClaimType.PASS:
                        break
                    if pick.type == ClaimType.HU:
                        eng.win_self_draw(seat, after_gang, hai_di)
                        sfx("hu")
                        self.message = "%s 自摸！" % SEAT_LABEL[seat]
                        self.board.redraw()
                        yield 0.4
                        return
                    if pick.type == ClaimType.GANG:
                        p = eng.players[seat]
                        if p.find_peng_meld(pick.tile) is not None:
                            # 只有补杠可被抢（暗杠/明杠不可抢）
                            robbers = eng.can_qiang_gang(seat, pick.tile,
                                                         MeldType.BU_GANG)
                            if robbers:
                                r = robbers[0]
                                if self._is_auto(r):
                                    agreed = True
                                else:
                                    agreed = yield from self._ask_human_qiang_gang(
                                        pick.tile, seat)
                                if agreed:
                                    eng.win_by_discard(r, pick.tile, seat, True, False)
                                    sfx("hu")
                                    self.message = "%s 抢杠胡 %s！" % (
                                        SEAT_LABEL[r], tile_name(pick.tile))
                                    self.board.redraw()
                                    yield 0.4
                                    return
                            if not eng.apply_bu_gang(seat, pick.tile):
                                break
                            sfx("gang")
                            self.message = "%s 补杠 %s" % (
                                SEAT_LABEL[seat], tile_name(pick.tile))
                        else:
                            eng.apply_an_gang(seat, pick.tile)
                            sfx("gang")
                            self.message = "%s 暗杠" % SEAT_LABEL[seat]
                        self.board.redraw()
                        yield 0.35
                        d2 = eng.draw_for_seat(seat)
                        if d2 < 0:
                            eng.declare_draw()
                            return
                        if seat == HUMAN:
                            self.human_drawn = d2
                        after_gang = True
                        hai_di = (len(eng.wall) == 0)
                        self.board.redraw()
                        yield 0.25
                        continue
                    break
                if eng.round_over:
                    return

            # ---- 出牌 ----
            if seat == HUMAN and self.discard_override is not None:
                tile = self.discard_override
                self.discard_override = None
            elif self._is_auto(seat):
                yield 0.4
                tile = self.ai[seat].choose_discard(eng, seat)
            else:
                tile = yield from self._ask_human_discard()

            if tile is None or tile < 0:
                eng.declare_draw()
                return
            eng.try_discard(seat, tile)
            sfx("discard")
            if seat == HUMAN:
                self.human_drawn = -1
                self.selected = -1
                self.inspect = None
            self.message = "%s 打出 %s" % (SEAT_LABEL[seat], tile_name(tile))
            self.board.redraw()
            yield 0.3

            # 杠上炮只认杠后补摸打出的第一张
            gang_shang_pao = (eng.last_action_was_gang and eng.last_gang_seat == seat)
            eng.clear_gang_mark()

            responders = []
            for kk in (1, 2):
                other = (seat + kk) % SEAT_COUNT
                opts = eng.get_claim_options(other, tile, seat, gang_shang_pao)
                if not opts:
                    continue
                if self._is_auto(other):
                    yield 0.3
                    pick = self.ai[other].decide_claim(
                        eng, other, self._auto_claim_options(other, opts))
                else:
                    pick = yield from self._ask_human_claim(other, tile, seat, opts)
                if pick is None or pick.type == ClaimType.PASS:
                    continue
                responders.append((kk, other, pick))

            if responders:
                prio = {ClaimType.HU: 0, ClaimType.GANG: 1, ClaimType.PENG: 2}
                responders.sort(key=lambda r: (prio.get(r[2].type, 9), r[0]))
                _, other, pick = responders[0]
                if pick.type == ClaimType.HU:
                    eng.win_by_discard(other, tile, seat, False, gang_shang_pao)
                    sfx("hu")
                    self.message = "%s 胡 %s！" % (SEAT_LABEL[other], tile_name(tile))
                    self.board.redraw()
                    yield 0.4
                    return
                if pick.type == ClaimType.GANG:
                    eng.apply_ming_gang(other, tile)
                    sfx("gang")
                    self.message = "%s 直杠 %s" % (SEAT_LABEL[other], tile_name(tile))
                    seat = other
                    need_draw = True
                else:
                    eng.apply_peng(other, tile)
                    sfx("peng")
                    self.message = "%s 碰 %s" % (SEAT_LABEL[other], tile_name(tile))
                    seat = other
                    need_draw = False
                self.board.redraw()
                yield 0.35
                continue

            seat = (seat + 1) % SEAT_COUNT
            need_draw = True

        if not eng.round_over:
            eng.declare_draw()

    # ----------------------------------------------------------------
    # 人机交互
    # ----------------------------------------------------------------

    def _is_auto(self, seat):
        return seat != HUMAN or self.engine.players[HUMAN].liang_dao and self.human_auto

    def _auto_claim_options(self, seat, opts):
        p = self.engine.players[seat]
        if not p.liang_dao:
            return opts
        return [o for o in opts if o.type != ClaimType.PENG]

    def _ask_human_self(self, opts):
        """摸牌后的自摸 / 暗杠 / 补杠选择，等待按钮回填 _self_pick。"""
        self.self_options = opts
        self._self_pick = _PENDING
        self.board.redraw()
        while self._self_pick is _PENDING:
            yield 0.05
        self.self_options = []
        pick = self._self_pick
        self._self_pick = None
        return pick

    def _ask_human_claim(self, seat, tile, from_seat, opts):
        """别人出牌后的响应选择，等待按钮回填 _claim_result。"""
        self.claim_options = opts
        self._claim_result = _PENDING
        self.message = "%s 打出 %s，你可以行动" % (SEAT_LABEL[from_seat],
                                               tile_name(tile))
        self.board.redraw()
        while self._claim_result is _PENDING:
            yield 0.05
        self.claim_options = []
        pick = self._claim_result
        self._claim_result = None
        return pick

    def _ask_human_qiang_gang(self, tile, ganger_seat):
        """问玩家要不要抢杠（只有补杠会走到这里）。"""
        eng = self.engine
        if not eng.can_hu_on_discard(HUMAN, tile, ganger_seat, False,
                                     qiang_gang=True):
            return False
        opt = ClaimOption(ClaimType.HU, HUMAN, tile, ganger_seat)
        opt.qiang_gang = True
        pick = yield from self._ask_human_claim(HUMAN, tile, ganger_seat, [opt])
        return bool(pick) and pick.type == ClaimType.HU

    def _ask_human_discard(self):
        self.wait_discard = True
        self.message = "轮到你了 · 点牌选中，再点一次打出"
        self.board.redraw()
        while self.wait_discard and self.pending_discard < 0:
            yield 0.05
        tile = self.pending_discard
        self.pending_discard = -1
        self.wait_discard = False
        return tile

    def _settle(self):
        eng = self.engine
        hu = eng.last_hu
        deltas = [eng.players[s].score - self.score_before[s]
                  for s in range(SEAT_COUNT)]
        if hu is not None:
            self.result = {
                "kind": "hu",
                "winner": hu.winner_seat,
                "type": hu.win_type_text,
                "tile": hu.win_tile,
                "fan": hu.score.fan_text,
                "mult": hu.score.multiplier,
                "deltas": deltas,
                "hand": list(hu.hand_snapshot),
            }
            self.dealer = hu.winner_seat
            self.reveal_all = True
            self.message = "%s %s %s" % (SEAT_LABEL[hu.winner_seat],
                                         hu.win_type_text, tile_name(hu.win_tile))
        else:
            self.result = {"kind": "draw", "deltas": deltas}
            self.message = "荒庄"
        self.selected = -1
        self.inspect = None
        self.board.redraw()
        self.pending_choice = None
        while self.pending_choice != "next":
            yield 0.05
        self.pending_choice = None
        self.result = None
        self.reveal_all = False
        self.round_index += 1

    # ----------------------------------------------------------------
    # 亮倒 / 听牌
    # ----------------------------------------------------------------

    def _can_liang_dao(self):
        eng = self.engine
        p = eng.players[HUMAN]
        if eng.round_over or p.liang_dao:
            return False
        slots = structural_slots(p)
        if slots == 13:
            return eng.is_ting(HUMAN)
        if slots == 14:
            return self._ting_keep_discard() >= 0
        return False

    def _ting_keep_discard(self):
        eng = self.engine
        p = eng.players[HUMAN]
        best, best_n = -1, -1
        for t in sorted(set(p.hand)):
            rest = list(p.hand)
            rest.remove(t)
            if not is_ting(rest, len(p.melds)):
                continue
            n = len(winning_tiles(rest, len(p.melds)))
            if n > best_n:
                best, best_n = t, n
        return best

    def do_liang_dao(self):
        eng = self.engine
        p = eng.players[HUMAN]
        if not self._can_liang_dao():
            return
        p.liang_dao = True
        self.human_auto = True
        if structural_slots(p) == 14:
            t = self._ting_keep_discard()
            if t >= 0:
                self.discard_override = t
        self.message = "你亮倒了（×2）· 机器自动打牌"
        self.board.redraw()

    # ----------------------------------------------------------------
    # 点击分发
    # ----------------------------------------------------------------

    def on_tap(self, x, y):
        b = self.board
        for (bx, byy, bw, bh, _label, value) in reversed(b.buttons):
            if bx <= x <= bx + bw and byy <= y <= byy + bh:
                self._on_button(value)
                return
        # 手牌
        for (hx, hy, hw, hh, tile, idx) in reversed(b.hand_rects):
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                self._on_hand_tap(idx, tile)
                return

    def _on_hand_tap(self, idx, tile):
        eng = self.engine
        p = eng.players[HUMAN]
        if self.result is not None or self.claim_options:
            return
        if p.liang_dao and not self.human_auto:
            pass
        if p.liang_dao:
            return                          # 亮倒后手牌锁死（托管由电脑打）
        if not self.wait_discard:
            # 没轮到出牌时点牌 = 只看推演
            self.inspect = tile if self.inspect != tile else None
            self.board.redraw()
            return
        if self.selected == idx:
            self.pending_discard = tile
            self.selected = -1
            self.inspect = None
        else:
            self.selected = idx
            self.inspect = tile
        self.board.redraw()

    def _on_button(self, value):
        eng = self.engine
        if value == "restart":
            self.pending_choice = None
            self.claim_options = []
            self.self_options = []
            self.wait_discard = False
            self.start_game()
            return
        if self.result is not None:
            if value == "next":
                self.pending_choice = "next"
            return
        if value == "toggleauto":
            p = eng.players[HUMAN]
            if p.liang_dao:
                self.human_auto = not self.human_auto
                self.message = "已开启托管" if self.human_auto else "已收回操作权"
            self.board.redraw()
            return
        if value == "liangdao":
            self.do_liang_dao()
            return
        if value == "pass":
            if self.self_options:
                self._self_pick = None          # 自身动作：过
            elif self.claim_options:
                self._claim_result = None       # 响应：过
            self.board.redraw()
            return
        if value.startswith("claim:"):
            parts = value.split(":")
            ctype, tile, from_seat = parts[1], int(parts[2]), int(parts[3])
            pick = None
            for o in self.claim_options:
                if o.type == ctype and o.tile == tile and o.from_seat == from_seat:
                    pick = o
                    break
            self._claim_result = pick
            self.board.redraw()
            return
        if value == "selfhu":
            self._self_pick = next((o for o in self.self_options
                                    if o.type == ClaimType.HU), None)
            return
        if value.startswith("selfgang:"):
            t = int(value.split(":")[1])
            self._self_pick = next((o for o in self.self_options
                                    if o.type == ClaimType.GANG and o.tile == t),
                                   None)
            return


if __name__ == "__main__":
    # 只在桌面调试时指定窗口尺寸；安卓上屏幕尺寸由设备决定，
    # 强制设置反而可能在部分机型上引发窗口初始化异常。
    try:
        from kivy.utils import platform as _kivy_platform
    except Exception:
        _kivy_platform = ""
    if _kivy_platform != "android":
        Window.size = (1280, 720)

    # 兜住启动期的任何异常：把 traceback 写进 boot.log（见文件顶部的重定向），
    # 而不是让进程静默退出 —— 否则手机上只能看到一个"闪退"。
    try:
        KaWuXingApp().run()
    except BaseException:
        import traceback
        traceback.print_exc()
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        raise
