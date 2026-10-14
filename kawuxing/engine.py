# -*- coding: utf-8 -*-
"""
卡五星牌局引擎 + 电脑对手（Python 版）。

对应 Unity 工程的 Assets/Scripts/Core/GameEngine.cs 与 Assets/Scripts/Ai/SimpleAi.cs。
流程与 C# 版完全一致：
    摸牌 → 自身动作（自摸/暗杠/补杠）→ 出牌 → 他家响应（胡/杠/碰）→ 下家
"""

import random

from .rules import (
    KIND_COUNT, TONG_START, HONOR_START, ZHONG, FA, BAI,
    MeldType, Meld, PlayerState, ClaimType, ClaimOption, RuleConfig, HuFlags,
    ScoreResult, HuResult,
    can_hu, all_shapes, estimate_shanten, is_pure_suit, is_que_yi_men,
    is_five, is_honor, is_number, is_valid, rank_of, tile_name,
    to_counts, count_of, remove_tiles, winning_tiles, is_ting,
    evaluate, is_pai_hu,
)

SEAT_COUNT = 3


class GameEngine(object):
    def __init__(self, rules=None, seed=0):
        self.rules = rules if rules is not None else RuleConfig()
        self.rng = random.Random(seed)
        self.players = [PlayerState(i) for i in range(SEAT_COUNT)]
        for i, p in enumerate(self.players):
            p.name = "玩家%d" % (i + 1)
            p.seat = i

        self.wall = []
        self.dealer_seat = 0
        self.current_seat = 0
        self.round_index = 0
        self.last_drawn_tile = -1
        self.last_discard_tile = -1
        self.last_discard_seat = -1
        self.last_action_was_gang = False
        self.last_gang_seat = -1
        self.round_over = False
        self.is_draw = False
        self.last_hu = None
        self.log_lines = []

    # ------------------------------------------------------------------
    # 开局
    # ------------------------------------------------------------------

    def start_round(self, dealer_seat, round_index):
        self.round_over = False
        self.is_draw = False
        self.last_hu = None
        self.last_action_was_gang = False
        self.last_gang_seat = -1
        self.last_discard_tile = -1
        self.last_discard_seat = -1

        self.dealer_seat = dealer_seat % SEAT_COUNT
        self.current_seat = self.dealer_seat
        self.round_index = round_index

        for s in range(SEAT_COUNT):
            self.players[s].reset()
            self.players[s].is_dealer = (s == self.dealer_seat)

        self.wall = []
        for t in range(KIND_COUNT):
            for _ in range(4):
                self.wall.append(t)
        self.rng.shuffle(self.wall)

        # 每人 13 张
        for _ in range(13):
            for s in range(SEAT_COUNT):
                self.players[s].hand.append(self.wall.pop(0))
                self.players[s].hand.sort()

        # 庄家摸第 14 张
        first = self._pop_wall()
        self.players[self.dealer_seat].hand.append(first)
        self.players[self.dealer_seat].hand.sort()
        self.last_drawn_tile = first

        self.log("第 %d 局开始，%s 坐庄（底分 %d，封顶 ×%d）" % (
            round_index, self.players[self.dealer_seat].name,
            self.rules.base_score, self.rules.score_cap))

    def _pop_wall(self):
        if not self.wall:
            return -1
        return self.wall.pop()

    # ------------------------------------------------------------------
    # 摸牌 / 出牌
    # ------------------------------------------------------------------

    def draw_for_seat(self, seat):
        """从牌墙摸一张。牌墙为空返回 -1（荒庄）。"""
        if not self.wall:
            return -1
        t = self._pop_wall()
        p = self.players[seat]
        p.hand.append(t)
        p.hand.sort()
        self.last_drawn_tile = t
        return t

    def try_discard(self, seat, tile):
        p = self.players[seat]
        if tile in p.hand:
            p.hand.remove(tile)
        else:
            if not p.hand:
                return False
            tile = p.hand.pop()
        p.discards.append(tile)
        self.last_discard_tile = tile
        self.last_discard_seat = seat
        return True

    # ------------------------------------------------------------------
    # 可行动作查询
    # ------------------------------------------------------------------

    def can_peng(self, seat, tile):
        if not self.rules.allow_peng:
            return False
        return count_of(self.players[seat].hand, tile) >= 2

    def can_ming_gang(self, seat, tile):
        if not self.rules.allow_gang:
            return False
        return count_of(self.players[seat].hand, tile) >= 3

    def can_hu_with(self, seat, tile, flags):
        """用「手里还没有的一张牌」补和（点炮 / 抢杠 / 杠上炮）。返回 ScoreResult 或 None。"""
        p = self.players[seat]
        counts = to_counts(p.hand)
        if not is_valid(tile):
            return None
        counts[tile] += 1
        self._fill_shou_zhua_yi(counts, p, flags)
        return evaluate(counts, tile, p.melds, flags, self.rules)

    def can_hu_self_draw(self, seat, flags):
        """
        自摸判定。
        注意：摸到的牌已经在手牌里了，所以这里绝不能再 counts[tile] += 1，
        否则会变成 15 张导致永远判不出自摸。
        """
        p = self.players[seat]
        tile = self.last_drawn_tile
        if not p.hand or not is_valid(tile):
            return None
        counts = to_counts(p.hand)
        self._fill_shou_zhua_yi(counts, p, flags)
        return evaluate(counts, tile, p.melds, flags, self.rules)

    def can_hu_on_discard(self, seat, tile, from_seat, gang_shang_pao,
                          qiang_gang=False):
        """
        别人打出 tile，seat 能不能胡。
        屁胡（没有任何番型加成）默认只能自摸 —— 点炮胡会被直接否掉；
        抢杠胡、杠上炮本身自带番型，不受这条限制。
        """
        flags = HuFlags(gang_shang_pao=gang_shang_pao, qiang_gang=qiang_gang)
        score = self.can_hu_with(seat, tile, flags)
        if score is None:
            return False
        if self.rules.pai_hu_requires_self_draw and is_pai_hu(score):
            allow = (getattr(self.rules, "pai_hu_allow_liang_dao", False)
                     and self.players[seat].liang_dao)
            if not allow:
                return False
        return True

    def get_self_options(self, seat, after_gang, hai_di):
        """摸牌后的自身选项：自摸胡 / 暗杠 / 补杠。"""
        lst = []
        p = self.players[seat]
        if not p.hand:
            return lst

        last = self.last_drawn_tile
        if is_valid(last) and last in p.hand:
            flags = HuFlags(self_draw=True, after_gang=after_gang,
                            hai_di=hai_di, liang_dao=p.liang_dao)
            score = self.can_hu_self_draw(seat, flags)
            if score is not None:
                opt = ClaimOption(ClaimType.HU, seat, last, -1)
                opt.is_self_draw = True
                opt.after_gang = after_gang
                opt.hai_di = hai_di
                opt.score = score
                lst.append(opt)

        if self.rules.allow_gang:
            counts = to_counts(p.hand)
            for t in range(KIND_COUNT):
                if counts[t] == 4:
                    opt = ClaimOption(ClaimType.GANG, seat, t, -1)
                    opt.score = None
                    lst.append(opt)
                else:
                    pm = p.find_peng_meld(t)
                    if counts[t] >= 1 and pm is not None:
                        lst.append(ClaimOption(ClaimType.GANG, seat, t, pm.from_seat))
        return lst

    def get_claim_options(self, seat, tile, from_seat, gang_shang_pao):
        """别人打出一张牌后，seat 可做的响应。"""
        lst = []
        if seat == from_seat:
            return lst

        if self.can_hu_on_discard(seat, tile, from_seat, gang_shang_pao):
            opt = ClaimOption(ClaimType.HU, seat, tile, from_seat)
            opt.gang_shang_pao = gang_shang_pao
            lst.append(opt)

        if self.can_ming_gang(seat, tile):
            lst.append(ClaimOption(ClaimType.GANG, seat, tile, from_seat))

        if self.can_peng(seat, tile):
            lst.append(ClaimOption(ClaimType.PENG, seat, tile, from_seat))

        return lst

    def is_ting(self, seat):
        p = self.players[seat]
        return is_ting(p.hand, len(p.melds))

    def ting_tiles(self, seat):
        p = self.players[seat]
        return winning_tiles(p.hand, len(p.melds))

    # ------------------------------------------------------------------
    # 执行动作
    # ------------------------------------------------------------------

    def apply_peng(self, seat, tile):
        p = self.players[seat]
        remove_tiles(p.hand, tile, 2)
        meld = Meld(MeldType.PENG, tile, self.last_discard_seat)
        p.melds.append(meld)
        self._take_from_discard_pile(self.last_discard_seat, tile)
        self.current_seat = seat
        self.clear_gang_mark()
        self.log("%s 碰 %s" % (p.name, tile_name(tile)))
        return meld

    def apply_ming_gang(self, seat, tile):
        """直杠：杠别人打出的牌，放杠者付 2 倍底金。"""
        p = self.players[seat]
        remove_tiles(p.hand, tile, 3)
        meld = Meld(MeldType.MING_GANG, tile, self.last_discard_seat)
        p.melds.append(meld)
        self._take_from_discard_pile(self.last_discard_seat, tile)

        pay = 2 * self.rules.base_score
        giver = self.last_discard_seat
        if giver >= 0 and giver != seat:
            self._transfer(giver, seat, pay)

        self.current_seat = seat
        self.mark_gang(seat)
        self.log("%s 直杠 %s%s" % (
            p.name, tile_name(tile),
            "（%s 付 %d）" % (self.players[giver].name, pay) if giver >= 0 else ""))
        return meld

    def apply_an_gang(self, seat, tile):
        """暗杠：另两家各付 2 倍底金。"""
        p = self.players[seat]
        remove_tiles(p.hand, tile, 4)
        meld = Meld(MeldType.AN_GANG, tile, -1)
        p.melds.append(meld)

        pay = 2 * self.rules.base_score
        for s in range(SEAT_COUNT):
            if s != seat:
                self._transfer(s, seat, pay)

        self.current_seat = seat
        self.mark_gang(seat)
        self.log("%s 暗杠（另两家各付 %d）" % (p.name, pay))
        return meld

    def apply_bu_gang(self, seat, tile):
        """补杠：碰后补第四张，另两家各付 1 倍底金。可被抢杠。"""
        p = self.players[seat]
        meld = p.find_peng_meld(tile)
        if meld is None:
            return False
        if remove_tiles(p.hand, tile, 1) == 0:
            return False

        meld.type = MeldType.BU_GANG

        pay = 1 * self.rules.base_score
        for s in range(SEAT_COUNT):
            if s != seat:
                self._transfer(s, seat, pay)

        self.current_seat = seat
        self.mark_gang(seat)
        self.log("%s 补杠 %s（另两家各付 %d）" % (p.name, tile_name(tile), pay))
        return True

    def _take_from_discard_pile(self, seat, tile):
        if seat < 0 or seat >= SEAT_COUNT:
            return
        d = self.players[seat].discards
        for i in range(len(d) - 1, -1, -1):
            if d[i] == tile:
                d.pop(i)
                return

    def mark_gang(self, seat):
        self.last_action_was_gang = True
        self.last_gang_seat = seat

    def clear_gang_mark(self):
        self.last_action_was_gang = False
        self.last_gang_seat = -1

    # ------------------------------------------------------------------
    # 结算
    # ------------------------------------------------------------------

    def win_self_draw(self, seat, after_gang, hai_di):
        tile = self.last_drawn_tile
        p = self.players[seat]
        counts = to_counts(p.hand)
        flags = HuFlags(self_draw=True, after_gang=after_gang,
                        hai_di=hai_di, liang_dao=p.liang_dao)
        self._fill_shou_zhua_yi(counts, p, flags)
        score = evaluate(counts, tile, p.melds, flags, self.rules)
        if score is None:
            return None

        hu = self._build_hu(seat, -1, tile, counts, score, flags)

        value = score.multiplier * self.rules.base_score
        for s in range(SEAT_COUNT):
            if s != seat:
                self._transfer(s, seat, value)

        self._finish(hu)
        self.log("%s %s %s，共 %d 倍 × %d 底分，两家各付 %d" % (
            p.name, hu.win_type_text, tile_name(tile),
            score.multiplier, self.rules.base_score, value))
        return hu

    def win_by_discard(self, seat, tile, from_seat, qiang_gang, gang_shang_pao):
        p = self.players[seat]
        counts = to_counts(p.hand)
        counts[tile] += 1
        flags = HuFlags(self_draw=False, qiang_gang=qiang_gang,
                        gang_shang_pao=gang_shang_pao, liang_dao=p.liang_dao)
        self._fill_shou_zhua_yi(counts, p, flags)
        score = evaluate(counts, tile, p.melds, flags, self.rules)
        if score is None:
            return None

        hu = self._build_hu(seat, from_seat, tile, counts, score, flags)

        value = score.multiplier * self.rules.base_score
        if self.players[from_seat].liang_dao:
            value *= 2      # 点亮倒者的炮，多一倍

        self._transfer(from_seat, seat, value)

        self._finish(hu)
        self.log("%s %s %s（%s 放炮），%d 倍 × %d 底分 = %d" % (
            p.name, hu.win_type_text, tile_name(tile), self.players[from_seat].name,
            score.multiplier, self.rules.base_score, value))
        return hu

    def can_qiang_gang(self, ganger_seat, tile, gang_type=MeldType.BU_GANG):
        """
        抢杠：别人要杠这张牌，我能不能抢来胡。

        只有「补杠（加杠）」可以被抢：
          · 暗杠 —— 四张都在自己手里，别人无从抢起；
          · 明杠（直杠）—— 那张牌本来就在牌河里摆过，能胡的话当时就该胡了，
            不存在回头再抢的说法；
          · 补杠 —— 碰后补第四张，等于「把一张牌重新打出来」，所以可以被抢。

        抢杠胡自带 ×2 番型，所以屁胡形状的手牌也可以抢。
        传入的 gang_type 不是补杠时直接返回空列表。
        """
        if gang_type != MeldType.BU_GANG:
            return []
        robbers = []
        for s in range(SEAT_COUNT):
            if s == ganger_seat:
                continue
            if self.can_hu_on_discard(s, tile, ganger_seat, False,
                                      qiang_gang=True):
                robbers.append(s)
        return robbers

    def _build_hu(self, seat, from_seat, tile, counts, score, flags):
        hu = HuResult()
        hu.winner_seat = seat
        hu.from_seat = from_seat
        hu.win_tile = tile
        hu.flags = flags
        hu.score = score

        p = self.players[seat]
        hu.hand_snapshot = list(p.hand)
        if from_seat >= 0 and tile not in p.hand:
            hu.hand_snapshot.append(tile)
            hu.hand_snapshot.sort()

        shapes = all_shapes(counts, len(p.melds))
        best = None
        for sh in shapes:
            if sh.seven_pairs:
                best = sh
                break
            if best is None or len(sh.groups) > len(best.groups):
                best = sh
        if best is not None:
            hu.groups = best.groups
            hu.pair_tile = best.pair_tile
        return hu

    def declare_draw(self):
        self.is_draw = True
        self.round_over = True
        self.log("牌墙已空，荒庄。")
        if self.rules.liang_dao_pays_on_draw:
            for s in range(SEAT_COUNT):
                if not self.players[s].liang_dao:
                    continue
                for o in range(SEAT_COUNT):
                    if o != s:
                        self._transfer(s, o, self.rules.base_score)
                self.log("%s 亮倒荒庄，赔每家 %d" % (
                    self.players[s].name, self.rules.base_score))

    def _finish(self, hu):
        self.last_hu = hu
        self.round_over = True

    def _fill_shou_zhua_yi(self, counts_after_win, p, flags):
        total = sum(counts_after_win)
        if len(p.melds) == 4 and total == 2:
            flags.shou_zhua_yi = True

    def _transfer(self, frm, to, amount):
        if amount <= 0 or frm == to:
            return
        self.players[frm].score -= amount
        self.players[to].score += amount

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def visible_counts(self, except_seat):
        """某一门牌在场上可见的张数（弃牌 + 副露 + 亮倒者的手牌）。"""
        v = [0] * KIND_COUNT
        for s in range(SEAT_COUNT):
            p = self.players[s]
            if s == except_seat:
                for m in p.melds:
                    v[m.tile] += m.tile_count
                continue
            for d in p.discards:
                v[d] += 1
            for m in p.melds:
                v[m.tile] += m.tile_count
            if p.liang_dao:
                for h in p.hand:
                    v[h] += 1
        return v

    def outs_left(self, seat, concealed, extra_used=None):
        """
        手里 concealed 张、已经成听牌形状时，「每张能赢的牌还剩几张没露面」。

        统计口径（4 张一副）：4 - 自己的手牌 - 自己的弃牌 - 自己的副露
                              - 别人看得见的（弃牌 / 副露 / 亮倒摊开的手牌）

        concealed 可以传「打出某一张之后」的手牌，用来做悬停推演；
        extra_used 是额外扣减，例如 {tile: 1} 表示这张正被自己打出去。
        返回 {tile: 剩余张数}，没剩的记 0（界面上显示「已绝张」）。
        """
        p = self.players[seat]
        vis = self.visible_counts(seat)          # 含自己的副露
        out = {}
        for t in winning_tiles(concealed, len(p.melds)):
            used = vis[t] + concealed.count(t) + p.discards.count(t)
            if extra_used:
                used += extra_used.get(t, 0)
            out[t] = max(0, 4 - used)
        return out

    def log(self, msg):
        self.log_lines.append(msg)


