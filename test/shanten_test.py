# -*- coding: utf-8 -*-
r"""shanten 正式测试（第 17 轮：三种向听数 = 国士無双 / 七対子 / 面子手）。

覆盖：
  1. 三种牌型的 -1 / 0 / 1 / 2 / >=3 手算用例（含副露手牌张数 14-3n、13-3n）
  2. 场上可见牌约束（avail）：进张必须「看得到」，同种牌看到几张就只能摸几张
  3. 独立参考实现对拍：枚举 d=0..3 张摸牌 multiset（D[k] <= avail[k]），
     用不带剪枝的朴素拆分判断能否凑出和牌型，逐例对比三种向听数
  4. 全量语料：data\ 5 + data_extra\ 66 = 71 个牌谱，逐帧（摸牌帧 / 吃碰帧）
     计算该家三种向听数，统计帧数与总耗时（供用户判断是否需要换算法）
  5. 起和役（m01436）：有非暗杠副露的手必须真能构成役才算和牌 —— 「假和牌」
     （block 拆分成立但没有任何役）不能记 -1，到它的距离也不能算进向听数；
     副露用例另用 mjscore.agari 的 score() 当独立裁判（门清手不判役）。
     全量语料里再双向核对：形和但无役的副露帧不得记 -1；记成 -1 的副露帧
     必须经 agari 复核「形和 + 真有役」。

运行：
  & 'D:\coding\anaconda3\envs\py314_null\python.exe' test\shanten_test.py
"""
import glob
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import agari, mjlog, replay, shanten  # noqa: E402
from mjscore.agari import counts_of  # noqa: E402

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


def cnt(kinds):
    """kind 列表 -> 34 项计数（同一 kind 最多 4 张，调用方自查）。"""
    c = [0] * 34
    for k in kinds:
        c[k] += 1
    assert max(c) <= 4, c
    return c


def hand_ids(counts):
    """34 项计数 -> 牌 id 列表（每个 kind 取该 kind 的第 0..n 号 id）。

    5 的 id 从该 kind 的第 1 号开始数（16 / 52 / 88 是赤 5）：赤宝牌会被
    agari.score 当成 1 番算进去，掩盖「只有宝牌、没有役 → 不能和」的判定。
    """
    out = []
    for k in range(34):
        base = k * 4 + (1 if k in (4, 13, 22) else 0)
        for j in range(counts[k]):
            out.append(base + j)
    return out


SW, RW = 28, 27                     # 起和役用例的自风（南）/ 场风（东）


def mchi(start):
    """吃：起点 kind 为 start 的顺子（m 0-6 / p 9-15 / s 18-24），取自下家。"""
    return {"callType": "chi", "tiles": [start * 4, (start + 1) * 4, (start + 2) * 4],
            "calledId": start * 4, "from": 1, "open": True}


def mpon(k):
    """碰。"""
    return {"callType": "pon", "tiles": [k * 4, k * 4 + 1, k * 4 + 2],
            "calledId": k * 4, "from": 1, "open": True}


def mankan(k):
    """暗杠（不算副露、不影响门清，也不吃起和役约束）。"""
    return {"callType": "ankan", "tiles": [k * 4, k * 4 + 1, k * 4 + 2, k * 4 + 3],
            "calledId": k * 4, "from": 0, "open": False}


def _less(counts, kind):
    """从计数里减去一张牌（用来把和牌形拆成「不含和了张的 13-3n 张」）。"""
    c = list(counts)
    c[kind] -= 1
    return c


def _score_ok(c13, melds, win_kind, sw=SW, rw=RW):
    """用 mjscore.agari.score() 当独立裁判：这个和牌形真有役、真能成立吗。

    ``c13`` = 不含和了张的门清手牌（13-3n 张）。只对副露手有意义：门清手
    agari 会给「門前清自摸和」，这也正是门清总有起和役的原因。
    """
    try:
        agari.score(hand_ids(c13), melds, win_tile=win_kind * 4, tsumo=True,
                    seat_wind=sw, round_wind=rw)
        return True
    except ValueError as e:
        if "役なし" in str(e):
            return False
        raise


