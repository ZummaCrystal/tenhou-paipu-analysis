"""向听数计算（第二类特征的基础，第 17 轮 m01278）。

三种牌型各算一个向听数，取值 {-1, 0, 1, 2, 3}：
  -1 = 已经和牌；0 = 听牌；n = 还差 n 次「打一张 + 摸一张」才能听牌；>= 3 一律记 3
  （内部值 3 = >=3；对外显示/导出时一律写成 >=3，见 cli.feat_value_text() 与
  web/js/app.js fmtFeatValue()，用户 m04115②）。

口径（m01278）：向听数 = 把当前手牌变成某个和牌形最少还要摸进几张牌（记 need，
向听数 = need - 1，need >= 4 一律记 3）。等价说法：往手里补 d 张牌后，手上存在一个
14-3n 张的和牌形（n = 自己副露数），求最小的 d。

进张必须结合场上信息：avail[kind] = 4 -（自己手牌 + 四家副露 + 四家牌河（被鸣走的那张
算在副露里，不再算牌河）+ 宝牌指示牌），某一种牌一共最多只能再摸 avail 张
（例：手里 1 张 4m、牌河与宝牌指示牌里能看见 2 张 4m ⇒ 最多再摸进 1 张 4m）。

起和役（m01436、m01701）：和牌形必须能通过「终局状态判别器」——从 block 拆分角度成立、却没有
任何役的「假和牌」要按没和牌处理（这种状态不能记 -1，到它的距离也不能当作向听数）。判定直接调用
`agari.sets_min_yaku_ok`（与 `agari` 的 18 种判别器、`score()` 共用同一个 `min_yaku_ok` 口径）：
立直（state == RIICHI）与门清自摸（門前清自摸和）自动通过，副露手与门清默听必须有真役，
宝牌（52/53/54）与偶发役（一发/槍槓/嶺上/海底/河底 = 2..6）不算。向听的「打一张 → 摸一张」模型里
最后摸进的牌就是和了张，所以一律按自摸判（`tsumo=True`）；门清手因此总有起和役。

三种牌型的和牌形：
  国士無双 = 13 种幺九牌各 1 张 + 其中一种成对（13 block）；
  七対子   = 7 个互不相同的对子（7 block）；
  面子手   = (4 - n) 组完整面子 + 一组雀头（n = 已有副露数；完整面子 = 刻子/顺子）。

本模块只吃「手牌 + 副露牌 + 各牌可见数 + 自风/场风」，不依赖 replay；`visible_counts` /
`avail_counts` / `shanten_at` 是 replay 状态的适配层。
"""

from . import agari
from .agari import counts_of, menzen_of, n_sets

KOKUSHI = "kokushi"
CHIITOI = "chiitoi"
MENSU = "mentsu"
SHAPES = (KOKUSHI, CHIITOI, MENSU)
SHAPE_NAMES = {KOKUSHI: "国士無双", CHIITOI: "七対子", MENSU: "面子手"}

CAP = 3
SENTINEL = CAP + 1

# 13 种幺九牌（1m/9m/1p/9p/1s/9s/東南西北白發中）
YAO_KINDS = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)

# 34 种牌各一组刻子 + 三个花色各 7 组顺子 = 55 种完整面子
GROUPS = tuple((k,) * 3 for k in range(34)) + tuple(
    (b + r, b + r + 1, b + r + 2) for b in (0, 9, 18) for r in range(7)
)


def suit_of(kind):
    """0-8 = m、9-17 = p、18-26 = s。"""
    return kind // 9


def rank_of(kind):
    """该花色内的序号 0-8（0 = 1）。"""
    return kind % 9


def cap(need):
    """「还差几张」→ 向听数（-1..3）：need 张牌才能凑成和牌形 ⇒ 向听数 need - 1。"""
    return CAP if need > CAP else need - 1


def _capacity(counts, avail):
    """每种牌最终能握在手里的上限 = 手里已有 + 还没露面的（avail 为 None 时不限）。"""
    if avail is None:
        return None
    return [counts[k] + avail[k] for k in range(34)]


