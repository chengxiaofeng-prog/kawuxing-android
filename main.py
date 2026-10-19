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
import faulthandler
import os
import random
import sys
import time


_prev_tail = []          # 上一轮异常退出时留下的日志尾巴
_RUN_FLAG = "running.flag"


def _flag_path():
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), _RUN_FLAG)
    except Exception:
        return None


def _clear_run_flag():
    """正常退出时删掉标记 —— 它还在，就说明上一轮没走完（多半是原生崩溃）。"""
    p = _flag_path()
    if not p:
        return
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


# 判断"上一轮到底崩没崩"的关键字（faulthandler / SDL 的输出特征）
_CRASH_MARKERS = (
    "Fatal Python error", "Current thread", "Stack (most recent call first)",
    "SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE",
    "signal 11", "signal 6", "signal 7", "signal 4", "signal 8",
    "Backtrace", "backtrace",
)


def _redirect_output_to_file():
    """
    把 stdout / stderr 重定向到「用数据线连电脑后能直接打开的位置」。

    安卓上如果崩在原生层（GPU 驱动 / SDL），进程会立即退出，屏幕上什么都看不到
    （表现就是"一打开就闪退"）。重定向之后，崩溃时写往 fd 1/2 的内容
    （含 faulthandler 的信号栈、Kivy/SDL 的 C 层输出）都会落到文件里。

    路径用真实包名：package.domain = org.kawuxing, package.name = kawuxing
    → 应用包名是 org.kawuxing.kawuxing（写错包名的目录会被 Scoped Storage 拒绝）。
    Android/data/<包名>/files 不需要任何权限，且 MTP(数据线) 下电脑可见。
    """
    candidates = [
        # ★ 首选：Android/media/<包名>/ —— Android 11+ 起 data/ 目录被系统对
        #   文件管理器隐藏，但 media/ 不隐藏：手机自带的「文件管理」能直接看到，
        #   不用连电脑、不用 adb，直接把这个文件发出来即可。
        "/storage/emulated/0/Android/media/org.kawuxing.kawuxing/boot.log",
        "/sdcard/Android/media/org.kawuxing.kawuxing/boot.log",
        # 次选：应用自己的外部目录（数据线连电脑 / MTP 可见）
        "/storage/emulated/0/Android/data/org.kawuxing.kawuxing/files/boot.log",
        "/sdcard/Android/data/org.kawuxing.kawuxing/files/boot.log",
        "/storage/emulated/0/Android/data/org.kawuxing/files/boot.log",
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
            # ★ 上一轮若是异常退出（flag 还在），先把旧日志尾巴存下来 ——
            #   本轮会清空文件，之后再想读就没了。
            flag = _flag_path()
            if flag and os.path.exists(flag) and os.path.exists(path):
                try:
                    with open(path, "r", errors="replace") as f:
                        _prev_tail.extend(l.rstrip("\n")
                                          for l in f.readlines()[-120:])
                except Exception:
                    pass
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            os.close(fd)
            # 标记"本轮运行中"；正常退出时会在 App.on_stop 里删掉它。
            if flag:
                try:
                    with open(flag, "w") as f:
                        f.write("1")
                except Exception:
                    pass
            return path
        except Exception:
            continue
    return None


_BOOT_LOG = _redirect_output_to_file()
print("=== KaWuXing boot %s ===" % datetime.datetime.now())
print("python  :", sys.version.replace("\n", " "))
print("platform:", sys.platform)
print("log file:", _BOOT_LOG)

# ★ 关键：捕获原生层崩溃（SIGSEGV/SIGABRT/SIGBUS…）。
#   GPU 驱动（如部分 Adreno）崩掉时，Python 的 try/except 完全抓不到，
#   进程直接消失 —— 表现就是"一打开就闪退"。faulthandler 会在进程被信号
#   杀死前，把所有线程的 Python 调用栈写进 stderr（已被重定向到 boot.log），
#   于是即使没有电脑、没有 adb，也能知道崩在哪一行。
try:
    faulthandler.enable()          # 默认写 stderr -> 已 dup2 到 boot.log
except Exception:
    pass

try:
    sys.stdout.flush()
except Exception:
    pass


def _trace(msg):
    """分步追踪：崩溃时文件里最后一行就是"最后一个成功走完的步骤"。"""
    try:
        print("[T] %s" % msg)
        sys.stdout.flush()
    except Exception:
        pass


def _log_env_info():
    """
    把 GPU / 机型 / 安卓版本写进 boot.log。

    这一条是排查"某台设备才崩"的核心线索：GPU 驱动（尤其部分 Adreno）
    上 Kivy 的着色器会把驱动直接打崩，崩在 native 层，Python 抓不到 —— 
    只有 GL_VENDOR / GL_RENDERER 能证明机器用的是不是那类驱动。
    """
    info = []
    try:
        from kivy.core.window import Window
        info.append(("gl_backend", str(Window.gl_backend)))
    except Exception:
        pass
    try:
        from kivy.graphics import cgl            # Kivy 2.x：GL 函数入口
        get = getattr(cgl, "glGetString", None)
        if get is not None:
            for key, enum in (("GL_VENDOR", 0x1F00), ("GL_RENDERER", 0x1F01),
                              ("GL_VERSION", 0x1F02)):
                try:
                    v = get(enum)
                    if isinstance(v, bytes):
                        v = v.decode("utf-8", "replace")
                    info.append((key, str(v)))
                except Exception:
                    pass
    except Exception:
        pass
    try:
        from kivy.utils import platform as _kp
        info.append(("platform", str(_kp)))
        info.append(("sdk_version", str(sys.getandroidapilevel())
                     if hasattr(sys, "getandroidapilevel") else "-"))
    except Exception:
        pass
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build")
        info.append(("device", "%s %s" % (Build.MANUFACTURER, Build.MODEL)))
        info.append(("android", str(Build.VERSION.RELEASE)))
        info.append(("sdk_int", str(Build.VERSION.SDK_INT)))
        info.append(("cpu_abi", " ".join(Build.SUPPORTED_ABIS)))
    except Exception:
        pass
    if info:
        try:
            # 一行一个字段：报告页按行显示，长行不会被截断
            for k, v in info:
                print("[ENV] %s=%s" % (k, v))
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
from kawuxing.engine import (                      # noqa: E402
    GameEngine, SimpleAi, SEAT_COUNT,
    keeps_ting, ting_keep_discards,
)

HUMAN = 0
SEAT_LABEL = {0: "你", 1: "左家", 2: "右家"}
SEAT_COLOR = {0: (0.95, 0.50, 0.10, 1), 1: (0.15, 0.47, 0.95, 1),
              2: (0.70, 0.25, 0.85, 1)}   # 牌河描边：你 / 左家 / 右家

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

_tex_cache = {}                       # name -> CoreImage（成功才缓存）
_tex_fail = {}                        # name -> 上次失败的 monotonic 时间


def load_tex(name):
    """
    加载 textures/<name>.jpg；缺失/损坏返回 None。

    注意：App 刚启动、GL 上下文还没就绪的那零点几秒里，纹理加载可能
    瞬时失败 —— 失败不能永久缓存（否则这一局永远没贴图），隔 1.5 秒
    要允许重试；成功的照常缓存。
    """
    if name in _tex_cache:
        return _tex_cache[name]
    now = time.monotonic() if hasattr(time, "monotonic") else time.time()
    if now - _tex_fail.get(name, -9.0) < 1.5:
        return None                    # 刚失败过，先等等再重试
    path = os.path.join(_TEX_DIR, name + ".jpg")
    img = None
    if os.path.exists(path):
        try:
            img = CoreImage(path)
        except Exception:
            img = None
    if img is not None:
        _tex_cache[name] = img
    else:
        _tex_fail[name] = now
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


_tile_sounds = {}                     # tile -> Sound 或 None（第一次用到才加载）


def _play_tile_voice(tile):
    """播报一张牌的名字（「五筒」「红中」…）。"""
    s = _tile_sounds.get(tile, 0)
    if s == 0:                        # 还没加载过
        path = os.path.join(_SND_DIR, "tiles", "t%02d.wav" % tile)
        s = None
        if os.path.exists(path):
            try:
                s = SoundLoader.load(path)
            except Exception:
                s = None
        _tile_sounds[tile] = s
    if s is None:
        return
    try:
        s.stop()                      # 同一张牌连着打，从头再播
    except Exception:
        pass
    try:
        s.play()
    except Exception:
        pass


def say_tile(tile, delay=0.16):
    """报牌：稍微延后一点，让「木牌落桌」的响声先出来。"""
    if tile is None or tile < 0:
        return
    Clock.schedule_once(lambda dt: _play_tile_voice(tile), delay)


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
        _trace("redraw size=%.0fx%.0f started=%s" % (
            self.width, self.height, self.app.started))
        self.canvas.clear()
        self.hand_rects = []
        self.buttons = []
        app = self.app
        # ★ 上一轮是异常退出（原生崩溃）→ 直接摆出「崩溃现场」页，
        #   用户不用连电脑、不用 adb，拍张照就能把原因发出来。
        if getattr(app, "crash_report", None):
            self._draw_crash_report(app.crash_report)
            _trace("  crash-report ok")
            return
        if not app.started:
            self._draw_title()
            _trace("  title ok")
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

        _trace("  bg ok")
        self._draw_topbar(W, H, k)
        _trace("  topbar ok")
        self._draw_opponents(W, H, k)
        _trace("  opponents ok")
        self._draw_discards(W, H, k)
        _trace("  discards ok")
        self._draw_hand(W, H, k)
        _trace("  hand ok")
        self._draw_info(W, H, k)
        _trace("  info ok")

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

    def _draw_crash_report(self, lines):
        """
        「崩溃现场」页：上一次运行没走完（flag 还在），就把那份日志的末尾直接
        铺在屏幕上 —— 拍张照即可，不需要数据线、不需要 adb、不需要找文件。
        """
        W, H, k = self._metrics()
        self.canvas.add(Color(0.08, 0.09, 0.11, 1))
        self.canvas.add(Rectangle(pos=(0, 0), size=(W, H)))

        blob = "\n".join(lines)
        if any(m in blob for m in _CRASH_MARKERS):
            verdict, vcol = "★ 检测到原生崩溃信号（faulthandler 已抓到调用栈）", \
                (1.0, 0.45, 0.34, 1)
        elif "Traceback (most recent call last)" in blob:
            verdict, vcol = "★ 检测到 Python 异常（见下方 Traceback）", \
                (1.0, 0.72, 0.30, 1)
        else:
            verdict, vcol = "未检测到崩溃信号（也可能是被系统回收，可直接开始游戏）", DIM

        draw_text(self, W * 0.5, H - 30 * k, "上次运行没有正常结束", 27 * k,
                  (1.0, 0.45, 0.34, 1))
        draw_text(self, W * 0.5, H - 56 * k, verdict, 16 * k, vcol)
        draw_text(self, W * 0.5, H - 78 * k,
                  "日志已存到 Android/media/org.kawuxing.kawuxing/boot.log，"
                  "拍照或把该文件发出来即可定位原因", 14 * k, DIM)

        # 只显示有效行；按屏宽裁剪长度，避免长行跑出屏幕
        fs = 13 * k
        maxchars = max(40, min(200, int((W - 40 * k) / (fs * 0.56))))
        rows = []
        for ln in lines:
            ln = ln.replace("\t", "    ").rstrip()
            if not ln:
                continue
            if len(ln) > maxchars:
                ln = ln[:maxchars] + "…"
            rows.append(ln)
        top = H - 100 * k
        step = 17 * k
        max_rows = max(5, int((top - 64 * k) / step))
        if len(rows) > max_rows:
            keep_head = 1
            tail_n = max_rows - keep_head - 1
            rows = rows[:keep_head] + \
                ["……（省略 %d 行）" % (len(rows) - keep_head - tail_n)] + \
                rows[-tail_n:]
        y = top
        for ln in rows:
            draw_text(self, 18 * k, y, ln, fs, (0.86, 0.89, 0.86, 1), anchor="l")
            y -= step
            if y < 58 * k:
                break

        bw, bh = 300 * k, 44 * k
        bx = W * 0.5 - bw / 2.0
        rounded_btn(self, bx, 12 * k, bw, bh, "知道了，开始游戏", 20 * k)
        self.buttons.append((bx, 12 * k, bw, bh, "知道了，开始游戏", "crashclear"))

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
            # 手牌：平时是牌背；胡牌结算后三家都倒牌，正面摊给所有人看
            face = self.app.reveal_all
            hand = p.hand
            if face and eng.last_hu is not None and eng.last_hu.winner_seat == seat:
                # 胡牌者用快照（含点炮那张），牌型看得更完整
                hand = list(eng.last_hu.hand_snapshot) or hand
            n = len(hand)
            tw, th = 20 * k, 28 * k
            gap = 2 * k
            if face:
                # 倒牌时把牌放大到单侧可行的最大尺寸，否则小牌看不清字
                avail = W * 0.46
                if n:
                    tw = min(46 * k, max(20 * k, avail / float(n) - 2 * k))
                    th = tw * 1.4
            row_w = n * (tw + gap)
            bx = x0 if left else W - W * 0.03 - row_w
            for i in range(n):
                draw_tile(self, bx + i * (tw + gap), y0 - 40 * k, tw, th,
                          hand[i] if face else 0, back=not face)
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

    def _tile_unit(self, W, H, k):
        """底部一组牌的统一「牌宽」：手牌按 1.5 倍目标放大，装不下就收到刚好铺满。

        三重封顶（与桌面版 `unit = min(BASE_UNIT * TILE_SCALE, (W-150)/slots)` 同一思路）：
          ① 用户要求的 1.5 倍目标；
          ② 屏幕宽度要放得下「手牌 + 副露」整行；
          ③ 自己的牌河要能摆下两行同样大小的牌（牌河与手牌同尺寸）。
        """
        app = self.app
        p = app.engine.players[HUMAN]
        n = len(p.hand)
        drawn = 1 if (app.human_drawn >= 0 and app.human_drawn in p.hand) else 0
        slots = n * 1.025 + drawn * 0.18          # 手牌占位（含摸到那张多出的缝）
        for m in p.melds:                          # 副露：0.8 倍宽 + 组间缝
            cnt = 3 if m.type == MeldType.PENG else m.tile_count
            slots += cnt * 0.83 + 0.10
        uw = min(64 * k * 1.5, W * 0.985 / max(slots, 1.0))
        avail_v = (H * 0.72 - 8 * k) - 244 * k     # 牌河两行的可用高度
        uw = min(uw, (avail_v - 10 * k - 4) / 2.812)   # 2 行 + 行距（1.406 = 牌高宽比）
        uw = max(40 * k, uw)
        return uw, uw * 1.406

    def _draw_discards(self, W, H, k):
        """统一牌河：三家打出的牌按「出牌先后」排成一片，不再各摆各家门口。

        顺序就是引擎的 discard_log —— 从左到右、从上到下，最早的在左上，
        最新一张在末尾并加金框；每张牌用座位色描边标是谁打的。
        牌与手牌同尺寸；摆不下的早牌收起，牌河上方标「更早 N 张已收起」。
        """
        eng = self.app.engine
        log = getattr(eng, "discard_log", None) or []
        if not log:
            return
        uw, uh = self._tile_unit(W, H, k)
        gap = uw * 0.025
        top = H * 0.72 - 8 * k
        per = max(4, int((W * 0.96 + gap) / (uw + gap)))
        rows = max(1, min(2, int((top - 244 * k + 5 * k) / (uh + 5 * k))))
        cap = per * rows
        items = log[-cap:]                       # 只摆得下最近的这么多张
        over = len(log) - len(items)
        grid_w = per * (uw + gap) - gap
        bx = W * 0.5 - grid_w / 2.0
        for i, (seat, t) in enumerate(items):
            r, c = divmod(i, per)
            x = bx + c * (uw + gap)
            y = top - (r + 1) * uh - r * 5 * k
            draw_tile(self, x, y, uw, uh, t)
            self.canvas.add(Color(*SEAT_COLOR.get(seat, DIM)))
            self.canvas.add(Line(rounded_rectangle=(x - 1, y - 1, uw + 2, uh + 2, 5),
                                 width=2.4))
            if i == len(items) - 1:              # 最新打出的一张
                self.canvas.add(Color(*GOLD))
                self.canvas.add(Line(rounded_rectangle=(
                    x - 2.5, y - 2.5, uw + 5, uh + 5, 7), width=2.4))
        if over > 0:
            draw_text(self, W * 0.98, top + 4 * k,
                      "更早 %d 张已收起" % over, 13 * k, DIM, anchor="r")

    def _draw_hand(self, W, H, k):
        app = self.app
        eng = app.engine
        p = eng.players[HUMAN]
        tw, th = self._tile_unit(W, H, k)        # 1.5 倍目标 + 宽度自适应
        gap = tw * 0.025
        n = len(p.hand)
        # 副露（碰/杠）排在左手边，比手牌小一号（与桌面版 0.8 倍一致）
        mw, mh = tw * 0.80, th * 0.80
        mgap = tw * 0.03
        groups = [3 if m.type == MeldType.PENG else m.tile_count for m in p.melds]
        melds_w = sum(c * (mw + mgap) + tw * 0.10 for c in groups)
        drawn = -1
        order = list(range(n))
        if app.human_drawn >= 0 and app.human_drawn in p.hand:
            drawn = p.hand.index(app.human_drawn)
            order = [i for i in range(n) if i != drawn] + [drawn]
        hand_w = n * (tw + gap) + (tw * 0.18 if drawn >= 0 else 0)
        x = W * 0.5 - (melds_w + hand_w) / 2.0
        y = 10 * k
        mx = x
        for m, cnt in zip(p.melds, groups):
            for _i in range(cnt):
                draw_tile(self, mx, y + (th - mh) / 2.0, mw, mh, m.tile)
                mx += mw + mgap
            mx += tw * 0.10
        x += melds_w
        for idx in order:
            is_drawn = (idx == drawn)
            sel = (idx == app.selected)
            xx = x
            yy = y + tw * 0.25 if sel else y
            draw_tile(self, xx, yy, tw, th, p.hand[idx], selected=sel)
            self.hand_rects.append((xx, yy, tw, th, p.hand[idx], idx))
            x += tw + gap + (tw * 0.18 if is_drawn else 0)

    def _draw_info(self, W, H, k):
        app = self.app
        eng = app.engine
        p = eng.players[HUMAN]
        # 亮倒/托管提示
        tips = []
        if p.liang_dao:
            tips.append("已亮倒 ×2" + ("（托管中）" if app.human_auto else ""))
        if tips:
            draw_text(self, W * 0.5, 186 * k, "　".join(tips), 18 * k, GOLD)
        # 亮倒中、还没出牌：把「能打哪几张」直接写出来（点别的牌打不出去）
        if p.liang_dao and app.wait_discard and not app.human_auto:
            draw_text(self, W * 0.5, 208 * k,
                      "亮倒中 · 只能打：%s" % app._liang_keep_text(), 18 * k, GOLD)
        # 听牌推演面板
        if app.inspect is not None:
            self._draw_ting(W, H, k, app.inspect)
        # 底部按钮
        bx, by = W * 0.5, 128 * k
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
            draw_text(self, W * 0.5, 230 * k,
                      "打 %s：不听牌" % tile_name(tile), 19 * k, DIM)
            return
        outs = eng.outs_left(HUMAN, rest, {tile: 1})
        parts = []
        for t in sorted(outs):
            n = outs[t]
            parts.append("%s 剩%d" % (tile_name(t), n) if n else
                         "%s 已绝张" % tile_name(t))
        draw_text(self, W * 0.5, 230 * k,
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
        _log_env_info()
        # ★ 上一轮没走完（原生崩溃）→ 先摆「崩溃现场」页，用户看完再开局。
        self.crash_report = list(_prev_tail) if _prev_tail else None
        self.started = False
        self.engine = None
        self.ai = None
        self._gen = None
        self._reset_state()
        _init_sounds()
        self.board = Board(self)
        if self.crash_report:
            print("[CRASH-REPORT] showing %d lines from previous run"
                  % len(self.crash_report))
            Clock.schedule_once(lambda dt: self.board.redraw(), 0)
        else:
            Clock.schedule_once(lambda dt: self.start_game(), 0.3)
        return self.board

    # ----------------------------------------------------------------
    # 生命周期：正常退出要摘掉 running.flag，否则下次会被误判成崩溃
    # ----------------------------------------------------------------

    def on_stop(self):
        _clear_run_flag()

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
        _trace("start_game")
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
        _trace("round %d start, dealer=%d" % (self.round_index, self.dealer))
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
            _trace("discard seat=%d tile=%s" % (seat, tile_name(tile)))
            sfx("discard")
            say_tile(tile)                    # 报出牌面（「五筒」…）
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
                # 逆时针轮转：先问「下家」= 出牌者的顺时针下一位
                other = (seat - kk) % SEAT_COUNT
                opts = eng.get_claim_options(other, tile, seat, gang_shang_pao)
                # 亮倒的人不能碰：碰会拆散已经听牌的手牌，亮倒就失去意义
                #（电脑托管和玩家手动走同一条过滤，口径一致）
                opts = self._auto_claim_options(other, opts)
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

            # 逆时针轮转：左家(1) → 你(0) → 右家(2) → 左家(1)…
            seat = (seat - 1) % SEAT_COUNT
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
        if self.engine.players[HUMAN].liang_dao:
            self.message = "亮倒中 · 只能打出打了仍能听头的牌"
        else:
            self.message = "轮到你了 · 点牌选中，再点一次打出"
        self.board.redraw()
        # 等待途中可能点了「亮倒」或「托管」：那两个都不改 pending_discard，
        # 所以循环必须同时盯着 human_auto，否则会一直等一张永不出现的牌。
        while (self.wait_discard and self.pending_discard < 0
               and not self._is_auto(HUMAN)):
            yield 0.05
        tile = self.pending_discard
        self.pending_discard = -1
        self.wait_discard = False
        if tile < 0 and self._is_auto(HUMAN):
            # 转托管：交给电脑挑一张（亮倒时优先打刚摸到的）
            return self.ai[HUMAN].choose_discard(self.engine, HUMAN)
        return tile

    def _settle(self):
        _trace("settle")
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
        """
        亮倒时机：**只有「自己进张之后、还没出牌」这一个窗口**。

        · 自己摸牌后（含杠后补摸）、碰牌后、庄家起手 14 张 —— 都是「待出牌」，
          结构位 14，只要有一张打出去之后仍然听头就能亮倒；
        · 别人回合、自己已经出完牌（结构位 13）—— 不能亮倒
          （早期版本这时也亮着按钮，等于「不打牌就能亮倒」，是 bug）。
        """
        eng = self.engine
        p = eng.players[HUMAN]
        if eng.round_over or p.liang_dao or not eng.rules.allow_liang_dao:
            return False
        if not self.wait_discard:                  # 必须轮到自己出牌
            return False
        if structural_slots(p) != 14:              # 必须已经进张、手里多一张
            return False
        return self._ting_keep_discard() >= 0      # 打了还得仍能听头

    def _liang_keep_text(self):
        """「亮倒中可打」的牌面文字，用于提示。"""
        eng = self.engine
        keeps = ting_keep_discards(eng, HUMAN)
        if not keeps:
            return "（无）"
        return " ".join(tile_name(t) for t in keeps)

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
        """
        亮倒：手牌摊开、本局输赢 ×2。

        注意时序 —— **先亮倒、后出牌**：亮倒只是把状态置位，接下来那张牌仍然
        由玩家自己点（只能点「打了仍能听头」的），出牌后才真正进入听牌形态。
        不再自动托管，想交给电脑就点「托管」。
        """
        eng = self.engine
        p = eng.players[HUMAN]
        if not self._can_liang_dao():
            return
        p.liang_dao = True
        self.human_auto = False
        self.inspect = None
        self.selected = -1
        self.message = "你亮倒了（×2）· 只能打：%s" % self._liang_keep_text()
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
        if p.liang_dao and self.human_auto:
            return                          # 亮倒 + 托管：牌由电脑打，点牌无效
        if not self.wait_discard:
            # 没轮到出牌时点牌 = 只看推演
            self.inspect = tile if self.inspect != tile else None
            self.board.redraw()
            return
        if self.selected == idx:
            # 亮倒中：只有「打了之后手牌仍然听头」的牌才打得出去
            if p.liang_dao and not keeps_ting(eng, HUMAN, tile):
                self.selected = -1
                self.inspect = None
                self.message = "亮倒中 · 只能打：%s" % self._liang_keep_text()
                self.board.redraw()
                return
            self.pending_discard = tile
            self.selected = -1
            self.inspect = None
        else:
            self.selected = idx
            self.inspect = tile
        self.board.redraw()

    def _on_button(self, value):
        eng = self.engine
        if value == "crashclear":
            # 崩溃现场看完了 → 收起报告页，正常开一局
            self.crash_report = None
            self.start_game()
            return
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