def fmt(r):
    return "国士 %d / 七対 %d / 面子 %d" % (r["kokushi"], r["chiitoi"], r["mentsu"])

def section1():
    print("=== 1. 三种牌型的手算用例 ===")
    # 和牌（面子手）：123m456m789m123p55s
    r = shanten.shanten_of(cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 22, 22]))
    eq(r["mentsu"], -1, "和牌 123m456m789m123p55s：面子手 -1")
    eq(r["kokushi"], 3, "同上：国士無双 >=3")
    eq(r["chiitoi"], 3, "同上：七対子 >=3")

    # 听牌（単騎 5s）：123m456m789m123p5s（13 张）
    r = shanten.shanten_of(cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 22]))
    eq(r["mentsu"], 0, "听牌 123m456m789m123p5s：面子手 0（単騎听）")

    # 听牌（両面 3s/6s）：123m456m789m123p 4s5s
    r = shanten.shanten_of(cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 21, 22]))
    eq(r["mentsu"], 0, "听牌 123m456m789m123p45s：面子手 0（両面听）")

    # 1 向听：123m456m789m123p 4s 7z（四组面子 + 两张无关单张）
    r = shanten.shanten_of(cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 21, 33]))
    eq(r["mentsu"], 0, "123m456m789m123p4s7z：面子手 0（四面子 + 两张单张 = 听牌，等其中一张成对）")

    # >=3：完全散手
    r = shanten.shanten_of(cnt([0, 2, 4, 6, 9, 11, 13, 15, 18, 20, 22, 24, 27, 29]))
    eq(r["mentsu"], 3, "散手 1m3m5m7m2p4p6p8p1s3s5s7s西發：面子手 >=3")
    eq(r["kokushi"], 3, "同上：国士無双 >=3")
    eq(r["chiitoi"], 3, "同上：七対子 >=3")

    # 副露：3 组副露（碰白 + 碰發 + 吃123s，役牌在手）+ 123m + 55s（手牌 5 张 = 14-9）
    r = shanten.shanten_of(cnt([0, 1, 2, 22, 22]), melds=[mpon(33), mpon(32), mchi(18)])
    eq(r["mentsu"], -1, "3 副露（碰白碰發吃123s）+ 123m55s：面子手 -1")
    # 副露：2 组副露（碰白 + 吃456p）+ 123m22s77z（手牌 7 张 = 13-6）：双碰听
    r = shanten.shanten_of(cnt([0, 1, 2, 19, 19, 27, 27]), melds=[mpon(33), mchi(12)])
    eq(r["mentsu"], 0, "2 副露 + 123m22s77z（手牌 7 张 = 13-6）：面子手 0（双碰听）")
    eq(r["kokushi"], 3, "有副露时国士無双 = >=3")
    eq(r["chiitoi"], 3, "有副露时七対子 = >=3")

    # 国士無双：13 种幺九牌各 1 张 + 1m 成对
    yao13 = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    r = shanten.shanten_of(cnt(yao13 + [0]))
    eq(r["kokushi"], -1, "国士無双 13 面听：-1")
    # 差 2 种、无对：13 张里 12 种幺九 + 一张多的 9m
    r = shanten.shanten_of(cnt([0, 8, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 33]))
    eq(r["kokushi"], 0, "国士無双 差 2 种且无对：0")

    # 七対子：6 对 + 2 单张
    r = shanten.shanten_of(cnt([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 20, 33]))
    eq(r["chiitoi"], 0, "七対子 6 对 + 2 单：0")
    eq(r["kokushi"], 3, "同上：国士無双 >=3")
    # 七対子：5 对 + 4 单张
    r = shanten.shanten_of(cnt([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 20, 21, 33, 32]))
    eq(r["chiitoi"], 1, "七対子 5 对 + 4 单：1")
    eq(r["mentsu"], 1, "同上：面子手 1（223344m55m + 456s? 这张是 1 向听）")


