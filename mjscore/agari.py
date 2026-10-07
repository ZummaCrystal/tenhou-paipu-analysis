# -*- coding: utf-8 -*-
"""和牌判别器 + 点数计算器（第 15 轮）

天凤立直麻将的「和牌判别」按牌型分三类：

* 国士無双（KOKUSHI）：十三种幺九牌各一张，其中一种成对，共 13 个 block；必须门清。
* 七対子（CHIITOI）：七个互不相同的对子，共 7 个 block；必须门清。
* 面子手（MENTSU）：四组完整面子 + 一组雀头，共 5 个 block；完整面子 = 副露摆出的
  顺子/明刻/明槓/暗槓、手中的暗刻、或手中点数相连的顺子（仅 m/p/s）。

每类牌型 × 自摸/荣和 × 立直/默听/副露 = 18 种判别器，见 ``DISCRIMINATORS``。
另外提供 ``score(...)``：判定可以和牌时，按天凤段位战规则算出符/番/打点。

牌 id 口径与 :mod:`mjscore.mjlog` 一致：``kind = tid // 4``
（0-8 = m1-9、9-17 = p1-9、18-26 = s1-9、27-33 = 東南西北白發中），赤 5 = id 16/52/88。

本模块只吃「手牌 + 副露 + 和了张 + 场况」，不依赖 :mod:`mjscore.replay` 的状态机。
本轮不集成界面，只作为第二类特征（期望打点）的计算基础。
"""

from __future__ import division

from .mjlog import kind_of, is_red

# ---------------------------------------------------------------- 常量

KOKUSHI = "国士無双"
CHIITOI = "七対子"
MENTSU = "面子手"
SHAPES = (KOKUSHI, CHIITOI, MENTSU)

RIICHI = "立直"
DAMATEN = "默听"
FURO = "副露"
STATES = (RIICHI, DAMATEN, FURO)

TSUMO = "自摸"
RON = "荣和"
MODES = (TSUMO, RON)

EAST, SOUTH, WEST, NORTH = 27, 28, 29, 30
WINDS = (EAST, SOUTH, WEST, NORTH)
DRAGONS = (31, 32, 33)          # 白 發 中
# 幺九牌的种类：1/9 + 字牌
YAOCHU_KINDS = (0, 8, 9, 17, 18, 26) + (27, 28, 29, 30, 31, 32, 33)
KOKUSHI_KINDS = YAOCHU_KINDS    # 国士要求的 13 种

# 天凤 log 的役 id（0..54）——与 web/js/ui.js 的 YAKU 表、以及用 71 个牌谱实测的结果一致。
YAKU_ID = {
    0: "門前清自摸和", 1: "立直", 2: "一発", 3: "槍槓", 4: "嶺上開花", 5: "海底摸月",
    6: "河底撈魚", 7: "平和", 8: "断幺九", 9: "一盃口", 10: "自風 東", 11: "自風 南",
    12: "自風 西", 13: "自風 北", 14: "場風 東", 15: "場風 南", 16: "場風 西",
    17: "場風 北", 18: "役牌 白", 19: "役牌 發", 20: "役牌 中", 21: "両立直",
    22: "七対子", 23: "混全帯幺九", 24: "一気通貫", 25: "三色同順", 26: "三色同刻",
    27: "三槓子", 28: "対々和", 29: "三暗刻", 30: "小三元", 31: "混老頭", 32: "二盃口",
    33: "純全帯幺九", 34: "混一色", 35: "清一色", 36: "人和", 37: "天和", 38: "地和",
    39: "大三元", 40: "四暗刻", 41: "四暗刻単騎", 42: "字一色", 43: "緑一色", 44: "清老頭",
    45: "九蓮宝燈", 46: "純正九蓮宝燈", 47: "国士無双", 48: "国士無双十三面",
    49: "大四喜", 50: "小四喜", 51: "四槓子", 52: "宝牌", 53: "里宝牌", 54: "赤宝牌",
}
ID_YAKU = dict((v, k) for k, v in YAKU_ID.items())
# 役満 id（打点按役満算，不是番数翻倍）
YAKUMAN_IDS = (36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51)
# 双倍役満（天凤：国士十三面 / 四暗刻単騎 / 大四喜 / 純正九蓮宝燈）
DOUBLE_YAKUMAN_IDS = (41, 46, 48, 49)

# 立直 default 关闭
DEFAULT_CTX = {
    "riichi": 0,          # 0=无、1=立直、2=両立直
    "ippatsu": False,     # 一発
    "rinshan": False,     # 嶺上開花
    "haitei": False,      # 海底摸月（自摸）
    "houtei": False,      # 河底撈魚（荣和）
    "chankan": False,     # 槍槓
    "tenhou": False,      # 天和
    "chiihou": False,     # 地和
    "renhou": False,      # 人和
    "dora": (),           # 宝牌指示牌（牌 id）
    "ura": (),            # 里宝牌指示牌（牌 id），无立直时忽略
}


def yaku_name(yid):
    """役 id -> 名（未知 id 退化为「役#id」）。"""
    return YAKU_ID.get(yid, "役#%d" % yid)


def merge_ctx(ctx=None):
    """把外部场况合并进默认 ctx（不修改入参）。"""
    out = dict(DEFAULT_CTX)
    if ctx:
        out.update(ctx)
    return out


