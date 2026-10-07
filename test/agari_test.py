# -*- coding: utf-8 -*-
r"""agari 正式测试（第 15 轮：和牌判别器 + 点数计算器，天凤段位战规则）。

覆盖：
  1. 18 种判别器（国士無双 / 七対子 / 面子手 × 自摸 / 荣和 × 立直 / 默听 / 副露）
     含起和役判定（m01701）：副露手必须有真役、门清默听也必须满足起和条件、立直/门清自摸自动放行、
     宝牌与偶发役（一发/里宝/槍槓/嶺上/海底/河底）不算役
  2. 符计算（平和 20/30 符、双碰 0 符、単騎/嵌張/辺張 +2、刻子/槓符、連風雀头、七対子 25 符）
  3. 点数计算（基本点跳档、亲/子、本场、供托、无切り上げ満貫、役満倍数、役なし报错）
  4. 宝牌/里宝牌/赤宝牌（is_red 修正回归）与同种 4 张上限
  5. 全量校验：data\ 5 个基础牌谱 + data_extra\ 66 个校验语料，共 640 个和牌事件
     （符/番/役/得点/4 家配分逐例一致）+ 545 个立直宣言必定听牌

运行：
  & 'D:\coding\anaconda3\envs\py314_null\python.exe' test\agari_test.py
"""
import collections
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import agari, mjlog, replay  # noqa: E402
from mjscore.agari import (  # noqa: E402
    CHIITOI, DAMATEN, DISCRIMINATORS, FURO, KOKUSHI, MENTSU, RIICHI, RON,
    SHAPES, STATES, TSUMO, WAIT_KANCHAN, WAIT_PENCHAN, WAIT_RYANMEN,
    WAIT_SHANPON, WAIT_TANKI, base_points, calc_fu, can_ron, can_tsumo, ceil100,
    check_all, dora_count, payment_of, score, seat_deltas, shapes_of,
    validate_tiles, wait_fu,
)
from mjscore.mjlog import is_red, kind_of  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK = [0]
BAD = [0]


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   %s" % label)
    else:
        BAD[0] += 1
        print("  FAIL %s" % label)
    return bool(cond)


def eq(got, want, label):
    return check(got == want, "%s（got %r / want %r）" % (label, got, want))


def fails(fn, label):
    """期望抛 ValueError。"""
    try:
        fn()
    except ValueError:
        return check(True, label)
    except Exception as exc:                      # noqa: BLE001
        return check(False, "%s（异常类型不对：%r）" % (label, exc))
    return check(False, "%s（未抛异常）" % label)


# ---------------------------------------------------------------- 牌张小工具

EAST, SOUTH, WEST, NORTH = 27, 28, 29, 30
HAKU, HATSU, CHUN = 31, 32, 33


def T(*ks):
    """kind 序列 -> 牌 id 序列。

    同种牌按出现顺序取倒数第 0,1,2,3 张：5m/5p/5s 的首选 id 不是赤宝牌的 16/52/88，
    所以只有显式写出 16/52/88、或用满 4 张时才会出现赤宝牌。
    """
    seen = {}
    out = []
    for k in ks:
        i = seen.get(k, 0)
        seen[k] = i + 1
        if i > 3:
            raise ValueError("%s 超过 4 张" % agari.kind_name(k))
        out.append(k * 4 + (3 - i))
    return out


def meld(call_type, *ks):
    """副露 dict（与 replay 状态里 players[i]["melds"] 的元素同构）。"""
    return {"callType": call_type, "tiles": T(*ks), "calledId": None, "from": None,
            "open": call_type != "ankan"}


# ------------------------------------------------------------------ 1
print("=== 1. 18 种判别器 ===")
COMBOS = [(s, m, st) for s in SHAPES for m in agari.MODES for st in agari.STATES]
eq(agari.SHAPES, (KOKUSHI, CHIITOI, MENTSU), "三种牌型")
eq(agari.MODES, (TSUMO, RON), "两种和牌方式")
eq(agari.STATES, (RIICHI, DAMATEN, FURO), "三种状态")
eq(len(DISCRIMINATORS), 18, "判别器总数 = 3 × 2 × 3")
eq(sorted(DISCRIMINATORS.keys()) == sorted(COMBOS), True, "判别器键为全组合")
for _s, _m, _st in COMBOS:
    _fn = DISCRIMINATORS[(_s, _m, _st)]
    eq(_fn.__name__, "%s_%s_%s" % (agari._en(_s), agari._en(_m), agari._en(_st)),
       "判别器名 %s / %s / %s" % (_s, _m, _st))
    eq(getattr(agari, _fn.__name__, None) is _fn, True, "已导出到模块全局：%s" % _fn.__name__)

KOKU = T(0, 8, 9, 17, 18, 26, EAST, SOUTH, WEST, NORTH, HAKU, HATSU, CHUN)
eq(len(KOKU), 13, "国士牌例 13 张（13 种各 1 张）")
eq(can_tsumo(KOKU, win_tile=T(CHUN)[0]), [KOKUSHI], "国士無双・自摸（默听）")
eq(can_ron(KOKU, win_tile=T(CHUN)[0]), [KOKUSHI], "国士無双・荣和（默听）")
eq(check_all(KOKU, win_tile=T(CHUN)[0], tsumo=True, riichi=1),
   [(KOKUSHI, TSUMO, RIICHI)], "国士無双・立直自摸")