def section1b():
    print("=== 1b. 起和役：副露手必须有役才算和牌（m01436） ===")
    # 共用形：123m456m234p99m + 一组副露（3 组暗面子 + 雀头 = 面子手）
    A = [0, 1, 2, 3, 4, 5, 10, 11, 12, 8, 8]
    PAIR = 8                        # 9m 雀头

    # ① 无役：吃 123s 时 123m + 123s 还差 123p，没有任何役 ⇒ 形和也不能记 -1
    melds = [mchi(18)]
    r = shanten.shanten_of(cnt(A), melds=melds)
    eq(r["mentsu"], 0, "吃123s + 123m456m234p99m：形和但无役 ⇒ 不记 -1（面子手 0）")
    eq(_score_ok(_less(cnt(A), PAIR), melds, PAIR), False,
       "同上：agari.score 判「役なし」")

    # ② 三色同順：吃 123s + 123m + 123p 就成役
    melds = [mchi(18)]
    B = [0, 1, 2, 3, 4, 5, 9, 10, 11, 8, 8]
    r = shanten.shanten_of(cnt(B), melds=melds)
    eq(r["mentsu"], -1, "吃123s + 123m456m123p99m：三色同順 ⇒ -1")
    eq(_score_ok(_less(cnt(B), PAIR), melds, PAIR), True, "同上：agari.score 认得三色同順")

    # ③ 役牌：碰白就有役
    melds = [mpon(33)]
    r = shanten.shanten_of(cnt(A), melds=melds)
    eq(r["mentsu"], -1, "碰白 + 123m456m234p99m：役牌 白 ⇒ -1")
    eq(_score_ok(_less(cnt(A), PAIR), melds, PAIR), True, "同上：agari.score 认得役牌 白")

    # ④ 暗杠不算副露：只有暗杠 ⇒ 按门清处理，不需要役（门清可以立直）
    melds = [mankan(27)]
    r = shanten.shanten_of(cnt(A), melds=melds)
    eq(r["mentsu"], -1, "暗杠東 + 123m456m234p99m：只有暗杠 ⇒ 门清 -1")
    eq(_score_ok(_less(cnt(A), PAIR), melds, PAIR), True,
       "同上：门清自摸有「門前清自摸和」")

    # ⑤ 三暗刻不是门清役：副露手里照样成立
    C = [1, 1, 1, 10, 10, 10, 20, 20, 20, 0, 0]
    melds = [mchi(25)]              # 吃 789s
    r = shanten.shanten_of(cnt(C), melds=melds)
    eq(r["mentsu"], -1, "吃789s + 222m333p444s11m：三暗刻 ⇒ -1")
    eq(_score_ok(_less(cnt(C), 0), melds, 0), True, "同上：agari.score 认得三暗刻")

    # ⑥ 断幺九
    D = [1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 13]
    melds = [mchi(19)]              # 吃 234s
    r = shanten.shanten_of(cnt(D), melds=melds)
    eq(r["mentsu"], -1, "吃234s + 234m567m234p55p：断幺九 ⇒ -1")
    eq(_score_ok(_less(cnt(D), 13), melds, 13), True, "同上：agari.score 认得断幺九")

    # ⑦ 一盃口是门清役：副露手里不算役，形和也不能记 -1
    E = [0, 1, 2, 0, 1, 2, 12, 13, 14, 17, 17]
    melds = [mchi(25)]              # 吃 789s
    r = shanten.shanten_of(cnt(E), melds=melds)
    eq(r["mentsu"], 2, "吃789s + 123m123m456p88p：只有一盃口（门清役）⇒ 2")
    eq(_score_ok(_less(cnt(E), 17), melds, 17), False, "同上：agari.score 判「役なし」")

    # ⑧ 风牌：场风 / 自风 / 都没役（碰東 + 同一手牌）
    eq(shanten.shanten_of(cnt(A), melds=[mpon(27)], seat_wind=28, round_wind=27)["mentsu"],
       -1, "碰東（东场）：場風 東 ⇒ -1")
    eq(shanten.shanten_of(cnt(A), melds=[mpon(27)], seat_wind=27, round_wind=28)["mentsu"],
       -1, "碰東（南场、自风东）：自風 東 ⇒ -1")
    eq(shanten.shanten_of(cnt(A), melds=[mpon(27)], seat_wind=30, round_wind=29)["mentsu"],
       2, "碰東（西场、自风北）：没有役 ⇒ 2")

    # ⑨ 门清不判役：同一手牌没有副露时与旧行为一致
    eq(shanten.shanten_of(cnt(A))["mentsu"], 2, "同一手牌门清（无副露）：不判役，面子手 2")

    # ⑩ 有副露却不给 melds：必须报错（拿不到副露牌就没法判役）
    try:
        shanten.shanten_of(cnt(A), 1)
        check(False, "有副露但没给 melds：应当报错")
    except ValueError as e:
        check("melds" in str(e), "有副露但没给 melds：ValueError（%s）" % e)