# ======================================================================
# 电脑玩家：先看向听、再看好坏
# ======================================================================

class SimpleAi(object):
    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def _rand(self):
        return self.rng.random()

    def choose_discard(self, engine, seat):
        p = engine.players[seat]
        if not p.hand:
            return -1

        # 亮倒之后手牌锁死，只能把刚摸到的牌打出去
        if p.liang_dao:
            return engine.last_drawn_tile

        visible = engine.visible_counts(seat)
        candidates = self._distinct(p.hand)

        best_tile = candidates[0]
        best_shanten = 1 << 30
        best_keep_value = 1e18

        for t in candidates:
            rest = list(p.hand)
            rest.remove(t)
            shanten = estimate_shanten(rest, len(p.melds))
            noise = self._rand() * 0.25
            keep = self._tile_value(t, p.hand, visible) + noise
            if shanten < best_shanten or (shanten == best_shanten and keep < best_keep_value):
                best_shanten = shanten
                best_keep_value = keep
                best_tile = t
        return best_tile

    def _tile_value(self, tile, hand, visible):
        n = count_of(hand, tile)
        v = 11.0 if n >= 3 else (6.5 if n == 2 else 0.6)

        if is_number(tile):
            r = rank_of(tile)
            if r > 1 and (tile - 1) in hand:
                v += 2.2
            if r < 9 and (tile + 1) in hand:
                v += 2.2
            if r > 2 and (tile - 2) in hand:
                v += 1.0
            if r < 8 and (tile + 2) in hand:
                v += 1.0
            v += 1.6 if 3 <= r <= 7 else 0.5
        else:
            v -= 0.0 if n >= 2 else 0.8

        left = 4 - (visible[tile] if visible else 0)
        v += left * 0.06
        return v

    def decide_claim(self, engine, seat, options):
        if not options:
            return None

        for o in options:
            if o.type == ClaimType.HU:
                return o

        p = engine.players[seat]
        before = estimate_shanten(p.hand, len(p.melds))

        for o in options:
            if o.type != ClaimType.GANG:
                continue
            rest = list(p.hand)
            remove_tiles(rest, o.tile, 3)
            after = estimate_shanten(rest, len(p.melds) + 1)
            ok = after <= before + 1
            if o.from_seat >= 0 and ok and self._rand() < 0.92:
                return o
            if o.from_seat < 0 and self._rand() < 0.9:
                return o

        for o in options:
            if o.type != ClaimType.PENG:
                continue
            rest = list(p.hand)
            remove_tiles(rest, o.tile, 2)
            after = estimate_shanten(rest, len(p.melds) + 1)
            if after > before:
                continue

            will = 0.72
            if is_honor(o.tile):
                will += 0.12
            if before <= 1:
                will += 0.1
            if self._rand() < will:
                return o

        return ClaimOption.make_pass(seat, engine.last_discard_tile)

    def decide_self_action(self, engine, seat, options):
        if not options:
            return None

        for o in options:
            if o.type == ClaimType.HU:
                return o

        p = engine.players[seat]
        for o in options:
            if o.type != ClaimType.GANG:
                continue
            if p.find_peng_meld(o.tile) is not None:
                if self._rand() < 0.7:
                    return o
            else:
                rest = list(p.hand)
                remove_tiles(rest, o.tile, 4)
                after = estimate_shanten(rest, len(p.melds) + 1)
                before = estimate_shanten(p.hand, len(p.melds))
                if after <= before + 1 and self._rand() < 0.9:
                    return o
        return None

    @staticmethod
    def _distinct(src):
        out = []
        for t in src:
            if t not in out:
                out.append(t)
        return out