eq(check_all(KOKU, win_tile=T(CHUN)[0], tsumo=False), [(KOKUSHI, RON, DAMATEN)],
   "国士無双・默听荣和（状态推出）")
KOKU1 = T(0, 0, 8, 9, 17, 18, 26, EAST, SOUTH, WEST, NORTH, HAKU, HATSU)
eq(can_ron(KOKU1, win_tile=T(CHUN)[0]), [KOKUSHI], "国士無双・単骑（1m 成对，非十三面）")
eq(agari.kokushi_13wait(KOKU), True, "十三面判定：13 种各 1 张")
eq(agari.kokushi_13wait(KOKU1), False, "十三面判定：存在对子")

CHI = T(0, 0, 9, 9, 18, 18, EAST, EAST, SOUTH, SOUTH, WEST, WEST, HAKU)
eq(len(CHI), 13, "七対子牌例 13 张（6 対 + 1 张单骑）")
eq(can_ron(CHI, win_tile=T(HAKU)[0]), [CHIITOI], "七対子・荣和")
eq(can_tsumo(CHI, win_tile=T(HAKU)[0]), [CHIITOI], "七対子・自摸")
eq(check_all(CHI, win_tile=T(HAKU)[0], tsumo=True, riichi=1), [(CHIITOI, TSUMO, RIICHI)],
   "七対子・立直自摸")
R = score(CHI, win_tile=T(HAKU)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["fu"], R["han"], [y[0] for y in R["yaku"]]), (25, 5, [22, 31, 0]),
   "七対子 = 25 符 / 七対子 + 混老頭 + 門前清自摸和 = 5 番")
eq(R["gain"], 8000, "七対子 5 番 子家自摸 = 2000/4000（共 8000）")

PIN = T(0, 1, 2, 3, 4, 5, 15, 16, 17, 12, 13, 19, 19)
eq(len(PIN), 13, "面子手牌例 13 张（123m 456m 789p 45p 22s）")
eq(can_tsumo(PIN, win_tile=T(11)[0]), [MENTSU], "面子手・自摸")
eq(check_all(PIN, win_tile=T(11)[0], tsumo=False, riichi=1), [(MENTSU, RON, RIICHI)],
   "面子手・立直荣和")
eq(can_ron(PIN, win_tile=T(CHUN)[0]), [], "未和牌的一手返回空")
FUHAND = T(0, 1, 2, 3, 4, 5, 12, 13, 16, 16)
PON2S = meld("pon", 19, 19, 19)
PONHAKU = meld("pon", HAKU, HAKU, HAKU)
# m01701 起和役：FUHAND = 123m 456m 345p 88p + 碰 2s，形已和但没有任何役
eq(can_tsumo(FUHAND, melds=[PON2S], win_tile=T(11)[0]), [], "副露手无役：形和也不放行（m01701）")
eq(can_ron(FUHAND, melds=[PON2S], win_tile=T(11)[0]), [], "副露手无役荣和：不放行（m01701）")
eq(can_tsumo(FUHAND, melds=[PONHAKU], win_tile=T(11)[0]), [MENTSU], "副露手有役（役牌 白）：放行")
eq(check_all(FUHAND, melds=[PONHAKU], win_tile=T(11)[0], tsumo=True), [(MENTSU, TSUMO, FURO)],
   "副露状态推出（有役）")
# 起和条件：门清自摸 = 門前清自摸和（放行）/ 门清默听荣和无役（不放行）/ 立直本身就是役（放行）
NOY13 = T(0, 1, 2, 3, 4, 5, 15, 16, 17, 19, 19, 21, 23)
eq(can_ron(NOY13, win_tile=T(22)[0]), [], "门清默听荣和无役：不放行（m01701）")
eq(can_tsumo(NOY13, win_tile=T(22)[0]), [MENTSU], "门清自摸（門前清自摸和）：放行")
eq(check_all(NOY13, win_tile=T(22)[0], tsumo=False, riichi=1), [(MENTSU, RON, RIICHI)],
   "立直（本身就是役）：无役也放行")
fails(lambda: score(FUHAND, [PON2S], win_tile=T(11)[0], tsumo=True, seat_wind=EAST,
                    round_wind=SOUTH, ctx={"dora": [T(4)[0]]}),
      "副露手只有宝牌没有役 -> 不放行（m01701 起和条件）")
eq(agari.n_sets([PON2S, meld("ankan", 0, 0, 0, 0)]), 2, "碰 + 暗槓 = 2 组面子")
eq(agari.concealed_size([PON2S]), 10, "1 组副露 -> 门清手牌 10 张")
eq(agari.state_of([meld("ankan", HAKU, HAKU, HAKU, HAKU)]), DAMATEN, "暗槓不影响门清（默听）")
eq(agari.state_of([PON2S]), FURO, "碰 -> 副露状态")
eq(DISCRIMINATORS[(KOKUSHI, TSUMO, FURO)](
    T(0, 8, 9, 17, 18, 26, EAST, SOUTH, WEST, NORTH), melds=[meld("chi", 0, 1, 2)],
    win_tile=T(CHUN)[0]), False, "国士無双・副露 恒为假（不可能存在）")
eq(DISCRIMINATORS[(CHIITOI, RON, FURO)](
    T(0, 0, 9, 9, 18, 18, EAST, EAST, SOUTH, SOUTH), melds=[meld("chi", 0, 1, 2)],
    win_tile=T(WEST)[0]), False, "七対子・副露 恒为假（不可能存在）")