def section2():
    print("=== 2. 场上可见牌约束（avail） ===")
    base = cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 22])
    av = [4] * 34
    eq(shanten.shanten_of(base, 0, av)["mentsu"], 0, "単騎听 5s：avail[5s]=4 -> 0")
    av2 = list(av)
    av2[22] = 0
    eq(shanten.shanten_of(base, 0, av2)["mentsu"], 1, "単騎听 5s：avail[5s]=0（5s 全见）-> 1")
    av3 = list(av)
    av3[22] = 1
    eq(shanten.shanten_of(base, 0, av3)["mentsu"], 0, "単騎听 5s：avail[5s]=1 -> 0")

    # 四组面子 + 两张单张 5s / 7z：雀头必须从这两张里长出来
    c = cnt([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 22, 33])
    eq(shanten.shanten_of(c, 0, [4] * 34)["mentsu"], 0, "四面子 + 5s + 7z：面子手 0")
    av4 = [4] * 34
    av4[22] = 0
    av4[33] = 0
    eq(shanten.shanten_of(c, 0, av4)["mentsu"], 1,
       "四面子 + 5s + 7z，5s/7z 都全见：雀头只能另摸两种 -> 1")

    # 用户 m01278 的例子：手里一张 4m，要摸进两张 4m 才能凑 444m 时，
    # avail[4m] < 2 就不能把它算进进张（4m 全见的张数由 avail 控制）
    c = cnt([0, 1, 2, 3, 12, 13, 14, 15, 16, 17, 22, 22, 24, 24])
    av5 = [4] * 34
    av5[22] = 0
    av5[24] = 0
    ref_a = ref_of(c, 0, av5)["mentsu"]
    got_a = shanten.shanten_of(c, 0, av5)["mentsu"]
    eq(got_a, ref_a, "4m 例子（avail[4m]=4）：模块与参考一致")
    av6 = list(av5)
    av6[3] = 1
    ref_b = ref_of(c, 0, av6)["mentsu"]
    got_b = shanten.shanten_of(c, 0, av6)["mentsu"]
    eq(got_b, ref_b, "4m 例子（avail[4m]=1，不够摸两张 4m）：模块与参考一致")
    check(got_b >= got_a, "4m 例子：avail[4m] 从 4 缩到 1，向听数只可能不变或变大（%d -> %d）" % (got_a, got_b))

# ---------------------------------------------------------------- 参考实现
YAO = shanten.YAO_KINDS


def _d_multisets(avail, d):
    """所有 d 张摸牌的 multiset：每 kind 上限 min(avail[k], d)。"""
    cur = [0] * 34

    def rec(k, left):
        if left == 0:
            yield list(cur)
            return
        if k >= 34:
            return
        m = avail[k] if avail[k] < left else left
        for t in range(m + 1):
            cur[k] = t
            for x in rec(k + 1, left - t):
                yield x
        cur[k] = 0

    for x in rec(0, d):
        yield x


def _sets_ok(c, want):
    """c 里能否取出 want 组完整面子（允许剩下没用的牌，多余的牌可以打掉）。"""
    if want == 0:
        return True
    k = -1
    for i in range(34):
        if c[i]:
            k = i
            break
    if k < 0:
        return False
    n = c[k]
    c[k] = 0
    ok_skip = _sets_ok(c, want)
    c[k] = n
    if ok_skip:
        return True
    if c[k] >= 3:
        c[k] -= 3
        ok = _sets_ok(c, want - 1)
        c[k] += 3
        if ok:
            return True
    if k < 27 and k % 9 <= 6 and c[k + 1] and c[k + 2]:
        c[k] -= 1
        c[k + 1] -= 1
        c[k + 2] -= 1
        ok = _sets_ok(c, want - 1)
        c[k] += 1
        c[k + 1] += 1
        c[k + 2] += 1
        if ok:
            return True
    return False


