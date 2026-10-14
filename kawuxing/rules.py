# -*- coding: utf-8 -*-
"""
卡五星规则内核（Python 版）。

本文件是 Unity 工程 Assets/Scripts/Core 下 Tiles.cs / Definitions.cs /
HandAnalyzer.cs / Scorer.cs 的逐行对应移植，用于桌面 exe 版本。
两份实现的规则必须保持一致：84 张牌、只碰杠不吃、番型相乘、杠牌即时结算。
"""

# ======================================================================
# 牌的编码
# ======================================================================

TONG_START = 0
TIAO_START = 9
HONOR_START = 18

ZHONG = 18
FA = 19
BAI = 20

KIND_COUNT = 21
TOTAL_COUNT = 84

_NUMERAL = ["一", "二", "三", "四", "五", "六", "七", "八", "九"]


def suit_of(tile):
    """0=筒 1=条 2=字"""
    if tile < TIAO_START:
        return 0
    if tile < HONOR_START:
        return 1
    return 2


def rank_of(tile):
    """序数牌 1..9，字牌 0"""
    if tile < TIAO_START:
        return tile + 1
    if tile < HONOR_START:
        return tile - TIAO_START + 1
    return 0


def index_in_suit(tile):
    if tile < TIAO_START:
        return tile
    if tile < HONOR_START:
        return tile - TIAO_START
    return tile - HONOR_START


def is_honor(tile):
    return tile >= HONOR_START


def is_number(tile):
    return 0 <= tile < HONOR_START


def is_valid(tile):
    return 0 <= tile < KIND_COUNT


def is_five(tile):
    """五筒 / 五条 —— 卡五星番型判定用"""
    return is_number(tile) and rank_of(tile) == 5


def is_terminal(tile):
    r = rank_of(tile)
    return r == 1 or r == 9


def tile_name(tile):
    if not is_valid(tile):
        return "??"
    s = suit_of(tile)
    if s == 0:
        return _NUMERAL[rank_of(tile) - 1] + "筒"
    if s == 1:
        return _NUMERAL[rank_of(tile) - 1] + "条"
    return "中" if tile == ZHONG else ("发" if tile == FA else "白")


def face_glyph(tile):
    if tile == ZHONG:
        return "中"
    if tile == FA:
        return "发"
    if tile == BAI:
        return "白"
    return ""


def to_counts(tiles):
    counts = [0] * KIND_COUNT
    if tiles:
        for t in tiles:
            if is_valid(t):
                counts[t] += 1
    return counts


def count_of(tiles, tile):
    n = 0
    for t in tiles:
        if t == tile:
            n += 1
    return n


def remove_tiles(tiles, tile, n):
    """从列表里移除 n 张指定牌，返回实际移除数量。就地修改。"""
    removed = 0
    for i in range(len(tiles) - 1, -1, -1):
        if removed >= n:
            break
        if tiles[i] == tile:
            tiles.pop(i)
            removed += 1
    return removed


def join_tiles(tiles):
    if not tiles:
        return "（无）"
    return " ".join(tile_name(t) for t in tiles)


# ======================================================================
# 副露 / 玩家 / 动作 / 规则配置
# ======================================================================

class MeldType(object):
    PENG = "peng"
    MING_GANG = "minggang"
    AN_GANG = "angang"
    BU_GANG = "bugang"


class Meld(object):
    __slots__ = ("type", "tile", "from_seat")

    def __init__(self, mtype, tile, from_seat=-1):
        self.type = mtype
        self.tile = tile
        self.from_seat = from_seat

    @property
    def is_gang(self):
        return self.type != MeldType.PENG

    @property
    def tile_count(self):
        return 3 if self.type == MeldType.PENG else 4

    @property
    def display_name(self):
        return {
            MeldType.PENG: "碰",
            MeldType.MING_GANG: "直杠",
            MeldType.AN_GANG: "暗杠",
        }.get(self.type, "补杠")

    def __repr__(self):
        return self.display_name + tile_name(self.tile)