fails(lambda: shapes_of(T(*range(13)), win_tile=None), "门清 13 张未给和了张 -> ValueError")
fails(lambda: validate_tiles([0, 1, 2, 3, 0]), "同种 5 张 -> ValueError")
# ------------------------------------------------------------------ 2
print("=== 2. 符计算 ===")
eq(wait_fu(WAIT_RYANMEN), 0, "両面待ち 0 符")
eq(wait_fu(WAIT_SHANPON), 0, "双碰待ち 0 符（天凤实测：13 例不符都是双碰多算 2 符造成的）")
eq(wait_fu(WAIT_KANCHAN), 2, "嵌張待ち 2 符")
eq(wait_fu(WAIT_PENCHAN), 2, "辺張待ち 2 符")
eq(wait_fu(WAIT_TANKI), 2, "単騎待ち 2 符")

R = score(PIN, win_tile=T(11)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["fu"], R["han"], R["wait"]), (20, 2, WAIT_RYANMEN),
   "平和自摸 = 20 符 2 番（平和 1 + 門前清自摸和 1）")
eq((R["base"], R["gain"], R["payments"]),
   (320, 1500, {"dealer": -700, "children": [-400, -400]}),
   "平和自摸 20 符 2 番 子家 = 400/700（共 1500）")
R = score(PIN, win_tile=T(11)[0], tsumo=False, seat_wind=EAST, round_wind=SOUTH)
eq((R["fu"], R["han"], R["gain"]), (30, 1, 1000),
   "平和荣和 = 30 符 1 番（門前清栄和 +10）子家 1000")

TANKI = T(0, 1, 2, 12, 13, 14, 24, 25, 26, 19, 20, 21, HAKU)
R = score(TANKI, win_tile=124, tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["wait"], R["fu"], R["han"]), (WAIT_TANKI, 30, 1),
   "単騎 2 符 + 役牌雀头 2 符：20+2+2+2 = 26 -> 30 符（白只是雀头不算役，仅門前清自摸和 1 番）")

SHANPON = T(0, 1, 2, 12, 13, 14, 24, 25, 26, 19, 19, HAKU, HAKU)
R = score(SHANPON, win_tile=124, tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["wait"], R["fu"], R["han"]), (WAIT_SHANPON, 30, 2),
   "双碰 0 符：20+2(自摸)+8(白暗刻) = 30 符（双碰若算 2 符则为 40，此例可判别）")

KANCHAN = T(0, 1, 2, 12, 13, 14, 24, 25, 26, 21, 23, 19, 19)
R = score(KANCHAN, win_tile=T(22)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["wait"], R["fu"], R["han"]), (WAIT_KANCHAN, 30, 1),
   "嵌張 2 符：20+2(自摸)+2 = 24 -> 30 符（无平和，仅門前清自摸和 1 番）")

PENCHAN = T(0, 1, 2, 12, 13, 14, 24, 25, 26, 18, 19, 22, 22)
R = score(PENCHAN, win_tile=T(20)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["wait"], R["fu"], R["han"]), (WAIT_PENCHAN, 30, 1), "辺張 2 符（12s 和 3s）：24 -> 30 符")

RUNS4 = [("run", 0, False, False), ("run", 3, False, False),
         ("run", 6, False, False), ("run", 9, False, False)]
eq(calc_fu(RUNS4, 19, WAIT_RYANMEN, True, True, True, NORTH, NORTH), 20,
   "平和自摸：底 20 + 自摸 0（平和型不加自摸符）")
eq(calc_fu(RUNS4, 19, WAIT_RYANMEN, False, True, True, NORTH, NORTH), 30,
   "平和荣和：底 20 + 門前清栄和 10")
eq(calc_fu(RUNS4, NORTH, WAIT_SHANPON, True, True, False, NORTH, NORTH), 30,
   "20 符（非平和）抬到 30 符")
eq(calc_fu([("tri", 0, False, False), ("tri", 1, False, False),
            ("run", 3, False, False), ("run", 6, False, False)],
           19, WAIT_RYANMEN, False, False, False, NORTH, NORTH), 40,
   "刻子符：幺九暗刻 8 + 中張暗刻 4 = 32 -> 40（若都按 4 算则 28 -> 30）")
eq(calc_fu([("tri", 0, False, True), ("run", 3, False, False),
            ("run", 6, False, False), ("run", 9, False, False)],
           19, WAIT_RYANMEN, False, False, False, NORTH, NORTH), 60,
   "槓子符：幺九暗槓 32 + 底 20 = 52 -> 60")
eq(calc_fu([("tri", 0, True, False), ("run", 3, False, False),
            ("run", 6, False, False), ("run", 9, False, False)],
           19, WAIT_RYANMEN, False, False, False, NORTH, NORTH), 30,
   "幺九明刻 4 符：20+4 = 24 -> 30")
eq(calc_fu(RUNS4, EAST, WAIT_RYANMEN, True, True, False, EAST, EAST), 30,
   "連風雀头按 2+2 = 4 符：26 -> 30（按 2 符时 24 -> 30；样本无法判别，保留 +4 口径）")

# ------------------------------------------------------------------ 3
print("=== 3. 点数计算 ===")
eq(ceil100(1000), 1000, "ceil100 已是 100 的倍数")
eq(ceil100(940), 1000, "ceil100 往上取整")
eq([base_points(h, 30) for h in (1, 2, 3, 4)], [240, 480, 960, 1920], "1~4 番基本点（30 符）")
eq([base_points(h, 30) for h in (5, 6, 7, 8, 11, 13)],
   [2000, 3000, 3000, 4000, 6000, 8000], "5 番以上跳档（満貫/跳満/倍満/三倍満/役満）")