def _mentsu_win(c, want_sets):
    """c 里能否取出 want_sets 组面子 + 1 组雀头（不要求用完所有牌）。"""
    for p in range(34):
        if c[p] >= 2:
            c[p] -= 2
            ok = _sets_ok(c, want_sets)
            c[p] += 2
            if ok:
                return True
    return False


def _kokushi_win(c):
    return all(c[k] >= 1 for k in YAO) and any(c[k] >= 2 for k in YAO)


def _chiitoi_win(c):
    return sum(1 for k in range(34) if c[k] >= 2) == 7


def _ref_need(win_fn, counts, want_sets=None, avail=None, max_d=3):
    av = [4] * 34 if avail is None else list(avail)
    for d in range(max_d + 1):
        for D in _d_multisets(av, d):
            c = [counts[i] + D[i] for i in range(34)]
            ok = win_fn(c, want_sets) if want_sets is not None else win_fn(c)
            if ok:
                return d
    return None


def _ref_plan(counts, melds=(), avail=None, sw=SW, rw=RW, max_d=3):
    """面子手向听数的参考实现（有副露时用）。

    方向与模块相反：模块从手牌出发「取走」面子，这里直接枚举
    「用哪些面子 + 哪门雀头」的计划，再用 need = 还缺几张 反推摸牌次数；
    avail 限制每种牌还能不能摸到，起和役用 shanten.has_open_yaku 判。
    """
    need_sets = 4 - shanten.n_sets(melds)
    if need_sets < 0:
        return None
    best = [None]
    use = [0] * 34
    chosen = []
    G = shanten.GROUPS

    def feasible(pair):
        """当前 use 计划 + 雀头 pair 还缺几张牌（avail / 4 张上限）都满足时返回 need。"""
        d = 0
        for k in range(34):
            want = use[k] + (2 if k == pair else 0)
            if want > 4:
                return None
            miss = want - counts[k]
            if miss > 0:
                if avail is not None and miss > avail[k]:
                    return None
                d += miss
        return d

    def can_add(ks):
        """把 ks 里的 kind 各 +1 是否还在 4 张上限与 avail 之内（逐张校验）。"""
        tmp = {}
        for k in ks:
            tmp[k] = tmp.get(k, 0) + 1
        for k, inc in tmp.items():
            nu = use[k] + inc
            if nu > 4:
                return False
            miss = nu - counts[k]
            if miss > 0 and avail is not None and miss > avail[k]:
                return False
        return True

    def rec(pos, left):
        if left == 0:
            for p in range(34):
                d = feasible(p)
                if d is None or d > max_d:
                    continue
                if not shanten.has_open_yaku(tuple(chosen), p, melds, sw, rw):
                    continue
                if best[0] is None or d < best[0]:
                    best[0] = d
            return
        for gi in range(pos, len(G)):
            g = G[gi]
            inc = (g[0], g[0], g[0]) if g[0] == g[1] else (g[0], g[0] + 1, g[0] + 2)
            if not can_add(inc):
                continue
            for k in inc:
                use[k] += 1
            chosen.append(g)
            rec(gi, left - 1)
            chosen.pop()
            for k in inc:
                use[k] -= 1

    rec(0, need_sets)
    return best[0]