class PlayerState(object):
    def __init__(self, seat=0):
        self.name = "玩家"
        self.is_human = False
        self.seat = seat
        self.hand = []          # 暗牌（已排序）
        self.melds = []         # 副露
        self.discards = []      # 弃牌堆
        self.score = 0
        self.liang_dao = False  # 是否已亮倒
        self.is_dealer = False
        self.last_meld_source_discard = -1

    def reset(self):
        del self.hand[:]
        del self.melds[:]
        del self.discards[:]
        self.liang_dao = False
        self.last_meld_source_discard = -1

    def find_peng_meld(self, tile):
        for m in self.melds:
            if m.type == MeldType.PENG and m.tile == tile:
                return m
        return None


class ClaimType(object):
    NONE = "none"
    PASS = "pass"
    PENG = "peng"
    GANG = "gang"
    HU = "hu"


class ClaimOption(object):
    __slots__ = ("type", "seat", "tile", "from_seat", "is_self_draw",
                 "after_gang", "qiang_gang", "hai_di", "gang_shang_pao", "score")

    def __init__(self, ctype, seat=-1, tile=-1, from_seat=-1):
        self.type = ctype
        self.seat = seat
        self.tile = tile
        self.from_seat = from_seat
        self.is_self_draw = False
        self.after_gang = False
        self.qiang_gang = False
        self.hai_di = False
        self.gang_shang_pao = False
        self.score = None

    @staticmethod
    def make_pass(seat, tile=-1):
        """构造一个「过」选项。tile 可省略（UI 侧只需要座位号）。"""
        return ClaimOption(ClaimType.PASS, seat, tile)

    # 便于阅读的别名（同一个函数，两种调用写法都支持：
    #   ClaimOption.make_pass(seat, tile) / ClaimOption.pass_of(seat)）
    pass_of = make_pass


class RuleConfig(object):
    """规则可调项，默认按湖北襄阳 / 随州一带的常见打法。"""

    def __init__(self):
        self.base_score = 1
        self.score_cap = 8
        self.allow_peng = True
        self.allow_gang = True
        self.allow_chi = False
        self.allow_seven_pairs = True
        self.allow_liang_dao = True
        # 屁胡（无任何番型加成）只能自摸，不能点炮和
        self.pai_hu_requires_self_draw = True
        # 例外：亮倒的玩家已经把手牌摊开、有输赢 ×2 的风险，
        # 所以允许他点炮胡（哪怕只是屁胡形状）—— 对手打出他听的牌就能胡。
        # 注意：这条只对「已亮倒」的人生效；没亮倒的人屁胡仍然只能自摸。
        self.pai_hu_allow_liang_dao = True
        self.require_que_yi_men = False
        self.liang_dao_pays_on_draw = True


class HuFlags(object):
    __slots__ = ("self_draw", "after_gang", "qiang_gang", "hai_di",
                 "gang_shang_pao", "shou_zhua_yi", "liang_dao")

    def __init__(self, **kw):
        self.self_draw = False
        self.after_gang = False
        self.qiang_gang = False
        self.hai_di = False
        self.gang_shang_pao = False
        self.shou_zhua_yi = False
        self.liang_dao = False
        for k, v in kw.items():
            setattr(self, k, v)


class ScoreResult(object):
    def __init__(self):
        self.fans = []
        self.raw_multiplier = 1
        self.multiplier = 1
        self.capped = False

    @property
    def fan_text(self):
        if not self.fans:
            return "屁胡 ×1"
        return " × ".join(self.fans) + "  =  ×" + str(self.raw_multiplier)


class HuResult(object):
    def __init__(self):
        self.winner_seat = -1
        self.from_seat = -1
        self.win_tile = -1
        self.flags = HuFlags()
        self.score = None
        self.hand_snapshot = []
        self.groups = []
        self.pair_tile = -1

    @property
    def win_type_text(self):
        f = self.flags
        if f.qiang_gang:
            return "抢杠胡"
        if f.after_gang:
            return "杠上开花"
        if f.hai_di:
            return "海底捞月"
        if f.self_draw:
            return "自摸"
        if f.gang_shang_pao:
            return "杠上炮"
        return "点炮"