eq(base_points(6, 40), 3000, "6 番 40 符 = 跳満（符不计入）")
eq(ceil100(base_points(4, 30) * 4), 7700, "4 番 30 符 子家荣和 = 7700（天凤无切り上げ満貫，牌谱实测）")
eq(ceil100(base_points(4, 40) * 4), 8000, "4 番 40 符 子家荣和 = 8000")
eq(ceil100(base_points(3, 70) * 6), 12000, "3 番 70 符 亲家荣和 = 12000")

r = payment_of(2000, False, False)
eq((r["self"], r["payments"]), (8000, {"loser": -8000}), "子家荣和満貫：+8000 / 放铳者 -8000")
r = payment_of(2000, True, False)
eq((r["self"], r["payments"]), (12000, {"loser": -12000}), "亲家荣和満貫：+12000 / -12000")
r = payment_of(2000, False, True)
eq((r["self"], r["payments"]), (8000, {"dealer": -4000, "children": [-2000, -2000]}),
   "子家自摸満貫：亲家 4000 / 子家 2000（共 8000）")
r = payment_of(2000, True, True)
eq((r["self"], r["payments"]), (12000, {"dealer": -4000, "children": [-4000, -4000]}),
   "亲家自摸満貫：三家各 4000（共 12000）")
r = payment_of(240, False, False, honba=1)
eq((r["self"], r["payments"]["loser"]), (1300, -1300),
   "子家 1 番 30 符 + 1 本场荣和 = 1300（牌谱实测：ダブロン先和者）")
r = payment_of(2000, False, True, honba=2)
eq(r["self"], 8600, "子家自摸満貫 + 2 本场（每家 +200）")
r = payment_of(2000, False, False, honba=2)
eq(r["self"], 8600, "子家荣和満貫 + 2 本场（放铳者 +600）")
r = payment_of(2000, False, True, kyotaku=2)
eq(r["self"], 10000, "子家自摸満貫 + 2 供托（+2000）")

r = {"gain": 8000, "payments": {"loser": -8000}, "oya": False}
eq(seat_deltas(r, 0, 4, loser=2), [8000, 0, -8000, 0], "荣和配分：失点记在放铳者座位")
r2 = {"gain": 8000, "payments": payment_of(2000, False, True)["payments"], "oya": False}
eq(seat_deltas(r2, 1, 4, oya_seat=2), [-2000, 8000, -4000, -2000],
   "子家自摸配分：亲家 -4000 / 其余子家 -2000")
eq(sum(seat_deltas(r2, 1, 4, oya_seat=2)), 0, "配分总和为 0（子家自摸）")
r3 = {"gain": 12000, "payments": payment_of(2000, True, True)["payments"], "oya": True}
eq(seat_deltas(r3, 2, 4, oya_seat=2), [-4000, -4000, 12000, -4000], "亲家自摸配分：三家各 -4000")
eq(sum(seat_deltas(r3, 2, 4, oya_seat=2)), 0, "配分总和为 0（亲家自摸）")

R = score(KOKU, win_tile=T(CHUN)[0], tsumo=False, seat_wind=EAST, round_wind=SOUTH)
eq((R["yakuman"], R["base"], R["gain"]), (2, 16000, 64000),
   "国士無双十三面 = 双倍役満（子家荣和 64000）")
R = score(KOKU, win_tile=T(CHUN)[0], tsumo=True, oya=True, seat_wind=EAST, round_wind=SOUTH)
eq((R["yakuman"], R["gain"]), (2, 96000), "国士無双十三面 亲家自摸 = 32000 all（96000）")
R = score(KOKU1, win_tile=T(CHUN)[0], tsumo=False, seat_wind=EAST, round_wind=SOUTH)
eq(([y[0] for y in R["yaku"]], R["yakuman"], R["gain"]), ([47], 1, 32000),
   "国士無双 = 役満（子家荣和 32000）")
R = score(PIN, win_tile=T(11)[0], tsumo=True, oya=True, seat_wind=EAST, round_wind=SOUTH,
          ctx={"tenhou": True})
eq(([y[0] for y in R["yaku"]], R["yakuman"], R["gain"]), ([37], 1, 48000),
   "天和 = 役満（亲家自摸 16000 all）")
R = score(PIN, win_tile=T(11)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH,
          ctx={"chiihou": True})
eq(([y[0] for y in R["yaku"]], R["yakuman"], R["gain"]), ([38], 1, 32000),
   "地和 = 役満（子家自摸 8000/16000，共 32000）")
R = score(PIN, win_tile=T(11)[0], tsumo=False, seat_wind=EAST, round_wind=SOUTH,
          ctx={"renhou": True})
eq(([y[0] for y in R["yaku"]], R["yakuman"], R["gain"]), ([36], 1, 32000),
   "人和 = 役満（子家荣和 32000）")

NOYAKU = T(0, 1, 2, 3, 4, 5, 15, 16, 17, 19, 19, 21, 23)
fails(lambda: score(NOYAKU, win_tile=T(22)[0], tsumo=False, seat_wind=EAST, round_wind=SOUTH),
      "无役荣和（默听、无立直、嵌張 5s）-> ValueError")
eq(len(score(NOYAKU, win_tile=T(22)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH)["yaku"]), 1,
   "同一手自摸时有役（門前清自摸和）")