def meld_counts(melds):
    """副露实际用掉的牌（暗杠 4 张、吃碰 3 张）。"""
    mc = [0] * 34
    for m in melds:
        for t in m["tiles"]:
            mc[t // 4] += 1
    return mc


def rand_melds(rng, n):
    """随机 n 组副露（面子取自 shanten.GROUPS），保证与手牌合计每种 <= 4 张。"""
    used = [0] * 34
    out = []
    tries = 0
    while len(out) < n and tries < 200:
        tries += 1
        g = shanten.GROUPS[rng.randrange(len(shanten.GROUPS))]
        is_kan = False
        if g[0] == g[1]:
            is_kan = rng.random() < 0.2
            ks = (g[0],) * (4 if is_kan else 3)
        else:
            ks = (g[0], g[0] + 1, g[0] + 2)
        if any(used[k] + 1 > 4 for k in ks):
            continue
        for k in ks:
            used[k] += 1
        if is_kan:
            out.append(mankan(g[0]))
        elif g[0] == g[1]:
            out.append(mpon(g[0]))
        else:
            out.append(mchi(g[0]))
    return out


def ref_of(counts, n_melds=0, avail=None, melds=(), sw=SW, rw=RW):
    """独立参考实现：三种向听数，取值 -1/0/1/2/3。

    有副露时：国士 / 七対子 = 3，面子手走 _ref_plan（带起和役约束）。
    """
    out = {}
    if n_melds == 0:
        d = _ref_need(_kokushi_win, counts, avail=avail)
    else:
        d = None
    out["kokushi"] = 3 if d is None else shanten.cap(d)
    if n_melds == 0:
        d = _ref_need(_chiitoi_win, counts, avail=avail)
    else:
        d = None
    out["chiitoi"] = 3 if d is None else shanten.cap(d)
    want = (4 - shanten.n_sets(melds)) if melds else (4 - n_melds)
    if want < 0:
        d = None
    elif melds:
        d = _ref_plan(counts, melds, avail, sw, rw)
    else:
        d = _ref_need(_mentsu_win, counts, want, avail=avail)
    out["mentsu"] = 3 if d is None else shanten.cap(d)
    return out


def section3():
    print("=== 3. 独立参考实现对拍（随机手牌 + 随机副露 + 随机可见牌） ===")
    rng = random.Random(20260901)
    n_case = [0]
    n_far = [0]
    n_open = [0]
    t0 = time.perf_counter()
    for case in range(40):
        n_melds = rng.choice([0, 0, 0, 1, 2, 3])
        melds = rand_melds(rng, n_melds)
        if n_melds and len(melds) != n_melds:
            continue
        mc = meld_counts(melds)
        sw = rng.choice([27, 28, 29, 30])
        rw = rng.choice([27, 28])
        size = rng.choice([14 - 3 * n_melds, 13 - 3 * n_melds])
        pool = []
        for k in range(34):
            pool.extend([k] * (4 - mc[k]))
        rng.shuffle(pool)
        kinds = []
        seen = [0] * 34
        for k in pool:
            if len(kinds) >= size:
                break
            if seen[k] < 4 - mc[k]:
                seen[k] += 1
                kinds.append(k)
        counts = cnt(kinds)
        if rng.random() < 0.25:
            avail = None
        else:
            avail = []
            for k in range(34):
                vis = rng.randint(counts[k] + mc[k], 4)
                avail.append(4 - vis)
        got = shanten.shanten_of(counts, n_melds, avail, melds=melds,
                                 seat_wind=sw, round_wind=rw)
        ref = ref_of(counts, n_melds, avail, melds, sw, rw)
        lab = "case%d（%d 张 / %d 副露 / 自风 %d 场风 %d / %s）" % (
            case, sum(counts), n_melds, sw - 26, rw - 26,
            "不限" if avail is None else "有可见约束")
        n_case[0] += 1
        if n_melds:
            n_open[0] += 1
        if got["mentsu"] == 3:
            n_far[0] += 1
        ok = (got["kokushi"] == ref["kokushi"] and got["chiitoi"] == ref["chiitoi"]
              and got["mentsu"] == ref["mentsu"])
        if not check(ok, "%s：%s == 参考 %s" % (lab, fmt(got), fmt(ref))):
            print("      牌：%s" % ",".join(str(k) for k in sorted(kinds)))
            print("      副露：%s" % ", ".join(m["callType"] + str(m["tiles"][0] // 4)
                                              for m in melds))
            print("      avail：%s" % ("不限" if avail is None else "".join(str(x) for x in avail)))
    print("  （%d 例，其中带副露 %d 例、面子手 >=3 的 %d 例；对拍耗时 %.1f s）"
          % (n_case[0], n_open[0], n_far[0], time.perf_counter() - t0))

def _min(r):
    return min(r["kokushi"], r["chiitoi"], r["mentsu"])


def section4():
    print("=== 4. 全量语料：逐帧三种向听数 + 总耗时 ===")
    files = sorted(glob.glob(os.path.join(ROOT, "data", "**", "*.xml"), recursive=True)
                   + glob.glob(os.path.join(ROOT, "data_extra", "*.xml")))
    eq(len(files), 71, "语料牌谱总数（data 下递归 + 可选 data_extra 共 71 个）")
    n_frame = [0]
    n_calc = [0]
    tsumo_frames = [0]
    tsumo_bad = [0]
    ron_frames = [0]
    ron_bad = [0]
    riichi_frames = [0]
    riichi_bad = [0]
    fake_frames = [0]
    fake_bad = [0]
    open_m1 = [0]
    open_m1_bad = [0]
    dist = {(-1): 0, 0: 0, 1: 0, 2: 0, 3: 0}
    times = []
    t4 = [0.0]
    n4 = [0]
    t0 = time.perf_counter()
    for fn in files:
        game = mjlog.game_from_file(fn)
        for ri in range(len(game["rounds"])):
            evs = game["rounds"][ri]["events"]
            for i, ev, st in replay.iter_events(game, ri):
                kind = None
                seat = -1
                if ev["type"] == "draw":
                    kind, seat = "draw", ev["player"]
                elif ev["type"] == "call" and ev["callType"] in ("chi", "pon"):
                    kind, seat = "call", ev["player"]
                if kind is None:
                    # 荣和：打牌者的下一事件是和了且放铳给别家 -> 别家手牌 + 这张牌能赢
                    if ev["type"] == "discard" and i + 1 < len(evs):
                        nx = evs[i + 1]
                        if (nx["type"] == "agari" and nx["winner"] != nx["fromWho"]
                                and nx["fromWho"] == ev["player"]):
                            w = nx["winner"]
                            pl = st["players"][w]
                            c = counts_of(pl["hand"])
                            c[mjlog.kind_of(ev["tile"])] += 1
                            r = shanten.shanten_of(
                                c, melds=pl["melds"],
                                seat_wind=27 + (w - st["oya"]) % 4,
                                round_wind=27 + st["round"] // 4)
                            ron_frames[0] += 1
                            if _min(r) != -1:
                                ron_bad[0] += 1
                                if ron_bad[0] <= 3:
                                    print("  FAIL 荣和家 %d 张 + 放铳牌仍非和牌：%s（%s 局 %d）"
                                          % (sum(c), fmt(r), os.path.basename(fn), ri))
                    continue
                ta = time.perf_counter()
                r = shanten.shanten_at(st, seat)
                times.append((time.perf_counter() - ta) * 1000)
                n_frame[0] += 1
                n_calc[0] += 3
                dist[r["mentsu"]] += 1
                pl = st["players"][seat]
                # 自摸和了的前一帧：该家一定已经和牌
                if i + 1 < len(evs):
                    nx = evs[i + 1]
                    if (nx["type"] == "agari" and nx["winner"] == seat
                            and nx["fromWho"] == seat):
                        tsumo_frames[0] += 1
                        if _min(r) != -1:
                            tsumo_bad[0] += 1
                            if tsumo_bad[0] <= 3:
                                print("  FAIL 自摸前帧仍非和牌：%s（%s 局 %d）"
                                      % (fmt(r), os.path.basename(fn), ri))
                # 起和役（m01436）：副露手「形是和的、但没有役」= 假和牌。
                # 用 agari 当独立裁判（shapes_of 只看牌型形状、score 判役），
                # 这种帧绝不能被记成 -1（模块的起和役约束应当已经排除了它）。
                if (kind == "draw" and not agari.menzen_of(pl["melds"])
                        and agari.shapes_of(pl["hand"], pl["melds"])):
                    wk = mjlog.kind_of(ev["tile"])
                    sw = 27 + (seat - st["oya"]) % 4
                    rw = 27 + st["round"] // 4
                    if not _score_ok(_less(counts_of(pl["hand"]), wk), pl["melds"], wk, sw, rw):
                        fake_frames[0] += 1
                        if r["mentsu"] == -1:
                            fake_bad[0] += 1
                            if fake_bad[0] <= 3:
                                print("  FAIL 副露手的假和牌被记成 -1：%s（%s 局 %d）"
                                      % (fmt(r), os.path.basename(fn), ri))
                # 反方向：副露手记成 -1 的帧，用 agari 复核「形是和的 + 真有役」
                if (kind == "draw" and not agari.menzen_of(pl["melds"])
                        and r["mentsu"] == -1):
                    wk = mjlog.kind_of(ev["tile"])
                    sw = 27 + (seat - st["oya"]) % 4
                    rw = 27 + st["round"] // 4
                    ok_shape = bool(agari.shapes_of(pl["hand"], pl["melds"]))
                    ok_yaku = ok_shape and _score_ok(
                        _less(counts_of(pl["hand"]), wk), pl["melds"], wk, sw, rw)
                    open_m1[0] += 1
                    if not ok_shape or not ok_yaku:
                        open_m1_bad[0] += 1
                        if open_m1_bad[0] <= 3:
                            print("  FAIL 副露手 -1 帧经 agari 复核不成立（形 %s / 役 %s）：%s（%s 局 %d）"
                                  % (ok_shape, ok_yaku, fmt(r), os.path.basename(fn), ri))
                # 立直（含宣言后未打牌）的家：这次摸牌前的 13 张一定听牌
                if kind == "draw" and (pl["riichi"] or pl["riichiPending"]):
                    c = counts_of(pl["hand"])
                    c[mjlog.kind_of(ev["tile"])] -= 1
                    r13 = shanten.shanten_of(
                        c, melds=pl["melds"],
                        seat_wind=27 + (seat - st["oya"]) % 4,
                        round_wind=27 + st["round"] // 4)
                    riichi_frames[0] += 1
                    if _min(r13) != 0:
                        riichi_bad[0] += 1
                        if riichi_bad[0] <= 3:
                            print("  FAIL 立直家 13 张非听牌：%s（%s 局 %d）"
                                  % (fmt(r13), os.path.basename(fn), ri))
                # 前 150 帧顺带量一下「四家全算」的代价
                if n_frame[0] <= 150:
                    tb = time.perf_counter()
                    for q in range(4):
                        if q != seat:
                            shanten.shanten_at(st, q)
                            n4[0] += 1
                    t4[0] += time.perf_counter() - tb
    total = time.perf_counter() - t0
    avg = total / n_frame[0] * 1000.0
    worst = max(times)
    print("  帧数 %d（每种帧 3 个向听数 ⇒ %d 次计算）" % (n_frame[0], n_calc[0]))
    print("  面子手向听数分布：-1 %d / 0 %d / 1 %d / 2 %d / >=3 %d"
          % (dist[-1], dist[0], dist[1], dist[2], dist[3]))
    print("  总耗时 %.2f s（平均 %.3f ms/帧，单帧最慢 %.2f ms）" % (total, avg, worst))
    eq(tsumo_bad[0], 0, "自摸和了前一帧一定是和牌（%d 帧）" % tsumo_frames[0])
    eq(ron_bad[0], 0, "荣和家的手牌 + 放铳牌一定能和（%d 帧）" % ron_frames[0])
    eq(riichi_bad[0], 0, "立直家的 13 张手牌一定听牌（%d 帧）" % riichi_frames[0])
    eq(fake_bad[0], 0, "副露手的假和牌（形和但无役）不记 -1（共 %d 帧）" % fake_frames[0])
    eq(open_m1_bad[0], 0, "副露手记成 -1 的帧经 agari 复核都是「形和 + 有役」（共 %d 帧）"
       % open_m1[0])
    if n4[0]:
        per_frame4 = t4[0] / 150.0 * 1000.0
        print("  四家全算：前 150 帧额外算 %d 次用 %.2f s（%.3f ms/帧），"
              "按此外推全部 %d 帧约 %.1f s"
              % (n4[0], t4[0], per_frame4, n_frame[0], per_frame4 * n_frame[0] / 1000.0))


def main():
    print("shanten_test：第 17 轮三种向听数（国士無双 / 七対子 / 面子手）")
    section1()
    section1b()
    section2()
    section3()
    section4()
    print("=== 结果：通过 %d 项，失败 %d 项 ===" % (OK[0], BAD[0]))
    if BAD[0]:
        print("有失败用例")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