# ======================================================================
# 和牌判定
# ======================================================================

GROUP_SEQUENCE = "seq"
GROUP_TRIPLET = "tri"


class Group(object):
    __slots__ = ("kind", "tile")

    def __init__(self, kind, tile):
        self.kind = kind
        self.tile = tile

    @property
    def display_name(self):
        if self.kind == GROUP_TRIPLET:
            return tile_name(self.tile) * 3
        return tile_name(self.tile) + tile_name(self.tile + 1) + tile_name(self.tile + 2)

    def __repr__(self):
        return self.display_name


class HuShape(object):
    __slots__ = ("pair_tile", "groups", "seven_pairs", "dragon_pairs")

    def __init__(self, pair_tile=-1, groups=None, seven_pairs=False, dragon_pairs=0):
        self.pair_tile = pair_tile
        self.groups = groups if groups is not None else []
        self.seven_pairs = seven_pairs
        self.dragon_pairs = dragon_pairs

    @property
    def all_triplets(self):
        if self.seven_pairs:
            return False
        for g in self.groups:
            if g.kind != GROUP_TRIPLET:
                return False
        return True

    def describe(self):
        if self.seven_pairs:
            return "七对"
        parts = [g.display_name for g in self.groups]
        parts.append("将:" + tile_name(self.pair_tile) * 2)
        return " + ".join(parts)


def all_shapes(counts, meld_count):
    """列出所有合法的和牌拆解。"""
    result = []
    if counts is None:
        return result

    need_groups = 4 - meld_count
    if need_groups < 0:
        return result

    total = sum(counts)
    if total != need_groups * 3 + 2:
        return result

    if meld_count == 0 and is_seven_pairs(counts):
        result.append(HuShape(pair_tile=-1, groups=[], seven_pairs=True,
                              dragon_pairs=count_dragon_pairs(counts)))

    work = list(counts)
    for pair in range(KIND_COUNT):
        if work[pair] < 2:
            continue
        work[pair] -= 2
        acc = []
        if _decompose(work, need_groups, acc):
            result.append(HuShape(pair_tile=pair, groups=list(acc)))
        work[pair] += 2
    return result


def _decompose(c, need_groups, acc):
    i = 0
    n = len(c)
    while i < n and c[i] == 0:
        i += 1
    if i == n:
        return need_groups == 0

    if need_groups > 0 and c[i] >= 3:
        c[i] -= 3
        acc.append(Group(GROUP_TRIPLET, i))
        if _decompose(c, need_groups - 1, acc):
            return True
        acc.pop()
        c[i] += 3

    # 顺子只在同一门序数牌内部成立，且不能跨过 9
    if (need_groups > 0 and is_number(i) and rank_of(i) <= 7
            and c[i + 1] > 0 and c[i + 2] > 0):
        c[i] -= 1
        c[i + 1] -= 1
        c[i + 2] -= 1
        acc.append(Group(GROUP_SEQUENCE, i))
        if _decompose(c, need_groups - 1, acc):
            return True
        acc.pop()
        c[i] += 1
        c[i + 1] += 1
        c[i + 2] += 1

    return False


def can_hu(counts, meld_count):
    return len(all_shapes(counts, meld_count)) > 0


def is_seven_pairs(counts):
    pairs = 0
    total = 0
    for c in counts:
        if c % 2 != 0:
            return False
        pairs += c // 2
        total += c
    return total == 14 and pairs == 7


def count_dragon_pairs(counts):
    return sum(1 for c in counts if c == 4)


def winning_tiles(concealed, meld_count):
    counts = to_counts(concealed)
    res = []
    for t in range(KIND_COUNT):
        if counts[t] >= 4:
            continue
        counts[t] += 1
        if can_hu(counts, meld_count):
            res.append(t)
        counts[t] -= 1
    return res