# ------------------------------------------------------------------ 4
print("=== 4. 宝牌 / 赤宝牌 / 里宝牌 / 牌张上限 ===")
eq(dora_count([T(0)[0]], [T(1)[0]]), 1, "指示牌 1m -> 2m 是宝牌")
eq(dora_count([T(8)[0]], [T(0)[0]]), 1, "指示牌 9m -> 1m（数牌回卷）")
eq(dora_count([T(NORTH)[0]], [T(EAST)[0]]), 1, "指示牌 北 -> 東（风牌回卷）")
eq(dora_count([T(CHUN)[0]], [T(HAKU)[0]]), 1, "指示牌 中 -> 白（三元回卷）")
eq(dora_count(T(0, 0), T(1, 1, 1)), 6,
   "宝牌按指示牌逐张累加（两张 1m 指示牌 × 三张 2m = 6 张宝牌）")
eq(is_red(16), True, "赤宝牌 5m（id 16）")
eq(is_red(52), True, "赤宝牌 5p（id 52）")
eq(is_red(88), True, "赤宝牌 5s（id 88）")
eq(is_red(19), False, "普通 5m（id 19）不是赤宝牌")
eq(is_red(124), False, "白（id 124）不是赤宝牌（第 15 轮修正：字牌没有赤宝牌）")

R = score(PIN, win_tile=T(11)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH,
          ctx={"dora": [T(4)[0]]})
eq((52 in [y[0] for y in R["yaku"]], 54 in [y[0] for y in R["yaku"]], R["han"]), (True, False, 3),
   "宝牌 1（6m，指示牌 5m）计入、无赤宝牌：平和+自摸+ドラ = 3 番")
RED = T(0, 1, 2, 4, 5, 6, 6, 7, 8, 12, 13, 19, 19)
eq(kind_of(RED[3]), 4, "构造手牌里第 4 张是 5m")
RED[3] = 16
eq(is_red(RED[3]), True, "把该张改成赤宝牌 id 16")
R = score(RED, win_tile=T(11)[0], tsumo=True, seat_wind=EAST, round_wind=SOUTH, riichi=1,
          ctx={"ura": []})
eq((54 in [y[0] for y in R["yaku"]], 1 in [y[0] for y in R["yaku"]], R["han"]), (True, True, 4),
   "赤宝牌 1 + 立直：平和 1 + 立直 1 + 門前清自摸和 1 + 赤宝牌 1 = 4 番")
eq(53 in [y[0] for y in R["yaku"]], False, "里宝牌指示牌为空时不产生 53 条目")
# ------------------------------------------------------------------ 5
print("=== 5. 全量校验：data 下（含 data/paipu/ 子目录）+ data_extra 的全部牌谱 ===")
FILES = sorted(glob.glob(os.path.join(ROOT, "data", "**", "*.xml"), recursive=True)
               + glob.glob(os.path.join(ROOT, "data_extra", "*.xml")))
eq(len(FILES), 71, "牌谱总数（71 个：data 下 + 可选 data_extra）")

FLAGS = (2, 3, 4, 5, 6)          # 一発 / 槍槓 / 嶺上開花 / 海底摸月 / 河底撈魚：作为场况输入
FLAG_NAME = {2: "ippatsu", 3: "chankan", 4: "rinshan", 5: "haitei", 6: "houtei"}
CNT = collections.Counter()
BAD_ = {}


def bump(key, msg):
    c = BAD_.setdefault(key, [0, ""])
    c[0] += 1
    if c[0] == 1:
        c[1] = msg


def kind_tile(k, used):
    """找一个手里没用过的 kind k 的牌 id（用于合成「和了张」）。"""
    for i in range(4):
        t = 4 * k + i
        if t not in used:
            return t
    return None