def kokushi_need(counts, n_melds=0, avail=None):
    """国士無双还差几张（有副露 → SENTINEL）。"""
    if n_melds:
        return SENTINEL
    lim = _capacity(counts, avail)
    if lim is not None:
        for k in YAO_KINDS:
            if lim[k] < 1:
                return SENTINEL
    need = 13 - sum(1 for k in YAO_KINDS if counts[k] >= 1)
    for k in YAO_KINDS:                      # 手里已经有对子
        if counts[k] >= 2:
            return need
    for k in YAO_KINDS:                      # 单张 + 摸 1 张，或空着 + 摸 2 张
        if lim is None or lim[k] >= 2:
            return need + 1
    return SENTINEL


def chiitoi_need(counts, n_melds=0, avail=None):
    """七対子还差几张（有副露 → SENTINEL）；七対子必须 7 个互不相同的对子。"""
    if n_melds:
        return SENTINEL
    costs = []
    for k in range(34):
        c = counts[k]
        if c >= 2:                           # 手里 2 张算一对（3、4 张也只算一对）
            costs.append(0)
        else:
            if avail is not None and avail[k] < 2 - c:
                continue
            costs.append(2 - c)
    if len(costs) < 7:
        return SENTINEL
    costs.sort()
    return sum(costs[:7])


def group_set(g):
    """一组完整面子（kind 元组）→ agari 的面子格式：("tri", k, open, kan) / ("run", k, open, False)。"""
    if g[0] == g[1]:
        return ("tri", g[0], False, False)
    return ("run", g[0], False, False)


def has_open_yaku(sets, pair, melds=(), seat_wind=27, round_wind=27):
    """一副「暗面子组合 + 雀头 + 副露」是否满足起和条件（m01436 / m01701）。

    `sets` = 手牌里拆出的暗面子（kind 元组），副露的面子由 `melds` 补上。判定交给和牌判别器的
    内核 ``agari.sets_min_yaku_ok``：立直与门清自摸自动通过，副露手与门清默听必须有真役，
    宝牌与偶发役（一发/槍槓/嶺上/海底/河底）不算。向听模型按自摸判（`tsumo=True`）。
    """
    melds = tuple(melds or ())
    return agari.sets_min_yaku_ok([group_set(g) for g in sets], pair, melds,
                                  tsumo=True, seat_wind=seat_wind, round_wind=round_wind)