# ---------------------------------------------------------------- 牌张小工具

def counts_of(tiles):
    """牌 id 列表 -> 34 项 kind 计数。"""
    counts = [0] * 34
    for t in tiles:
        counts[kind_of(t)] += 1
    return counts


def is_yaochu_kind(k):
    """该 kind 是否为幺九牌（1/9 或字牌）。"""
    return k in YAOCHU_KINDS


def is_terminal_kind(k):
    return k < 27 and (k % 9 == 0 or k % 9 == 8)


def is_honor_kind(k):
    return k >= 27


def is_simple_kind(k):
    """断幺九要求：2..8 的数牌。"""
    return k < 27 and 1 <= (k % 9) <= 7


def kind_name(k):
    """kind -> 牌名（m/p/s 用 1-9，字牌用汉字）。"""
    if k < 27:
        return "%d%s" % (k % 9 + 1, "mps"[k // 9])
    return "東南西北白發中"[k - 27]


def dora_count(indicators, tiles):
    """宝牌指示牌 -> 手里实际宝牌张数。"""
    n = 0
    counts = counts_of(tiles)
    for ind in indicators:
        k = kind_of(ind)
        if k < 27:
            nxt = k // 9 * 9 + (k % 9 + 1) % 9
        elif k < 31:
            nxt = 27 + (k - 27 + 1) % 4
        else:
            nxt = 31 + (k - 31 + 1) % 3
        n += counts[nxt]
    return n


def validate_tiles(tiles, what="手牌"):
    """同一种牌最多 4 张（合成数据时最容易犯的错）。"""
    counts = counts_of(tiles)
    for k, c in enumerate(counts):
        if c > 4:
            raise ValueError("%s里 %s 出现了 %d 张（超过 4）" % (what, kind_name(k), c))
    return counts
# ---------------------------------------------------------------- 副露 / 状态

OPEN_TYPES = ("chi", "pon", "kakan", "daiminkan")
CLOSED_TYPES = ("ankan",)
SET_TYPES = OPEN_TYPES + CLOSED_TYPES


def set_melds(melds):
    """只取真正占一组面子的副露（拔北忽略）。"""
    return [m for m in (melds or ()) if m.get("callType") in SET_TYPES]


def n_sets(melds):
    """已有的完整面子数（吃/碰/槓各算一组）。"""
    return len(set_melds(melds))


def meld_set(m):
    """副露 -> ("tri", kind, open, kan) 或 ("run", start_kind, open, False)。"""
    ct = m["callType"]
    tiles = list(m.get("tiles") or ())
    if ct == "chi":
        ks = sorted(kind_of(t) for t in tiles)
        return ("run", ks[0], True, False)
    k = kind_of(tiles[0])
    return ("tri", k, ct != "ankan", ct in ("ankan", "kakan", "daiminkan"))


def menzen_of(melds):
    """门清 = 没有任何吃/碰/大明槓/加槓（暗槓不影响门清）。"""
    return not any(m.get("callType") in OPEN_TYPES for m in (melds or ()))


def state_of(melds, riichi=0):
    """立直 / 默听 / 副露。"""
    if not menzen_of(melds):
        return FURO
    return RIICHI if riichi else DAMATEN


def concealed_size(melds):
    """该副露数下，门清手牌应有的张数（不含和了张）。"""
    return 13 - 3 * n_sets(melds)


# ---------------------------------------------------------------- 牌型判别

def is_kokushi(counts):
    """国士無双：13 种幺九牌各一张，其中一种成对。"""
    if sum(counts) != 14:
        return False
    ok = False
    for k in KOKUSHI_KINDS:
        c = counts[k]
        if c == 0:
            return False
        if c == 2:
            ok = True
        elif c != 1:
            return False
    return ok and sum(counts[k] for k in KOKUSHI_KINDS) == 14


def kokushi_13wait(tiles13):
    """国士無双十三面待ち：和了前 13 种幺九牌各一张（役満倍数用）。"""
    counts = counts_of(tiles13)
    return len(tiles13) == 13 and all(counts[k] == 1 for k in KOKUSHI_KINDS)


def is_chiitoi(counts):
    """七対子：七个互不相同的对子（同种 4 张不算两个对子）。"""
    if sum(counts) != 14:
        return False
    return sum(1 for c in counts if c == 2) == 7


def decompose_with_pairs(counts, want_sets):
    """同 :func:`decompose`，但显式给出雀头：产 ``(pair_kind, sets)``。"""
    out = []
    for pair in range(34):
        if counts[pair] < 2:
            continue
        rest = list(counts)
        rest[pair] -= 2
        for sets in _extract_all(rest, want_sets):
            out.append((pair, sets))
    return out


def _extract_all(rest, left):
    res = []
    seen = set()

    def go(rest, left, acc):
        if left == 0:
            if any(rest):
                return
            key = tuple(sorted(acc))
            if key not in seen:
                seen.add(key)
                res.append(key)
            return
        i = 0
        while i < 34 and rest[i] == 0:
            i += 1
        if i >= 34:
            return
        if rest[i] >= 3:
            rest[i] -= 3
            go(rest, left - 1, acc + [("tri", i)])
            rest[i] += 3
        if i < 27 and i % 9 <= 6 and rest[i + 1] and rest[i + 2]:
            rest[i + 1] -= 1
            rest[i + 2] -= 1
            rest[i] -= 1
            go(rest, left - 1, acc + [("run", i)])
            rest[i] += 1
            rest[i + 1] += 1
            rest[i + 2] += 1

    go(list(rest), left, [])
    return res


def shapes_of(hand, melds=(), win_tile=None):
    """手上（含和了张）能凑成哪些和牌牌型，返回 shape 列表。"""
    tiles = list(hand) + ([win_tile] if win_tile is not None else [])
    counts = validate_tiles(tiles)
    if len(tiles) != concealed_size(melds) + 1:
        raise ValueError("手牌张数不对：%d 张（该副露数下应为 %d + 1）"
                         % (len(tiles), concealed_size(melds)))
    out = []
    if menzen_of(melds) and n_sets(melds) == 0:
        if is_kokushi(counts):
            out.append(KOKUSHI)
        if is_chiitoi(counts):
            out.append(CHIITOI)
    if decompose_with_pairs(counts, 4 - n_sets(melds)):
        out.append(MENTSU)
    return out


# ---------------------------------------------------------------- 起和役（m01701）

# 偶发 / 特殊役：判别器判「这一手有没有起和役」时不看它们（它们只在真和牌时额外加番）。
OCCASIONAL_YAKU = (2, 3, 4, 5, 6)           # 一発 / 槍槓 / 嶺上開花 / 海底摸月 / 河底撈魚
DORA_IDS = (52, 53, 54)                     # 宝牌 / 里宝牌 / 赤宝牌
GATE_IGNORED = OCCASIONAL_YAKU + DORA_IDS   # 不能用来满足起和条件的役


def min_yaku_ok(menzen, tsumo, state, ids):
    """起和役判定（18 种判别器与 score() 共用同一个函数，m01701）。

    ids 是某一拆解能成立的牌型役 id 列表（不含场况役与宝牌）：
    立直手（state == RIICHI）与门清自摸（門前清自摸和）自动满足，否则至少要有一个
    「非偶发、非宝牌」的役。副露手能成立的役都跟和了张/待ち形无关，所以这里不需要和了张。
    """
    if state == RIICHI:
        return True
    if tsumo and menzen:
        return True
    return any(i not in GATE_IGNORED for i in ids)


# ---------------------------------------------------------------- 18 种判别器

def _mk_disc(shape, mode, req_state):
    def disc(hand, melds=(), win_tile=None, riichi=0, state=None, **ctx):
        st = state if state is not None else state_of(melds, riichi)
        if st != req_state:
            return False
        if shape in (KOKUSHI, CHIITOI):
            if not menzen_of(melds) or n_sets(melds):
                return False
            # 国士無双 / 七対子 本身就是役 ⇒ 起和条件自动满足
            return shape in shapes_of(hand, melds, win_tile)
        if shape not in shapes_of(hand, melds, win_tile):
            return False
        # 起和役（m01701）：副露手必须另有真役；门清默听荣和也要有真役（平和依赖待ち形）
        return has_min_yaku(hand, melds, win_tile, tsumo=(mode == TSUMO),
                            seat_wind=ctx.get("seat_wind", EAST),
                            round_wind=ctx.get("round_wind", EAST),
                            state=st, riichi=riichi)
    disc.__name__ = "%s_%s_%s" % (_en(shape), _en(mode), _en(req_state))
    disc.__doc__ = "%s · %s · %s" % (shape, mode, req_state)
    return disc


def _en(name):
    table = {KOKUSHI: "kokushi", CHIITOI: "chiitoi", MENTSU: "mentsu",
             TSUMO: "tsumo", RON: "ron", RIICHI: "riichi", DAMATEN: "damaten",
             FURO: "furo"}
    return table[name]


DISCRIMINATORS = {}
for _shape in SHAPES:
    for _mode in MODES:
        for _state in STATES:
            _fn = _mk_disc(_shape, _mode, _state)
            DISCRIMINATORS[(_shape, _mode, _state)] = _fn
            globals()[_fn.__name__] = _fn


def check_all(hand, melds=(), win_tile=None, tsumo=True, riichi=0,
              seat_wind=EAST, round_wind=EAST):
    """返回所有成立的 ``(shape, mode, state)``（state 由副露/立直推出）。

    起和役（m01701）要判役牌，所以可以传自风/场风（默认東）。
    """
    mode = TSUMO if tsumo else RON
    st = state_of(melds, riichi)
    out = []
    for shape in SHAPES:
        if DISCRIMINATORS[(shape, mode, st)](hand, melds, win_tile, riichi=riichi,
                                             seat_wind=seat_wind, round_wind=round_wind):
            out.append((shape, mode, st))
    return out


def can_tsumo(hand, melds=(), win_tile=None, riichi=0, seat_wind=EAST, round_wind=EAST):
    """自摸判别器总入口：返回成立的 shape 列表（不细分 state）。"""
    st = state_of(melds, riichi)
    return [s for s in SHAPES
            if DISCRIMINATORS[(s, TSUMO, st)](hand, melds, win_tile, riichi=riichi,
                                              seat_wind=seat_wind, round_wind=round_wind)]


def can_ron(hand, melds=(), win_tile=None, riichi=0, seat_wind=EAST, round_wind=EAST):
    """荣和判别器总入口。"""
    st = state_of(melds, riichi)
    return [s for s in SHAPES
            if DISCRIMINATORS[(s, RON, st)](hand, melds, win_tile, riichi=riichi,
                                            seat_wind=seat_wind, round_wind=round_wind)]
# ---------------------------------------------------------------- 和牌张位置 / 符

WAIT_RYANMEN = "両面"
WAIT_KANCHAN = "嵌張"
WAIT_PENCHAN = "辺張"
WAIT_TANKI = "単騎"
WAIT_SHANPON = "双碰"

GREEN_KINDS = (19, 20, 21, 23, 25, 32)     # s2 s3 s4 s6 s8 發


def _set_kinds(s):
    """一组面子包含的 kind 列表（槓算 4 张同类）。"""
    if s[0] == "run":
        return [s[1], s[1] + 1, s[1] + 2]
    return [s[1]] * (4 if s[3] else 3)


def all_kinds(sets, pair):
    ks = []
    for s in sets:
        ks.extend(_set_kinds(s))
    ks.extend((pair, pair))
    return ks


def set_has_yaochu(s):
    if s[0] == "run":
        return s[1] % 9 in (0, 6)
    return is_yaochu_kind(s[1])


def wait_of_set(s, win_kind):
    """和了张落在该组里时的待ち形（顺子按 両面/嵌張/辺張，刻子=双碰）。"""
    if s[0] == "tri":
        return WAIT_SHANPON
    start = s[1]
    if win_kind == start + 1:
        return WAIT_KANCHAN
    if start % 9 == 0 and win_kind == start + 2:
        return WAIT_PENCHAN
    if start % 9 == 6 and win_kind == start:
        return WAIT_PENCHAN
    return WAIT_RYANMEN


def wait_fu(wait):
    # 待ちの符：嵌張/辺張/単騎 各 2 符、両面と双碰 0 符（天凤实测：双碰不加）
    return 2 if wait in (WAIT_KANCHAN, WAIT_PENCHAN, WAIT_TANKI) else 0


def calc_fu(sets, pair, wait, tsumo, menzen, pinfu, seat_wind, round_wind):
    """符计算（天凤段位战：連風牌雀头 4 符（自风 2 + 场风 2），食い平和型 30 符，平和自摸 20 符）。"""
    fu = 20
    if tsumo and not pinfu:
        fu += 2            # 自摸 2 符；平和型不加
    if menzen and not tsumo:
        fu += 10           # 門前清栄和 +10（平和荣和也是 30 符）
    fu += wait_fu(wait)
    if pair in DRAGONS:
        fu += 2
    if pair == seat_wind:
        fu += 2
    if pair == round_wind:
        fu += 2
    for s in sets:
        if s[0] != "tri":
            continue
        kind, open_, kan = s[1], s[2], s[3]
        yao = is_yaochu_kind(kind)
        if kan:
            fu += 32 if (not open_ and yao) else (16 if (not open_ or yao) else 8)
        else:
            fu += 8 if (not open_ and yao) else (4 if (not open_ or yao) else 2)
    if fu == 20 and not pinfu:
        fu = 30
    return ((fu + 9) // 10) * 10


# ---------------------------------------------------------------- 役判定（面子手）

def mentsu_yaku(sets, pair, wait, tsumo, menzen, seat_wind, round_wind):
    """普通役（不含立直/一発/海底等场况役与宝牌），返回 [(id, 番)]。"""
    out = []
    kinds = all_kinds(sets, pair)
    runs = [s for s in sets if s[0] == "run"]
    tris = [s for s in sets if s[0] == "tri"]
    tri_kinds = [s[1] for s in tris]
    kans = [s for s in tris if s[3]]
    starts = [s[1] for s in runs]
    has_honor = any(is_honor_kind(k) for k in kinds)
    suits = set(k // 9 for k in kinds if k < 27)
    closed_tris = [i for i, s in enumerate(tris) if not s[2]]

    # 役満（先判定，命中就不再算普通役）
    if len(tris) == 4 and all(is_honor_kind(s[1]) for s in tris):
        return [(42, 0)]                       # 字一色
    if all(is_terminal_kind(k) for k in kinds):
        return [(44, 0)]                       # 清老頭
    if all(k in GREEN_KINDS for k in kinds):
        return [(43, 0)]                       # 緑一色
    dragons = [s for s in tris if s[1] in DRAGONS]
    winds = [s for s in tris if s[1] in WINDS]
    if len(dragons) == 3:
        return [(39, 0)]                       # 大三元
    if len(winds) == 4:
        return [(49, 0)]                       # 大四喜（双倍）
    if len(winds) == 3 and pair in WINDS:
        return [(50, 0)]                       # 小四喜
    if len(kans) >= 4:
        return [(51, 0)]                       # 四槓子
    if len(tris) == 4 and len(closed_tris) == 4:
        return [(41, 0)] if wait == WAIT_TANKI else [(40, 0)]   # 四暗刻単騎 / 四暗刻

    # 普通役
    if all(is_simple_kind(k) for k in kinds):
        out.append((8, 1))                        # 断幺九
    pinfu = (menzen and len(runs) == 4 and wait == WAIT_RYANMEN
             and pair not in DRAGONS and pair != seat_wind and pair != round_wind)
    if pinfu:
        out.append((7, 1))                        # 平和
    for s in tris:
        if s[1] in DRAGONS:
            out.append((18 + (s[1] - 31), 1))     # 役牌 白/發/中
        if s[1] == seat_wind:
            out.append((10 + WINDS.index(seat_wind), 1))   # 自風
        if s[1] == round_wind:
            out.append((14 + WINDS.index(round_wind), 1))  # 場風
    if menzen:
        seen = {}
        for st in starts:
            seen[st] = seen.get(st, 0) + 1
        pairs = sum(c // 2 for c in seen.values())
        if pairs >= 2:
            out.append((32, 3))                   # 二盃口（不叠加一盃口）
        elif pairs == 1:
            out.append((9, 1))                    # 一盃口（同种顺子 3 组也只算 1 番）
    # 三色同順 / 一気通貫
    if any(all((r + 9 * i) in starts for i in range(3)) for r in range(7)):
        out.append((25, 2 if menzen else 1))
    if any(all((9 * s + 3 * i) in starts for i in range(3)) for s in range(3)):
        out.append((24, 2 if menzen else 1))
    # 混全帯幺九 / 純全帯幺九
    if all(set_has_yaochu(s) for s in sets) and is_yaochu_kind(pair):
        if has_honor:
            out.append((23, 2 if menzen else 1))
        else:
            out.append((33, 3 if menzen else 2))
    if all(is_yaochu_kind(k) for k in kinds):
        if len(tris) == 4:
            out.append((31, 2))                   # 混老頭
    if len(tris) == 4:
        out.append((28, 2))                       # 対々和
    if len(closed_tris) >= 3:
        out.append((29, 2))                       # 三暗刻
    if any(all((r + 9 * i) in tri_kinds for i in range(3)) for r in range(9)):
        out.append((26, 2))                       # 三色同刻
    if len(kans) >= 3:
        out.append((27, 2))                       # 三槓子
    if len(dragons) == 2 and pair in DRAGONS:
        out.append((30, 2))                       # 小三元
    # 混一色 / 清一色
    if not has_honor and len(suits) == 1:
        out.append((35, 6 if menzen else 5))      # 清一色
    elif has_honor and len(suits) == 1:
        out.append((34, 3 if menzen else 2))      # 混一色
    return out


def kokushi_yaku(tiles13):
    """国士無双（13 面待ち = 双倍役満）。"""
    return 48 if kokushi_13wait(tiles13) else 47


def chiitoi_yaku(counts, menzen):
    """七対子（2 番）+ 混老頭/断幺九 + 混一色/清一色。"""
    kinds = []
    for k, c in enumerate(counts):
        kinds.extend([k] * c)
    out = [(22, 2)]
    if all(is_yaochu_kind(k) for k in kinds):
        out.append((31, 2))                       # 混老頭
    if all(is_simple_kind(k) for k in kinds):
        out.append((8, 1))                        # 断幺九
    has_honor = any(is_honor_kind(k) for k in kinds)
    suits = set(k // 9 for k in kinds if k < 27)
    if not has_honor and len(suits) == 1:
        out.append((35, 6 if menzen else 5))
    elif has_honor and len(suits) == 1:
        out.append((34, 3 if menzen else 2))
    return out


def yaku_ids_of_sets(sets, pair, melds=(), tsumo=True, seat_wind=EAST, round_wind=EAST,
                     menzen=None):
    """一组拆解（手牌面子 + 副露）能成立的牌型役 id 列表（不含场况役/宝牌）。

    sets 是 agari 面子格式的元组列表（手牌里拆出的面子），副露面子由 melds 补上。
    待ち形固定按両面传 —— 副露手能成立的役都与待ち形无关；门清手请用判别器（门清自摸/立直
    直接通过，默听荣和才需要看待ち形，那种情况下用 has_min_yaku）。
    """
    all_sets = list(sets) + [meld_set(m) for m in set_melds(melds)]
    yaku = mentsu_yaku(all_sets, pair, WAIT_RYANMEN, tsumo,
                       menzen_of(melds) if menzen is None else bool(menzen),
                       seat_wind, round_wind)
    return [i for i, _h in yaku]


def sets_min_yaku_ok(sets, pair, melds=(), tsumo=True, seat_wind=EAST, round_wind=EAST,
                     state=None, riichi=0, menzen=None):
    """按一组拆解判起和役（判别器内核的「已知拆解」版本，向听计算的叶子用）。

    与 18 种判别器里的 has_min_yaku 调用同一个 min_yaku_ok，口径完全一致；
    省掉了重新拆牌，供向听搜索逐计划调用。
    """
    st = state if state is not None else state_of(melds, riichi)
    menzen = menzen_of(melds) if menzen is None else bool(menzen)
    if min_yaku_ok(menzen, tsumo, st, ()):
        return True
    return min_yaku_ok(menzen, tsumo, st,
                       yaku_ids_of_sets(sets, pair, melds, tsumo, seat_wind, round_wind, menzen))


def ctx_yaku(tsumo, menzen, ctx, riichi, all_tiles):
    """场况役 + 宝牌：立直/一発/門前清自摸和/槍槓/嶺上/海底/河底/天和/地和/人和 + 宝牌。"""
    out = []
    if ctx.get("tenhou"):
        return [(37, 0)]
    if ctx.get("chiihou"):
        return [(38, 0)]
    if ctx.get("renhou"):
        return [(36, 0)]
    if riichi == 2:
        out.append((21, 2))                       # 両立直
    elif riichi == 1:
        out.append((1, 1))                        # 立直
    if riichi and ctx.get("ippatsu"):
        out.append((2, 1))
    if tsumo and menzen:
        out.append((0, 1))                        # 門前清自摸和
    if ctx.get("chankan") and not tsumo:
        out.append((3, 1))
    if ctx.get("rinshan") and tsumo:
        out.append((4, 1))
    if ctx.get("haitei") and tsumo:
        out.append((5, 1))
    if ctx.get("houtei") and not tsumo:
        out.append((6, 1))
    return out


def dora_yaku(ctx, riichi, all_tiles):
    """宝牌 / 里宝牌（仅立直）/ 赤宝牌。"""
    out = []
    n = dora_count(ctx.get("dora") or (), all_tiles)
    if n:
        out.append((52, n))
    if riichi:
        n = dora_count(ctx.get("ura") or (), all_tiles)
        if n:
            out.append((53, n))
    aka = sum(1 for t in all_tiles if is_red(t))
    if aka:
        out.append((54, aka))
    return out
# ---------------------------------------------------------------- 打点

def ceil100(x):
    """天凤的点数都是 100 的倍数（往上取整）。"""
    return ((x + 99) // 100) * 100


def base_points(han, fu):
    """番/符 -> 基本点（天凤无切り上げ満貫；5 番以上按番数跳）。"""
    if han >= 13:
        return 8000
    if han >= 11:
        return 6000
    if han >= 8:
        return 4000
    if han >= 6:
        return 3000
    if han >= 5:
        return 2000
    return min(fu * (1 << (2 + han)), 2000)


def is_pinfu(sets, pair, wait, menzen, seat_wind, round_wind):
    return (menzen and len(sets) == 4 and all(s[0] == "run" for s in sets)
            and wait == WAIT_RYANMEN and pair not in DRAGONS
            and pair != seat_wind and pair != round_wind)


def is_chuuren(counts):
    """九蓮宝燈形：门清单色数牌，计数 = 1112345678999 + 任意一张。"""
    ks = [k for k, c in enumerate(counts) if c]
    if not ks:
        return None
    suit = ks[0] // 9
    if suit > 2 or any(k // 9 != suit for k in ks):
        return None
    need = {0: 3, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 3}
    diff = 0
    for i in range(9):
        d = counts[suit * 9 + i] - need[i]
        if d < 0:
            return None
        diff += d
    return diff == 1


def chuuren_pure(counts):
    """純正九蓮宝燈：和了前的 13 张恰好是 1112345678999。"""
    ks = [k for k, c in enumerate(counts) if c]
    if not ks or ks[0] // 9 > 2:
        return False
    suit = ks[0] // 9
    need = {0: 3, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 3}
    return all(counts[suit * 9 + i] == need[i] for i in range(9))


def win_candidates(hand, melds=(), win_tile=None, tsumo=True, seat_wind=EAST, round_wind=EAST,
                   menzen=None):
    """枚举所有和牌拆解（``hand`` = 不含和了张的门清手牌，``win_tile`` = 和了张）。

    返回项与 ``score()`` 的 ``cands`` 同格式：``shape/wait/yaku/han/fu/yakuman_mult/seki``；
    一个拆解都不成立时返回空列表。**不含**场况役与宝牌（那些与拆解无关，由 ``score()`` 另加）。

    ``menzen`` = None 时按 ``melds`` 推断；显式传 False 时**强制按副露手算**（门清役
    平和 / 一盃口 / 門前清自摸和 / 国士 / 七対子 / 九蓮 都不成立，符也没有门清加符），
    用于「门清手牌按副露假设计算」的期望特征（用户 m02075）。
    """
    if win_tile is None:
        raise ValueError("必须给出和了张 win_tile")
    concealed = list(hand)
    counts = validate_tiles(concealed + [win_tile])
    mels = set_melds(melds)
    menzen = menzen_of(melds) if menzen is None else bool(menzen)
    want_sets = 4 - len(mels)
    win_kind = kind_of(win_tile)
    cands = []
    # ---- 国士無双
    if menzen and not mels and is_kokushi(counts):
        yk = kokushi_yaku(concealed)
        cands.append({"shape": KOKUSHI, "wait": "単騎" if yk == 48 else "十三面",
                      "yaku": [(yk, 0)], "han": 0, "fu": 0, "yakuman_mult": 2 if yk == 48 else 1,
                      "seki": None})
    # ---- 七対子
    if menzen and not mels and is_chiitoi(counts):
        y = chiitoi_yaku(counts, menzen)
        cands.append({"shape": CHIITOI, "wait": "単騎", "yaku": y,
                      "han": sum(h for _i, h in y), "fu": 25, "yakuman_mult": 0, "seki": None})
    # ---- 面子手
    for pair, csets in decompose_with_pairs(counts, want_sets):
        placements = []
        # 和了张的三种读法全部枚举（符/番不同 ⇒ 打点不同，由最大原则挑选）：
        #   ① 落进顺子 = 両面/嵌張/辺張；② 落进刻子 = 双碰；③ 与手里的单张组成雀头 = 単騎。
        # 注意：手里同种已有 3 张时照样能读成単騎（例：1123567m + 1m 自模 = 11m 雀头 + 123m 顺子），
        # 因此不能按「手里恰好 2 张」之类的條件提前剪枝（用户 m01164 指正）。
        if pair == win_kind:
            placements.append(("pair", None))
        for i, s in enumerate(csets):
            if s[0] == "run":
                if win_kind in (s[1], s[1] + 1, s[1] + 2):
                    placements.append(("set", i))
            elif s[1] == win_kind:
                placements.append(("set", i))
        for where, idx in placements:
            sets = []
            for m in mels:
                sets.append(meld_set(m))
            for j, s in enumerate(csets):
                if s[0] == "run":
                    sets.append(("run", s[1], False, False))
                else:
                    flip = (not tsumo) and where == "set" and j == idx
                    sets.append(("tri", s[1], flip, False))
            if where == "pair":
                wait = WAIT_TANKI
            else:
                wait = wait_of_set(csets[idx], win_kind)
            pinfu = is_pinfu(sets, pair, wait, menzen, seat_wind, round_wind)
            fu = calc_fu(sets, pair, wait, tsumo, menzen, pinfu, seat_wind, round_wind)
            y = mentsu_yaku(sets, pair, wait, tsumo, menzen, seat_wind, round_wind)
            if menzen and is_chuuren(counts):
                # 純正 = 和了前的 13 张恰好是 1112345678999
                y = [(46, 0)] if chuuren_pure(counts_of(concealed)) else [(45, 0)]
            cands.append({"shape": MENTSU, "wait": wait, "yaku": y,
                          "han": sum(h for _i, h in y), "fu": fu,
                          "yakuman_mult": 0, "seki": (sets, pair)})

    return cands


def has_min_yaku(hand, melds=(), win_tile=None, tsumo=True, seat_wind=EAST, round_wind=EAST,
                 state=None, riichi=0, menzen=None):
    """手牌 + （可选）和了张能否满足起和条件（m01701）：牌型 + 起和役。

    ``win_tile`` 省略时手牌必须是完整的 14-3n 张（``can_tsumo`` 等的用法）：门清手直接通过
    （門前清自摸和 / 立直），副露手枚举拆解找真役 —— 和了张不明时按「不看待ち形」判，
    因为副露手能成立的役都与待ち形无关。
    """
    st = state if state is not None else state_of(melds, riichi)
    menzen = menzen_of(melds) if menzen is None else bool(menzen)
    if min_yaku_ok(menzen, tsumo, st, ()):
        return True
    if win_tile is not None:
        for c in win_candidates(hand, melds, win_tile, tsumo, seat_wind, round_wind, menzen):
            if min_yaku_ok(menzen, tsumo, st, [i for i, _h in c["yaku"]]):
                return True
        return False
    mels = set_melds(melds)
    counts = validate_tiles(list(hand))
    if menzen and not mels and (is_kokushi(counts) or is_chiitoi(counts)):
        return True
    for pair, csets in decompose_with_pairs(counts, 4 - len(mels)):
        sets = [("run", s[1], False, False) if s[0] == "run" else ("tri", s[1], False, False)
                for s in csets]
        if sets_min_yaku_ok(sets, pair, melds, tsumo, seat_wind, round_wind, state=st, menzen=menzen):
            return True
    return False


def score(hand, melds=(), win_tile=None, tsumo=True, oya=False, honba=0, kyotaku=0,
          seat_wind=EAST, round_wind=EAST, riichi=0, ctx=None, state=None, menzen=None):
    """和牌判定 + 符/番/打点。

    ``hand`` 为不含和了张的门清手牌（13-3n 张），``win_tile`` 为和了张（自摸=摸到的牌，
    荣和=他家打出的牌）。返回 dict：``shape/mode/state/han/fu/yakuman/yaku/base/gain/payments/wait/cands``。

    起和役（m01701）：只有通过判别器判定的拆解才进入得点计算，一个都没有时抛
    ``ValueError("役なし：…")``；``cands`` 里列出的也是通过起和役的拆解。
    """
    if win_tile is None:
        raise ValueError("必须给出和了张 win_tile")
    ctx = merge_ctx(ctx)
    concealed = list(hand)
    tiles = concealed + [win_tile]
    validate_tiles(tiles)
    mels = set_melds(melds)
    menzen = menzen_of(melds) if menzen is None else bool(menzen)
    st = state if state is not None else state_of(melds, riichi)
    win_kind = kind_of(win_tile)
    all_tiles = tiles + [t for m in mels for t in (m.get("tiles") or ())]
    mode = TSUMO if tsumo else RON

    all_cands = win_candidates(concealed, melds, win_tile, tsumo, seat_wind, round_wind, menzen)
    if not all_cands:
        raise ValueError("并未和牌：手牌 %s + %s" % (concealed, kind_name(win_kind)))
    # 起和役（m01701）：只有判别器放行的拆解才允许进入得点计算（与 18 种判别器同用 min_yaku_ok）
    cands = [c for c in all_cands
             if min_yaku_ok(menzen, tsumo, st, [i for i, _h in c["yaku"]])]
    if not cands:
        raise ValueError("役なし：和牌牌型成立，但没有任何役（手牌 %s + %s）"
                         % (concealed, kind_name(win_kind)))

    def total_of(c):
        yk = [i for i, h in c["yaku"] if h == 0]
        if yk:
            return 8000 * (c.get("yakuman_mult") or 1)
        if ctx.get("tenhou") or ctx.get("chiihou") or ctx.get("renhou"):
            return 8000                             # 场况役満
        han = c["han"] + sum(h for _i, h in ctx_yaku(tsumo, menzen, ctx, riichi, all_tiles)) \
            + sum(h for _i, h in dora_yaku(ctx, riichi, all_tiles))
        return base_points(han, c["fu"]) * 4

    best = max(cands, key=total_of)

    yaku = [(i, h) for i, h in best["yaku"]]
    yaku += ctx_yaku(tsumo, menzen, ctx, riichi, all_tiles)
    yaku += dora_yaku(ctx, riichi, all_tiles)
    yk_ids = [i for i, h in yaku if h == 0]         # 牌型的役満 + 天和/地和/人和
    if yk_ids:
        yaku = [(i, 0) for i in yk_ids]
        mult = sum(2 if i in DOUBLE_YAKUMAN_IDS else 1 for i in yk_ids)
        han, fu = 0, 0
        base = 8000 * mult                          # 双倍役満（国士十三面/純正九蓮/四暗刻単騎/大四喜）
    else:
        han = sum(h for _i, h in yaku)
        fu = best["fu"]
        mult = 0
        if han == 0:
            raise ValueError("役なし：和牌牌型成立，但没有任何役（手牌 %s + %s）"
                             % (concealed, kind_name(win_kind)))
        base = base_points(han, fu)

    pay = payment_of(base, oya, tsumo, honba, kyotaku)
    return {
        "shape": best["shape"], "mode": mode, "state": st,
        "han": han, "fu": fu, "yakuman": mult, "yaku": [(i, h, yaku_name(i)) for i, h in yaku],
        "base": base, "gain": pay["self"], "payments": pay["payments"],
        "wait": best["wait"], "tiles": tiles, "melds": mels, "detail": best.get("seki"),
        "menzen": menzen, "oya": oya, "honba": honba, "kyotaku": kyotaku,
        # 通过起和役的候选拆解（「最大原则」测试用）：base 必须是这些 total 中的最大值
        "cands": [{"shape": c["shape"], "wait": c["wait"], "yaku": list(c["yaku"]),
                   "han": c["han"], "fu": c["fu"], "yakuman_mult": c["yakuman_mult"],
                   "total": total_of(c)} for c in cands],
    }


def evaluate(hand, melds=(), win_tile=None, tsumo=True, oya=False, honba=0, kyotaku=0,
             seat_wind=EAST, round_wind=EAST, riichi=0, ctx=None, state=None, menzen=None):
    """一次候选枚举同时得到「是否满足起和役」与打点（用户 m02073：别把枚举跑两遍）。

    通过起和役 -> ``score()`` 的返回 dict；牌型不成立或没有役 -> None。
    """
    try:
        return score(hand, melds, win_tile, tsumo, oya, honba, kyotaku, seat_wind, round_wind,
                     riichi, ctx, state, menzen)
    except ValueError:
        return None


def payment_of(base, oya, tsumo, honba=0, kyotaku=0):
    """基本点 -> 和了者的净得点与各家的失点（天凤：本场 自摸每家 +100 / 荣和放铳 +300）。"""
    pay = {"self": 0, "payments": {}}
    if tsumo:
        each = ceil100(base * 2) + 100 * honba
        if oya:
            pay["payments"] = {"dealer": each, "children": [each, each]}
            pay["self"] = each * 3 + 1000 * kyotaku
        else:
            others = ceil100(base) + 100 * honba
            pay["payments"] = {"dealer": each, "children": [others, others]}
            pay["self"] = each + others * 2 + 1000 * kyotaku
        pay["payments"] = dict((k, -v if isinstance(v, int) else [-x for x in v])
                               for k, v in pay["payments"].items())
    else:
        loser = ceil100(base * (6 if oya else 4)) + 300 * honba
        pay["payments"] = {"loser": -loser}
        pay["self"] = loser + 1000 * kyotaku
    return pay


def seat_deltas(result, seat, n=4, oya_seat=None, loser=None):
    """把 payments 摊到 n 个座位（供托/本场已算在 result["gain"] 里）。

    ``seat`` = 和了者座位，``oya_seat`` = 亲家座位（自摸时用来区分亲/子失点），
    ``loser`` = 荣和时的放铳者座位。缺省按「和了者的下一家」猜，只在与实际相符时才对。
    """
    dels = [0] * n
    dels[seat] = result["gain"]
    p = result["payments"]
    if "loser" in p:
        dels[(seat + 1) % n if loser is None else loser % n] = p["loser"]
        return dels
    oya_seat = (seat + 1) % n if oya_seat is None else oya_seat % n
    if result["oya"]:
        for i in range(1, n):
            dels[(seat + i) % n] = p["children"][0]
    else:
        dels[oya_seat] = p["dealer"]
        for i in range(n):
            if i != seat and i != oya_seat:
                dels[i] = p["children"][0]
    return dels