for fn in FILES:
    game = mjlog.game_from_file(fn)
    for ri, rnd in enumerate(game["rounds"]):
        st = replay.initial_state(game, ri)
        evs = rnd["events"]
        n_agari = 0
        for ei, ev in enumerate(evs):
            if ev["type"] == "reach" and ev.get("step") == 1:
                # 立直宣言时必定听牌：14-3n 张里去掉任意一张后，存在某张和了张能成立
                p = ev["player"]
                pl = st["players"][p]
                seen = set()
                ok = False
                for t in pl["hand"]:
                    k = kind_of(t)
                    if k in seen:
                        continue
                    seen.add(k)
                    h13 = list(pl["hand"])
                    h13.remove(t)
                    used = set(h13)
                    for m in pl["melds"]:
                        used.update(m.get("tiles") or ())
                    for w in range(34):
                        if len([1 for x in used if kind_of(x) == w]) >= 4:
                            continue
                        try:
                            if shapes_of(h13, pl["melds"], kind_tile(w, used)):
                                ok = True
                                break
                        except ValueError as exc:
                            CNT["tenpai_err"] += 1
                            bump("tenpai", "%s 局%d: %s" % (os.path.basename(fn), ri, exc))
                            ok = True
                            break
                    if ok:
                        break
                CNT["riichi"] += 1
                if not ok:
                    CNT["tenpai_bad"] += 1
                    bump("tenpai", "%s 局%d who=%d 立直未听牌" % (os.path.basename(fn), ri, p))
            if ev["type"] != "agari":
                replay.apply_event(st, ev)
                continue
            w, fw = ev["winner"], ev["fromWho"]
            tsumo = (w == fw)
            pl = st["players"][w]
            if tsumo:
                win = (st["drawn"] or {}).get("tile")
                hand = list(pl["hand"])
                if win is not None and win in hand:
                    hand.remove(win)
            else:
                win = st["players"][fw]["river"][-1]["tile"]
                hand = list(pl["hand"])
            yids = [y for y, h in ev["yaku"]]
            ctx = {"dora": list(st["dora"]), "ura": list(ev["ura"]) if pl["riichi"] else ()}
            for fid in FLAGS:
                if fid in yids:
                    ctx[FLAG_NAME[fid]] = True
            riichi = 2 if (pl["riichi"] and pl["river"] and pl["river"][0].get("riichi")
                           and not any(e.get("type") == "call" for e in evs[:ei])) \
                else (1 if pl["riichi"] else 0)
            honba = st["honba"] if n_agari == 0 else 0       # ダブロン：本场/供托只归先和者
            kyotaku = st["kyotaku"] if n_agari == 0 else 0
            n_agari += 1
            tag = "%s 局%d who=%d" % (os.path.basename(fn), ri, w)
            try:
                res = score(hand, pl["melds"], win, tsumo=tsumo, oya=(w == st["oya"]),
                            honba=honba, kyotaku=kyotaku,
                            seat_wind=27 + (w - st["oya"]) % 4,
                            round_wind=27 + (st["round"] // 4) % 4,
                            riichi=riichi, ctx=ctx)
            except Exception as exc:                          # noqa: BLE001
                CNT["score_err"] += 1
                bump("score_err", "%s: %r" % (tag, exc))
                replay.apply_event(st, ev)
                continue
            CNT["agari"] += 1
            try:
                hits = check_all(hand, pl["melds"], win, tsumo=tsumo, riichi=riichi,
                                 seat_wind=27 + (w - st["oya"]) % 4,
                                 round_wind=27 + (st["round"] // 4) % 4)
                if not any(h[0] == res["shape"] for h in hits):
                    CNT["disc_bad"] += 1
                    bump("disc", "%s shape=%s hits=%s" % (tag, res["shape"], hits))
            except ValueError as exc:
                CNT["disc_bad"] += 1
                bump("disc", "%s: %s" % (tag, exc))
            if res["fu"] != ev["ten"][0]:
                CNT["fu_bad"] += 1
                bump("fu", "%s 我=%d 谱=%d 待ち=%s" % (tag, res["fu"], ev["ten"][0], res["wait"]))
            mine = dict((i, h) for i, h, _n in res["yaku"] if i not in FLAGS)
            theirs = dict((y, h) for y, h in ev["yaku"] if y not in FLAGS and h > 0)
            if mine != theirs:
                CNT["yaku_bad"] += 1
                bump("yaku", "%s 我=%s 谱=%s" % (tag, sorted(mine.items()),
                                                 sorted(theirs.items())))
            if res["han"] != sum(h for _y, h in ev["yaku"]):
                CNT["han_bad"] += 1
                bump("han", "%s 我=%d 谱=%d" % (tag, res["han"], sum(h for _y, h in ev["yaku"])))
            if res["gain"] != ev["gain"][w]:
                CNT["gain_bad"] += 1
                bump("gain", "%s 我=%d 谱=%d（%d 番 %d 符）"
                     % (tag, res["gain"], ev["gain"][w], res["han"], res["fu"]))
            _tot = max(c["total"] for c in res["cands"])
            _want = res["base"] if res["yakuman"] else res["base"] * 4
            if _tot != _want:
                CNT["max_bad"] += 1
                bump("max", "%s 选中 base=%d，候选最大 %d" % (tag, res["base"], _tot))
            if len(res["cands"]) > 1:
                CNT["multi"] += 1
            deltas = seat_deltas(res, w, oya_seat=st["oya"], loser=None if tsumo else fw)
            if deltas != list(ev["gain"]):
                CNT["deltas_bad"] += 1
                bump("deltas", "%s 我=%s 谱=%s" % (tag, deltas, list(ev["gain"])))
            if list(st["dora"]) != list(ev["dora"]):
                CNT["dora_bad"] += 1
                bump("dora", "%s state=%s agari=%s"
                     % (tag, [mjlog.tile_name(t) for t in st["dora"]],
                        [mjlog.tile_name(t) for t in ev["dora"]]))
            replay.apply_event(st, ev)

eq(CNT["agari"], 640, "和牌事件数")
eq(CNT["riichi"], 545, "立直宣言数")
eq(CNT["score_err"], 0, "score 异常数（首例：%s）"
   % (BAD_.get("score_err", [0, "-"])[1] or "-"))
eq(CNT["disc_bad"], 0, "判别器与 score 牌型不一致数")
eq(CNT["tenpai_bad"] + CNT["tenpai_err"], 0, "立直必定听牌违例数")
for _key, _label in (("fu", "符"), ("yaku", "役"), ("han", "番"), ("gain", "得点"),
                     ("deltas", "4 家配分"), ("dora", "宝牌指示牌")):
    _c = BAD_.get(_key, [0, ""])
    check(_c[0] == 0, "%s 逐例一致（%d 处不符%s）"
          % (_label, _c[0], "，首例 " + _c[1] if _c[0] else ""))

# ------------------------------------------------------------------ 6
print("=== 6. \u6700\u5927\u539f\u5219\uff1a\u591a\u4e2a\u62c6\u89e3\u90fd\u80fd\u548c\u724c\u65f6\u53d6\u6253\u70b9\u6700\u5927\u8005 ===")


def check_max(r, label):
    """\u65ad\u8a00 score() \u9009\u4e2d\u7684\u5019\u9009\u662f\u5168\u90e8\u5019\u9009\u4e2d\u6253\u70b9\u6700\u5927\u8005\uff08\u6700\u5927\u539f\u5219\uff09\u3002"""
    tot = max(c["total"] for c in r["cands"])
    want = r["base"] if r["yakuman"] else r["base"] * 4
    check(tot == want, "%s\uff1abase=%d \u5373\u5168\u90e8\u5019\u9009\u7684\u6700\u5927\u503c\uff08\u5019\u9009 %d \u4e2a\uff09"
          % (label, want, len(r["cands"])))
    return len(r["cands"])


# 6.1 \u5168\u91cf 640 \u4f8b\uff08\u7b2c 5 \u8282\u7d2f\u79ef\u7684\u7edf\u8ba1\uff09
eq(CNT["max_bad"], 0, "\u9009\u4e2d\u8005 = \u5019\u9009\u4e2d\u6253\u70b9\u6700\u5927\u8005\uff08\u8fdd\u4f8b %d \u5904%s\uff09"
   % (CNT["max_bad"], "\uff0c\u9996\u4f8b " + BAD_["max"][1] if CNT["max_bad"] else ""))
check(CNT["multi"] > 0, "\u5b58\u5728\u591a\u89e3\u5019\u9009\u7684\u548c\u724c\uff08%d \u4f8b / \u5171 %d \u4f8b\uff09"
      % (CNT["multi"], CNT["agari"]))

# 6.2 \u9023\u98a8\u96c0\u982d 4 \u7b26\uff08\u81ea\u98ce +2\u3001\u5834\u98ce +2\uff1b\u7528\u6237 m01068 \u786e\u8ba4\uff09
_KAN = [("tri", 2, True, False), ("tri", 3, False, False)]   # \u4e2d\u5f35\u660e\u523b 2 \u7b26\u3001\u4e2d\u5f35\u6697\u523b 4 \u7b26
eq(calc_fu(_KAN, SOUTH, "\u4e21\u9762", True, False, False, SOUTH, SOUTH), 40,
   "\u9023\u98a8\u96c0\u982d\uff1a20+2(\u81ea\u6478)+2(\u660e\u523b)+4(\u6697\u523b)+2(\u81ea\u98a8)+2(\u5834\u98a8) = 32\u219240")
eq(calc_fu(_KAN, SOUTH, "\u4e21\u9762", True, False, False, SOUTH, EAST), 30,
   "\u975e\u9023\u98a8\uff08\u5834\u98a8\u6771\uff09\uff1a20+2+2+4+2 = 30\u219230\uff08\u5dee\u984d = \u9023\u98a8\u591a\u51fa\u7684 2 \u7b26\uff09")

# 6.3 \u7528\u6237 m01068 \u7684 6 \u4e2a\u4f8b\u5b50\uff08\u6771\u5834\u30fb\u5357\u5bb6\u30fb\u5b50\u5bb6\u30fb0 \u672c\u5834\u30fb0 \u4f9b\u6258\u30fb\u5b9d\u724c\u6307\u793a\u724c 1z\uff09
#     \u300c\u5b50,\u4eb2\u300d= \u5b50\u5bb6\u4ed8\u70b9 / \u4eb2\u5bb6\u4ed8\u70b9\uff1b\u672c\u5f15\u64ce riichi=1 \u7acb\u76f4\u3001riichi=2 \u4e21\u7acb\u76f4\uff08\u4e0d\u53e0 (1,1)\uff09
U6 = dict(oya=False, seat_wind=SOUTH, round_wind=EAST, honba=0, kyotaku=0,
          ctx={"dora": [T(27)[0]]})

r1 = score(T(0, 0, 1, 2, 4, 5, 6, 10, 11, 12, 21, 22, 23), win_tile=T(0)[0],
           tsumo=True, riichi=1, **U6)
eq((r1["han"], r1["fu"]), (3, 20), "\u4f8b 1\uff1a\u7acb\u76f4+\u5e73\u548c+\u9580\u524d\u6e05\u81ea\u6478\u548c = 3 \u756a 20 \u7b26")
eq(check_max(r1, "例 1"), 2, "例 1：两种读法（11m 雀头 + 23m 両面 = 平和 20 符，打点最高；単騎 1m 只有 2 番 30 符）")
eq((r1["payments"]["children"][0], r1["payments"]["dealer"]), (-700, -1300),
   "\u4f8b 1\uff1a\u5b50\u5bb6 700 / \u4eb2\u5bb6 1300\uff08\u4e0e\u7528\u6237 m01068 \u4f8b 1 \u4e00\u81f4\uff09")

r2 = score(T(0, 0, 1, 2, 4, 5, 6, 10, 11, 12, 33, 33, 33), win_tile=T(0)[0],
           tsumo=True, riichi=1, **U6)
eq((r2["han"], r2["fu"]), (3, 40), "例 2：立直+役牌中+自模 = 3 番 40 符（两种读法：① 両面 20+8+2 = 30 符；② 単騎 20+8+2(単騎)+2(自模) = 32→40 符，最大原则取 ②，与用户 m01164 一致）")
eq((r2["payments"]["children"][0], r2["payments"]["dealer"]), (-1300, -2600),
   "例 2：1300,2600（用户 m01164 的期望值；旧实现因 placement 有效性剪枝只给 1000,2000）")
check_max(r2, "\u4f8b 2")

r3 = score(T(0, 0, 1, 1, 2, 2, 4, 4, 5, 6, 6, 10, 10), win_tile=T(5, 5)[1],
           tsumo=False, riichi=0, **U6)
eq(r3["shape"], MENTSU, "\u4f8b 3\uff1a\u9762\u5b50\u624b > \u4e03\u5bfe\u5b50\uff08\u6700\u5927\u539f\u5219\uff09")
eq((r3["han"], r3["fu"]), (3, 40), "\u4f8b 3\uff1a\u4e8c\u76c3\u53e3\uff08\u5929\u51e4 3 \u756a\uff09+ \u9580\u524d\u6e05\u6804\u548c/\u5d4c\u5f35 = 40 \u7b26")
eq(r3["gain"], 5200, "\u4f8b 3\uff1a5200\uff08\u7528\u6237 m01068 \u5199 2600 = \u4e8c\u76c3\u53e3\u6309 2 \u756a\uff09")
eq(check_max(r3, "\u4f8b 3"), 3, "\u4f8b 3\uff1a\u5019\u9009 3 \u4e2a\uff08\u4e03\u5bfe\u5b50 2 \u756a 25 \u7b26 base 400 < 1280\uff09")

r4 = score(T(1, 1, 1, 2, 2, 2, 3, 3, 9, 10, 11, 26, 26), win_tile=T(3, 3, 3)[2],
           tsumo=True, riichi=0, **U6)
eq((r4["han"], r4["fu"]), (3, 40), "\u4f8b 4\uff1a\u4e09\u6697\u523b+\u81ea\u6478 = 3 \u756a\uff0820+2 \u81ea\u6478+3\u00d74 \u6697\u523b = 34\u219240 \u7b26\uff09")
eq((r4["payments"]["children"][0], r4["payments"]["dealer"]), (-1300, -2600),
   "\u4f8b 4\uff1a\u672c\u5f15\u64ce 1300,2600\uff08\u7528\u6237\u5199 1000,2000 = 30 \u7b26\uff09")
eq(check_max(r4, "\u4f8b 4"), 4, "\u4f8b 4\uff1a\u5019\u9009 4 \u4e2a\uff08\u4e21\u9762+\u4e00\u76c3\u53e3 2 \u756a 20 \u7b26 base 480 \u4e0d\u662f\u6700\u5927\uff09")

r5 = score(T(0, 0, 0, 1, 1, 1, 2, 2, 9, 10, 11, 26, 26), win_tile=T(2, 2, 2)[2],
           tsumo=True, riichi=0, **U6)
eq((r5["han"], r5["fu"]), (5, 30), "\u4f8b 5\uff1a\u4e00\u76c3\u53e3+\u7d14\u5168\u5e2f\u5e7a\u4e5d(3)+\u81ea\u6478 = 5 \u756a 30 \u7b26\uff08\u6e80\u8cab\uff09")
eq(r5["gain"], 8000, "\u4f8b 5\uff1a\u672c\u5f15\u64ce 2000,4000\uff085 \u756a\u6e80\u8cab 8000 > \u4e09\u6697\u523b 3 \u756a 40 \u7b26 5120\uff09")
eq(check_max(r5, "\u4f8b 5"), 4, "\u4f8b 5\uff1a\u5019\u9009 4 \u4e2a\uff08\u53cc\u78b0\u4e09\u6697\u523b 2 \u756a 40 \u7b26 base 1280 \u4e0d\u662f\u6700\u5927\uff09")

r6 = score(T(0, 0, 0, 1, 1, 1, 2, 2, 9, 10, 11, 30, 30), win_tile=T(2, 2, 2)[2],
           tsumo=True, riichi=0, **U6)
eq((r6["han"], r6["fu"]), (4, 30), "\u4f8b 6\uff1a\u4e00\u76c3\u53e3+\u6df7\u5168\u5e2f\u5e7a\u4e5d(2)+\u81ea\u6478 = 4 \u756a 30 \u7b26")
eq((r6["payments"]["children"][0], r6["payments"]["dealer"]), (-2000, -3900),
   "\u4f8b 6\uff1a\u672c\u5f15\u64ce 2000,3900\uff08\u7528\u6237\u5199 1300,2600 = \u4e09\u6697\u523b 3 \u756a 40 \u7b26\uff09")
eq(check_max(r6, "\u4f8b 6"), 4, "\u4f8b 6\uff1a\u5019\u9009 4 \u4e2a")

# 6.4 同种 3 张时単騎读法存在，但平和（両面）读法打点更高 ⇒ 仍取 30 符
#     （对应实测牌谱 data\2026090320gm-00a9-0000-ed855534.xml 局 1 who=2：立直+平和 30 符）
r7 = score(T(18, 18, 19, 20, 21, 22, 23, 15, 16, 17, 1, 2, 3), win_tile=T(18)[0],
           tsumo=False, riichi=1, **U6)
eq((r7["han"], r7["fu"]), (2, 30), "同种 3 张：平和両面 2 番 30 符 胜过硬读単騎的 1 番 40 符")
eq(r7["wait"], "両面", "同种 3 张：选中的读法是両面（単騎读法也在 cands 里）")
eq(check_max(r7, "同种 3 张"), 2, "同种 3 张：単騎与両面两种读法各 1 个候选")

# ------------------------------------------------------------------ 汇总
print("")
print("===== 结果 =====")
print("通过 %d 项，失败 %d 项" % (OK[0], BAD[0]))
if BAD[0]:
    print("测试失败")
    sys.exit(1)
print("全部通过")