def mentsu_need(counts, n_melds=0, avail=None, melds=(), seat_wind=27, round_wind=27):
    """面子手还差几张才能和牌（need；找不到 <= 3 的拆法就返回 SENTINEL）。

    枚举「(4 - n) 组完整面子 + 一组雀头」的所有组合：每种面子要么全在手里（成本 0），
    要么缺几张就算摸进来几张（成本 = 缺的张数）。同一种牌一共摸不满 avail 张的组合直接
    跳过。成本只会越加越大，所以一旦 >= 当前最优值就剪枝。
     `melds` = 自家副露：有非暗杠副露时，没有役的拆法不算和牌（起和役，判别器判，m01436/m01701）。
    """
    melds = tuple(melds or ())
    if melds:
        n_melds = n_sets(melds)
    slots = 4 - n_melds
    if slots < 0:
        return SENTINEL
    need_yaku = not menzen_of(melds)
    best = [SENTINEL]
    used = [0] * 34                          # 已经用掉的手牌张数
    drawn = [0] * 34                         # 已经算成「摸进来」的张数
    chosen = []                              # 当前枚举出的暗面子（判起和役用）
    yaku_memo = {}                           # (暗面子组合, 雀头) -> 有没有役

    def take(kinds):
        """就地拿走一组牌（先用手里的，不够的算摸进来）；返回 (成本, undo)；不可行 None。"""
        undo = []
        cost = 0
        for k in kinds:
            if used[k] < counts[k]:
                used[k] += 1
                undo.append((k, 1))
            else:
                if avail is not None and drawn[k] + 1 > avail[k]:
                    for kk, hand in reversed(undo):
                        if hand:
                            used[kk] -= 1
                        else:
                            drawn[kk] -= 1
                    return None
                drawn[k] += 1
                undo.append((k, 0))
                cost += 1
        return cost, undo

    def untake(undo):
        for k, hand in reversed(undo):
            if hand:
                used[k] -= 1
            else:
                drawn[k] -= 1

    def rec(start, left, cost):
        if cost >= best[0] or best[0] == 0:
            return
        if left == 0:
            for k in range(34):              # 雀头
                if best[0] == 0:
                    return
                r = take((k, k))
                if r is None:
                    continue
                c = cost + r[0]
                if c < best[0]:
                    if not need_yaku:
                        best[0] = c
                    else:                    # 副露手：没有役的拆法不算和牌（判别器判起和役）
                        key = (tuple(sorted(chosen)), k)
                        ok = yaku_memo.get(key)
                        if ok is None:
                            ok = has_open_yaku(chosen, k, melds, seat_wind, round_wind)
                            yaku_memo[key] = ok
                        if ok:
                            best[0] = c
                untake(r[1])
            return
        for g in range(start, len(GROUPS)):
            r = take(GROUPS[g])
            if r is None:
                continue
            if cost + r[0] < best[0]:
                chosen.append(GROUPS[g])
                rec(g, left - 1, cost + r[0])
                chosen.pop()
            untake(r[1])

    rec(0, slots, 0)
    return best[0]


def shanten_of(counts, n_melds=0, avail=None, melds=(), seat_wind=27, round_wind=27):
    """三种牌型各算一次 → {'kokushi': …，'chiitoi': …，'mentsu': …}（-1..3）。

    有副露时必须把副露牌传进 `melds`（起和役交给和牌判别器判，m01436/m01701）；只给 `n_melds` 会报错。
    国士無双 / 七対子本身要求门清（有副露直接无解），所以起和役只影响面子手。
    """
    melds = tuple(melds or ())
    if melds:
        n_melds = n_sets(melds)
    elif n_melds:
        raise ValueError("有副露时必须传 melds（起和役要按副露牌判，m01436）")
    return {
        KOKUSHI: cap(kokushi_need(counts, n_melds, avail)),
        CHIITOI: cap(chiitoi_need(counts, n_melds, avail)),
        MENSU: cap(mentsu_need(counts, n_melds, avail, melds, seat_wind, round_wind)),
    }


def min_shanten(values):
    """{牌型: 向听数} → 其中最小的一个（整体向听数）。"""
    return min(values.values())


def visible_counts(state, seat):
    """某个座位视角的「可见牌」计数：自己手牌 + 四家副露 + 四家牌河（被鸣走的不算）+ 宝牌指示牌。"""
    out = [0] * 34
    for tid in state["players"][seat]["hand"]:
        out[tid // 4] += 1
    for pl in state["players"]:
        for m in pl["melds"]:
            for tid in m["tiles"]:
                out[tid // 4] += 1
        for r in pl["river"]:
            if not r.get("called"):
                out[r["tile"] // 4] += 1
    for tid in state["dora"]:
        out[tid // 4] += 1
    return out


def avail_counts(state, seat):
    """各牌种还能摸到的张数 = 4 - 可见张数。"""
    return [4 - v for v in visible_counts(state, seat)]


def shanten_at(state, seat):
    """截面上某个座位的三种向听数（手牌、副露牌、场上可见牌、自风/场风）。

    自风 = 27 + (seat - oya) % 4（东 27/南 28/西 29/北 30），场风 = 27 + 局数 // 4。
    """
    pl = state["players"][seat]
    return shanten_of(
        counts_of(pl["hand"]),
        avail=avail_counts(state, seat),
        melds=pl["melds"],
        seat_wind=27 + (seat - state["oya"]) % 4,
        round_wind=27 + state["round"] // 4,
    )