def is_ting(concealed, meld_count):
    return len(winning_tiles(concealed, meld_count)) > 0


def estimate_shanten(concealed, meld_count):
    """距离和牌还差几步的粗略估计（越小越接近），AI 打牌时用来排序。"""
    counts = to_counts(concealed)
    need_groups = 4 - meld_count
    if need_groups < 0:
        return 0

    best = 8
    work = list(counts)

    for pair in range(KIND_COUNT):
        if work[pair] < 2:
            continue
        work[pair] -= 2
        groups, partials = _count_groups(work, need_groups)
        shanten = (need_groups - groups) * 2 - partials
        if shanten < best:
            best = shanten
        work[pair] += 2

    if meld_count == 0:
        pairs = sum(c // 2 for c in counts)
        sp = 6 - pairs
        if sp < best:
            best = sp

    return best


def _count_groups(c, need_groups):
    work = list(c)
    groups = 0
    partials = 0
    n = len(work)

    i = 0
    while i < n and groups < need_groups:
        while work[i] >= 3 and groups < need_groups:
            work[i] -= 3
            groups += 1
        while (work[i] >= 1 and is_number(i) and rank_of(i) <= 7
               and work[i + 1] >= 1 and work[i + 2] >= 1 and groups < need_groups):
            work[i] -= 1
            work[i + 1] -= 1
            work[i + 2] -= 1
            groups += 1
        i += 1

    i = 0
    while i < n and groups + partials < need_groups:
        if work[i] >= 2:
            partials += 1
            work[i] -= 2
            continue                      # 四张可拆成两搭，i 不动
        if is_number(i) and rank_of(i) <= 8 and work[i] >= 1 and work[i + 1] >= 1:
            partials += 1
            work[i] -= 1
            work[i + 1] -= 1
        i += 1

    return groups, partials


def is_que_yi_men(counts, melds):
    has = [False, False, False]
    for i in range(len(counts)):
        if counts[i] == 0:
            continue
        has[suit_of(i)] = True
    if melds:
        for m in melds:
            has[suit_of(m.tile)] = True
    return (1 if has[0] else 0) + (1 if has[1] else 0) + (1 if has[2] else 0) <= 2


def is_pure_suit(counts, melds):
    suit = None
    for i in range(len(counts)):
        if counts[i] == 0:
            continue
        s = suit_of(i)
        if s == 2:
            return False
        if suit is None:
            suit = s
        elif suit != s:
            return False
    if melds:
        for m in melds:
            s = suit_of(m.tile)
            if s == 2:
                return False
            if suit is None:
                suit = s
            elif suit != s:
                return False
    return suit is not None


# ======================================================================
# 算番：番型之间相乘，最后按封顶倍数截断（双龙七对可破顶）
# ======================================================================

def evaluate(counts, win_tile, melds, flags, rules):
    """返回 ScoreResult 或 None（不能和）。"""
    if counts is None:
        return None
    if rules is None:
        rules = RuleConfig()
    meld_count = len(melds) if melds else 0

    shapes = all_shapes(counts, meld_count)
    if not shapes:
        return None

    if rules.require_que_yi_men and not is_que_yi_men(counts, melds):
        return None
    if not rules.allow_seven_pairs:
        shapes = [s for s in shapes if not s.seven_pairs]
    if not shapes:
        return None

    best = None
    for shape in shapes:
        sr = _score_shape(shape, counts, win_tile, melds, flags, rules)
        if best is None or sr.raw_multiplier > best.raw_multiplier:
            best = sr
    if best is None:
        return None

    double_dragon = bool(best.fans) and best.fans[0].startswith("双龙七对")
    cap = rules.score_cap if rules.score_cap > 0 else 1 << 30
    if not double_dragon and best.raw_multiplier > cap:
        best.capped = True
        best.multiplier = cap
    else:
        best.multiplier = best.raw_multiplier
    return best


def _score_shape(shape, counts, win_tile, melds, flags, rules):
    sr = ScoreResult()
    m = 1
    seven_pairs = shape.seven_pairs

    # ---- 牌型 ----
    if seven_pairs:
        if shape.dragon_pairs >= 2:
            m *= 16
            sr.fans.append("双龙七对×16")
        elif shape.dragon_pairs == 1:
            m *= 8
            sr.fans.append("龙七对×8")
        else:
            m *= 4
            sr.fans.append("七对×4")
    elif shape.all_triplets:
        m *= 2
        sr.fans.append("碰碰胡×2")

    # ---- 清一色 ----
    if is_pure_suit(counts, melds):
        m *= 4
        sr.fans.append("清一色×4")

    if not seven_pairs:
        # ---- 大三元 / 小三元 ----
        honor_triplets = 0
        for t in (ZHONG, FA, BAI):
            if _has_triplet_of(counts, shape, melds, t):
                honor_triplets += 1
        pair_is_honor = shape.pair_tile >= HONOR_START

        if honor_triplets >= 3:
            m *= 8
            sr.fans.append("大三元×8")
        elif honor_triplets == 2 and pair_is_honor:
            m *= 4
            sr.fans.append("小三元×4")

        # ---- 四归一 ----
        if _has_peng_meld(melds, win_tile):
            m *= 2
            sr.fans.append("明四归一×2")
        elif is_valid(win_tile) and counts[win_tile] >= 4:
            m *= 4
            sr.fans.append("暗四归一×4")

        # ---- 卡五星：卡张胡五筒 / 五条 ----
        # 判定标准是「这一手和牌里，和的那张 5 确实补成了一个四五六的顺子」，
        # 也就是 4、6 夹 5。单吊 5、或 5 只是组成刻子/对子，都不算。
        if is_five(win_tile) and _forms_ka_wu_xing(shape, win_tile):
            m *= 2
            sr.fans.append("卡五星×2")

    # ---- 手抓一：四副碰/杠，手中只剩一张单吊 ----
    if flags.shou_zhua_yi:
        m *= 4
        sr.fans.append("手抓一×4")

    # ---- 场合番 ----
    if flags.after_gang:
        m *= 2
        sr.fans.append("杠上开花×2")
    if flags.qiang_gang:
        m *= 2
        sr.fans.append("抢杠胡×2")
    if flags.gang_shang_pao:
        m *= 2
        sr.fans.append("杠上炮×2")
    if flags.hai_di:
        m *= 2
        sr.fans.append("海底捞月×2")

    # ---- 亮倒 ----
    if flags.liang_dao:
        m *= 2
        sr.fans.append("亮倒×2")

    sr.raw_multiplier = m
    return sr


def _forms_ka_wu_xing(shape, win_tile):
    """
    和牌张 win_tile 是否为「卡张五筒 / 五条」。
    牌序里五筒 = 4、五条 = 13，所以四五六的顺子记作 Group(SEQUENCE, win_tile - 1)：
    筒 四五六 = 3/4/5，条 四五六 = 12/13/14。
    """
    for g in shape.groups:
        if g.kind == GROUP_SEQUENCE and g.tile == win_tile - 1:
            return True
    return False


def _has_triplet_of(counts, shape, melds, tile):
    if counts[tile] >= 3:
        return True
    if melds:
        for m in melds:
            if m.tile == tile and m.is_gang:
                return True
        for m in melds:
            if m.tile == tile and m.type == MeldType.PENG:
                return True
    if shape is not None:
        for g in shape.groups:
            if g.kind == GROUP_TRIPLET and g.tile == tile:
                return True
    return False


def _has_peng_meld(melds, tile):
    if not melds:
        return False
    for m in melds:
        if m.tile == tile and m.type == MeldType.PENG:
            return True
    return False


def is_pai_hu(sr):
    return sr is not None and sr.raw_multiplier <= 1
