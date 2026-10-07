# -*- coding: utf-8 -*-
"""第 19 轮：12 个「期望」特征的计算（期望听牌枚数 / 绝对枚数 / 期望打点）。

口径（用户 m01875 / m01877，修订 m02073 / m02075 / m02389；本轮只做「计算」，暂不入库、不接界面）：

1. 目标状态：从当前帧（含该帧刚摸到或刚鸣到的牌）出发，按**最小向听数**（国士無双 / 七対子 /
   面子手三者取最小）达到听牌状态（或和牌状态）。
2. 进张概率：``p(k) = 剩余未见张数(k) / 剩余未见总张数``；剩余未见张数 = ``avail[k] - 已假想摸进的
   张数(k)``、分母 = ``Σavail - 已假想摸进的总张数``（m02073：假想摸到的牌必须扣掉，否则概率分布
   会和实际情形对不上，还会出现「摸到第 5 张同种牌」这种不可能的路线）。``avail = 4 - 可见牌``，
   可见牌 = 自己手牌 + 四家副露 + 四家牌河（被鸣走的不算） + 宝牌指示牌；每一步都用「该步的
   剩余未见牌」。
3. 只看「没有一次进张浪费」的完美路线：每次进张后都要能打出一张使最小向听数正好 -1，否则这条
   路线不计（该进张的贡献记 0）。
4. 期望听牌枚数 = 「**有役听牌**」前提下的**条件期望**（用户 m02647；分母口径按 m02766 修订，与第 5
   条同构）：先把「有役听牌」叶子的到达概率归一化，再对枚数加权求和，即
   ``Σ [ p(叶子) / Σ p(有役听牌叶子) ] x 听牌枚数`` —— 达到听牌状态的概率本身不计入（那是听牌强度
   关心的量）。「有役」= 该假设 / 模式下存在**满足起和役**的和牌张（``agari.evaluate`` 判定，起和役
   门槛见第 6 条）；无役的听牌状态既不进分子、也不进分母（否则会把均值拉低）。节点里的分子
   ``("tp", ...)`` = Σ p x 枚数、分母 ``("tq", ...)`` = 同一批有役听牌叶子的 Σ p（叶子值 1.0 / 0.0）。
   - 聚合口径两种都算：``"sum"`` = 每一条完美路线都计入（同一状态的多条路线概率相加，等价于
     「对可达听牌状态求和」，默认），分子 / 分母按同一套路线各自求和后相除；``"best"`` = 同一个
     进张下打牌取让**枚数分子**最大的那一张（argmax，与第 5 条的打牌选择同构），分子 / 分母都取
     这一条分支。
   - 期望枚数：和牌张数按剩余未见张数计；绝对枚数：按 ``4 - 自己握着的张数``（手牌 + 副露）计，
     不再看牌桌公共信息（用户用它把「两面听 8 枚」这类熟悉的数字对上）。
5. 期望打点 = 「已经和牌」前提下的**条件期望**（用户 m02389）：先把所有和牌叶子的概率归一化，
   再对得点加权求和，即 ``Σ [ p(叶子) / Σ p(和牌叶子) ] x 得点`` —— 达到和牌状态的概率本身不计入
   （那是听牌强度关心的量）。打牌的选择仍然按 ``argmax{ p(打完的后继状态 -> 和牌状态) x 和牌打点 }``
   （= 未归一化的 ``Σ p·得点``，与归一化后的 argmax 等价）：每个打牌层都只走这条 argmax 分支，同一
   分支上的和牌概率 p 一起带走、作为归一化的分母（6 个枚数项同理，见第 4 条：只是把「和牌概率 x
   得点」换成「听牌概率 x 枚数」）。得点 = ``agari.score(...)["gain"]``（含本场 / 供托 / **表宝牌**——宝牌指示牌是场上公开信息，
   按 ``state["dora"]`` 计入 ``ctx``；不含里宝牌 / 一发 / 嶺上 / 海底等偶发役与未知信息，赤 5 按非赤牌算）。
6. 副露 / 门清两套假设（m02075、m02512）：带「副露」字样的 6 项（4 个枚数 + 2 个打点）**不管这一
   帧是不是门清**，都按「有副露」（门清役不存在）判定起和役与算番；门清帧再额外交出 2 个枚数项
   与 4 个打点项 —— 打点按两种假想各算一遍：**立直** = 保持门清直到听牌、在听牌时宣布立直
   （立直本身就是役，起和役门槛自动通过；本帧已经宣布立直时沿用它自己的立直番数），**默听** =
   保持门清但不宣布立直（荣和必须有真役，自摸有門前清自摸和）。两种假想都不看偶发 / 特殊役
   （一発 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底）。副露帧没有「假想门清」可言（碰出去的牌收不回来），
   所以门清项在副露帧记 0。门清枚数按自摸门槛（門前清自摸和）计，与自摸 / 荣和 / 立直 / 默听
   无关，两种假想共用。
7. 枚举方式（m02073）：整棵「进张 -> 打牌 -> 再进张」的递归树只走一遍，每个节点算一次向听数，
   每张候选和牌张只做一次候选拆解枚举（``agari.evaluate`` 同时给出「能不能和」与「打点」），
   12 项特征都从这同一个节点字典里聚合出来；后续的听牌强度等特征也在这里加键。
8. 边界：向听数 >= 3（默认 > 上限 1）时 12 项一律 0；已和牌的帧：枚数 = 0、打点 = 直接按该手牌算
   （取所有和了张里最大）。13-3n 张的帧直接算；14-3n 张（摸牌帧 / 吃碰帧）先打一张：枚数按「打到
   最小向听数」的那些打牌聚合（sum 口径下先把分子 / 分母各自求和、再相除，见第 4 条），打点在
   「打到最小向听数」的打牌里按 ``argmax{p x 打点}`` 选一手，再用
   同一手的和牌概率归一化（不评估让向听数变大的打牌：那会再深一层枚举，代价高且不是有意义的打法）。
   默认只算到向听数 1（``DEFAULT_MAX_SHANTEN``），可用 ``max_shanten`` 调高。
"""

from . import agari, shanten
from .agari import DAMATEN, FURO, RIICHI, RON, TSUMO
from .shanten import GROUPS

# 允许计算的最大向听数：>= 3 一律记 0（枚举深度到这里不可行，见模块 docstring 第 8 条）
MAX_SHANTEN = 2
# 默认上限。向听数 2 的帧要枚举两层（单帧约 10 s，见第 19 轮报告），默认只算到 1。
DEFAULT_MAX_SHANTEN = 1

# 「假想状态」：副露手（门清役不存在）/ 门清 + 立直 / 门清 + 默听（用户 m02512）
FURO_ASSUME = "furo"
RIICHI_ASSUME = "riichi"
DAMATEN_ASSUME = "damaten"
MENZEN_ASSUME = "menzen"                              # 门清枚数项（立直 / 默听共用）
ASSUMES = (FURO_ASSUME, RIICHI_ASSUME, DAMATEN_ASSUME)      # 打点键（sc / ms）用它
MENZEN_ASSUMES = (RIICHI_ASSUME, DAMATEN_ASSUME)           # 门清打点的两种假想

# 12 个特征：key -> 显示名
FEATURES = [
    ("furo_tsumo_tenpai_expect", "副露自摸期望听牌枚数"),
    ("furo_tsumo_tenpai_abs", "副露自摸期望听牌绝对枚数"),
    ("furo_ron_tenpai_expect", "副露荣和期望听牌枚数"),
    ("furo_ron_tenpai_abs", "副露荣和期望听牌绝对枚数"),
    ("menzen_tenpai_expect", "立直/默听期望听牌枚数"),
    ("menzen_tenpai_abs", "立直/默听期望听牌绝对枚数"),
    ("furo_ron_score", "副露荣和期望打点"),
    ("furo_tsumo_score", "副露自摸期望打点"),
    ("riichi_ron_score", "立直荣和期望打点"),
    ("riichi_tsumo_score", "立直自摸期望打点"),
    ("damaten_ron_score", "默听荣和期望打点"),
    ("damaten_tsumo_score", "默听自摸期望打点"),
]
NAMES = dict(FEATURES)
KEYS = [k for k, _n in FEATURES]


def tid_of(kind):
    """某种牌的代表 id（避开赤 5：5 用该种的第 2 个 id）。"""
    if kind < 27 and kind % 9 == 4:
        return kind * 4 + 1
    return kind * 4


def tiles_of(counts):
    """34 项计数 -> 牌 id 列表（同种重复用同一个 id，``counts_of`` 只看张数）。"""
    out = []
    for k in range(34):
        for _ in range(counts[k]):
            out.append(tid_of(k))
    return out


def _mentsu_waits(counts, slots):
    """面子手：还差 1 张就能凑成 ``slots`` 组面子 + 雀头时，返回可和的所有牌种（不看起和役）。

    就是 ``shanten.mentsu_need`` 的 DFS，但只允许「摸 1 张」，把那张牌的种类收集起来。
    只看手牌形状（不看可见牌，也不看起和役）—— 可见牌与起和役的过滤在 ``Expect`` 里做。
    """
    out = set()
    used = [0] * 34
    drawn = [0] * 34

    def untake(undo):
        for k, hand in reversed(undo):
            if hand:
                used[k] -= 1
            else:
                drawn[k] -= 1

    def take(kinds):
        undo = []
        cost = 0
        for k in kinds:
            if used[k] < counts[k]:
                used[k] += 1
                undo.append((k, 1))
            else:
                drawn[k] += 1
                undo.append((k, 0))
                cost += 1
        return cost, undo

    def rec(start, left, cost):
        if cost > 1:
            return
        if left == 0:
            for k in range(34):                    # 雀头
                r = take((k, k))
                if cost + r[0] == 1:
                    for kk in range(34):
                        if drawn[kk] > 0:
                            out.add(kk)
                untake(r[1])
            return
        for g in range(start, len(GROUPS)):
            r = take(GROUPS[g])
            if cost + r[0] <= 1:
                rec(g, left - 1, cost + r[0])
            untake(r[1])

    rec(0, slots, 0)
    return out


def waits_of(counts, melds=()):
    """形状上还差一张就能和牌的牌种集合（不看起和役；三种牌型取并集）。"""
    melds = tuple(melds or ())
    mels = agari.set_melds(melds)
    out = set()
    if agari.menzen_of(melds) and not mels:
        if shanten.kokushi_need(counts, 0, None) == 1:
            if any(counts[k] >= 2 for k in shanten.YAO_KINDS):
                out |= set(k for k in shanten.YAO_KINDS if counts[k] == 0)
            else:
                out |= set(shanten.YAO_KINDS)
        if shanten.chiitoi_need(counts, 0, None) == 1:
            out |= set(k for k in range(34) if counts[k] == 1)
    out |= _mentsu_waits(counts, 4 - len(mels))
    return out


# 特征名映射
TENPAI_KEYS = {
    (FURO, TSUMO, "avail"): "furo_tsumo_tenpai_expect",
    (FURO, TSUMO, "abs"): "furo_tsumo_tenpai_abs",
    (FURO, RON, "avail"): "furo_ron_tenpai_expect",
    (FURO, RON, "abs"): "furo_ron_tenpai_abs",
}
MENZEN_TENPAI_KEYS = {"avail": "menzen_tenpai_expect", "abs": "menzen_tenpai_abs"}
SCORE_KEYS = {
    (FURO, TSUMO): "furo_tsumo_score",
    (FURO, RON): "furo_ron_score",
    (RIICHI, TSUMO): "riichi_tsumo_score",
    (RIICHI, RON): "riichi_ron_score",
    (DAMATEN, TSUMO): "damaten_tsumo_score",
    (DAMATEN, RON): "damaten_ron_score",
}
AGGS = ("sum", "best")


def _zeros():
    """节点字典的键（见 Expect.node）：枚数的分子 (``"tp"``) 与分母 (``"tq"``) + 打点的分子
    (``"sc"``) 与分母 (``"ms"``)，共 36 个。

    ``("sc", assume, mode)`` = 该分支上 Σ p·得点（未归一化），``("ms", assume, mode)`` = 同一分支上
    的和牌概率 Σ p；帧级打点特征 = 两者的商（用户 m02389）。
    ``("tp", ...)`` = Σ p x 听牌枚数、``("tq", ...)`` = 同一批听牌叶子的 Σ p；帧级枚数特征 = 两者的
    商（用户 m02647：听牌枚数也要先归一化再加权）。
    """
    out = {}
    for agg in AGGS:
        for mode in (TSUMO, RON):
            for measure in ("avail", "abs"):
                out[("tp", FURO_ASSUME, agg, mode, measure)] = 0.0
                out[("tq", FURO_ASSUME, agg, mode, measure)] = 0.0
        for measure in ("avail", "abs"):
            out[("tp", MENZEN_ASSUME, agg, measure)] = 0.0
            out[("tq", MENZEN_ASSUME, agg, measure)] = 0.0
    for assume in ASSUMES:
        for mode in (TSUMO, RON):
            out[("sc", assume, mode)] = 0.0
            out[("ms", assume, mode)] = 0.0
    return out


class Expect(object):
    """一帧（某个座位）的 12 个期望特征计算器。

    ``agg`` = 期望听牌枚数的打牌聚合口径（"sum" / "best"，见模块 docstring）；
    ``compute()`` 同时返回另一种口径的值（``alt``）。
    """

    def __init__(self, state, seat, agg="sum", max_shanten=DEFAULT_MAX_SHANTEN):
        if agg not in AGGS:
            raise ValueError("agg 只能是 sum / best")
        if not 0 <= max_shanten <= MAX_SHANTEN:
            raise ValueError("max_shanten 只能是 0..%d" % MAX_SHANTEN)
        self.state = state
        self.seat = seat
        self.agg = agg
        self.max = max_shanten
        pl = state["players"][seat]
        self.melds = tuple(pl["melds"])
        self.counts = agari.counts_of(pl["hand"])
        self.size = sum(self.counts)
        self.n13 = agari.concealed_size(self.melds)          # 13 - 3 * 副露组数
        self.avail = shanten.avail_counts(state, seat)
        self.dora = tuple(state.get("dora") or ())           # 宝牌指示牌（牌 id，场上公开信息）
        self.unseen = sum(self.avail)
        self.sw = 27 + (seat - state["oya"]) % 4             # 自风
        self.rw = 27 + state["round"] // 4                   # 场风
        self.oya = (seat == state["oya"])
        self.honba = state["honba"]
        self.kyotaku = state["kyotaku"]
        self.menzen = agari.menzen_of(self.melds)
        riichi = bool(pl["riichi"] or pl["riichiPending"])
        self.cat = FURO if not self.menzen else (RIICHI if riichi else DAMATEN)
        self.riichi = 1 if self.cat == RIICHI else 0
        self.meldc = [0] * 34                                # 副露里的张数（绝对枚数用）
        for m in agari.set_melds(self.melds):
            for tid in (m.get("tiles") or ()):
                self.meldc[agari.kind_of(tid)] += 1
        self._zero_used = (0,) * 34        # dist / node 的默认 used（还没假想摸进任何牌）
        self._dists = {}
        self._waits = {}
        self._evals = {}
        self._nodes = {}

    # ------------------------------------------------------------ 缓存的基本量
    def _avail_left(self, used):
        """扣掉「已经假想摸进」的牌之后，各种牌的剩余未见张数（m02073）。"""
        return [self.avail[k] - used[k] for k in range(34)]

    def _unseen_left(self, used):
        """剩余未见总张数（概率分母）。"""
        return self.unseen - sum(used)

    def dist(self, counts, used=None):
        """最小向听数（三种牌型取最小；面子手已含起和役判定；可见牌用剩余未见牌）。"""
        used = self._zero_used if used is None else tuple(used)
        key = (tuple(counts), used)
        v = self._dists.get(key)
        if v is None:
            v = shanten.min_shanten(shanten.shanten_of(
                counts, melds=self.melds, avail=self._avail_left(used),
                seat_wind=self.sw, round_wind=self.rw))
            self._dists[key] = v
        return v

    def waits(self, counts):
        """形状听牌张（与可见牌、起和役无关；两种假设共用，所以缓存键只看手牌）。"""
        key = tuple(counts)
        v = self._waits.get(key)
        if v is None:
            v = waits_of(counts, self.melds)
            self._waits[key] = v
        return v

    def _eval(self, counts, kind, tsumo, assume):
        """这张和了张在某种假设下的自家得点；不能和（牌型 / 起和役不成立）时返回 None。

        一次 ``agari.evaluate()`` 同时回答「有没有役」与「打点多少」（m02073：别把候选拆解
        枚举跑两遍）。结果与「已假想摸进的牌」无关，所以缓存键里不含 used。
        """
        key = (tuple(counts), kind, bool(tsumo), assume)
        if key in self._evals:
            return self._evals[key]
        if assume == FURO_ASSUME:
            st, riichi, menzen = FURO, 0, False
        elif assume == RIICHI_ASSUME:
            # m02512：本帧已宣布立直就沿用它自己的番数；否则按「保持门清到听牌、宣布立直」算 1 番
            st, riichi, menzen = RIICHI, (self.riichi or 1), True
        else:
            st, riichi, menzen = DAMATEN, 0, True
        r = agari.evaluate(tiles_of(counts), self.melds, win_tile=tid_of(kind), tsumo=bool(tsumo),
                           ctx={"dora": self.dora},
                           oya=self.oya, honba=self.honba, kyotaku=self.kyotaku,
                           seat_wind=self.sw, round_wind=self.rw, riichi=riichi,
                           state=st, menzen=menzen)
        v = float(r["gain"]) if r else None
        self._evals[key] = v
        return v

    def _tiles(self, counts, kinds, measure, used):
        """和牌张数：剩余未见张数（期望枚数）/ 4 - 自己握着（手牌 + 副露）（绝对枚数）。"""
        if measure == "avail":
            return float(sum(self.avail[k] - used[k] for k in kinds))
        return float(sum(4 - counts[k] - self.meldc[k] for k in kinds))

    # ------------------------------------------------------------ 主枚举
    def node(self, counts, used=None):
        """13-3n 张手牌（刚打完牌、等待下一张进张）的各项值（内部键，见 ``_zeros``）。"""
        used = self._zero_used if used is None else tuple(used)
        key = (tuple(counts), used)
        v = self._nodes.get(key)
        if v is not None:
            return v
        d = self.dist(counts, used)
        out = _zeros()
        if d < 0 or d > self.max:
            self._nodes[key] = out
            return out
        al = self._avail_left(used)
        ul = self._unseen_left(used)
        if d == 0:                                          # 听牌：叶子（枚举和牌张 + 判役 + 取点）
            waits = self.waits(counts)
            for mode in (TSUMO, RON):
                tsumo = (mode == TSUMO)
                got = [k for k in waits if self._eval(counts, k, tsumo, FURO_ASSUME) is not None]
                for measure in ("avail", "abs"):
                    n = self._tiles(counts, got, measure, used)
                    for agg in AGGS:
                        out[("tp", FURO_ASSUME, agg, mode, measure)] = n
                        # 归一化的分母（m02647 / m02766）：只有「这个假设 / 模式下存在满足起和役的
                        # 和牌张」的听牌叶子才计入 => 报告值是 E[枚数 | 有役听牌]；无役的听牌状态
                        # （分子本来就是 0）不该把均值拉低
                        out[("tq", FURO_ASSUME, agg, mode, measure)] = 1.0 if got else 0.0
                sc = 0.0
                ms = 0.0                                    # 和牌概率（打点归一化的分母，m02389）
                if ul > 0:
                    for k in got:
                        p = al[k] / float(ul)
                        sc += p * self._eval(counts, k, tsumo, FURO_ASSUME)
                        ms += p
                out[("sc", FURO_ASSUME, mode)] = sc
                out[("ms", FURO_ASSUME, mode)] = ms
            if self.menzen:                                 # 门清假设（副露帧不存在「假想门清」）
                for measure in ("avail", "abs"):
                    n = self._tiles(counts, waits, measure, used)   # 门清自摸必有役 => 全部形状听牌
                    for agg in AGGS:
                        out[("tp", MENZEN_ASSUME, agg, measure)] = n
                        out[("tq", MENZEN_ASSUME, agg, measure)] = 1.0   # 门清自摸必有役 => 必为有役听牌
                for assume in MENZEN_ASSUMES:           # 立直 / 默听两种假想各算一遍（m02512）
                    for mode in (TSUMO, RON):
                        tsumo = (mode == TSUMO)
                        sc = 0.0
                        ms = 0.0
                        if ul > 0:
                            for k in waits:
                                g = self._eval(counts, k, tsumo, assume)
                                if g is not None:
                                    p = al[k] / float(ul)
                                    sc += p * g
                                    ms += p
                        out[("sc", assume, mode)] = sc
                        out[("ms", assume, mode)] = ms
            self._nodes[key] = out
            return out
        for t in range(34):                                 # 进张
            if counts[t] >= 4 or al[t] <= 0:
                continue
            newc = list(counts)
            newc[t] += 1
            nu = list(used)
            nu[t] += 1
            nu = tuple(nu)
            # 14 张的向听数 = 「打一张之后」的最小向听数：不等于 d-1 就直接跳过这一张，
            # 不必再逐张试打牌（省下大量 dist 调用；仍与逐个试打等价）。
            if self.dist(newc, nu) != d - 1:
                continue
            kids = []
            for c in range(34):                             # 打牌（只留让向听数正好 -1 的）
                if newc[c] <= 0:
                    continue
                h = list(newc)
                h[c] -= 1
                if self.dist(h, nu) == d - 1:
                    kids.append(self.node(h, nu))
            if not kids:
                continue
            p = al[t] / float(ul)
            # 打牌层的选择：argmax{p(打完的后继状态 -> 和牌状态) x 和牌打点} = argmax 未归一化的
            # ("sc", ...)（用户 m02389：打牌仍然要考虑达到和牌状态的概率）；同一条分支上的和牌
            # 概率 ("ms", ...) 跟着一起走，作为归一化的分母。
            chosen = {}
            for assume in ASSUMES:
                for mode in (TSUMO, RON):
                    kk = ("sc", assume, mode)
                    chosen[kk] = max(kids, key=lambda g: g[kk])
            # 枚数的分母 ("tq", ...) 必须统计与分子 ("tp", ...) 同一批听牌状态（用户 m02647），
            # 所以跟着对应分子的 best 分支走；打牌层仍然按未归一化的分子 argmax。
            for kk in list(out.keys()):
                if kk[0] not in ("tp", "tq"):
                    continue
                src = list(kk)
                src[0] = "tp"
                src[2] = "best"
                src = tuple(src)
                if src not in chosen:
                    chosen[src] = max(kids, key=lambda g: g[src])
                chosen[kk] = chosen[src]
            for kk in list(out.keys()):
                if kk[0] == "sc":
                    out[kk] += p * chosen[kk][kk]
                elif kk[0] == "ms":
                    out[kk] += p * chosen[("sc",) + kk[1:]][kk]
                else:
                    agg = kk[2]
                    if agg == "sum":
                        out[kk] += p * sum(g[kk] for g in kids)
                    else:                                   # best：取分子最大的那一手（tp / tq 同分支）
                        out[kk] += p * chosen[kk][kk]
        self._nodes[key] = out
        return out

    def _score_now(self, mode, assume):
        """已和牌的手牌：取所有和了张 / 读法里最大的自家得点（某种假设下）。"""
        tsumo = (mode == TSUMO)
        best = 0.0
        for k in range(34):
            if self.counts[k] <= 0:
                continue
            h = list(self.counts)
            h[k] -= 1
            g = self._eval(h, k, tsumo, assume)
            if g and g > best:
                best = g
        return best

    # ------------------------------------------------------------ 聚合到 12 项
    def _pick_sum(self, nodes, key):
        return sum(g[key] for g in nodes)

    def _pick_best(self, nodes, key):
        return max(g[key] for g in nodes)

    def _pick_score(self, nodes, assume, mode):
        """期望打点：和牌前提下的条件期望（用户 m02389）。

        分子 = ``argmax{p x 打点}`` 选出的那一手打牌上的 Σ p·得点（节点键 ``("sc", ...)``）；分母 =
        同一条分支上的和牌概率 Σ p（``("ms", ...)``）。也就是先把各和牌叶子的概率归一化，再加权求和；
        达到和牌状态的概率本身不计入（那是听牌强度关心的量）。分母为 0（无役 / 和不了）时给 0。
        """
        if not nodes:
            return 0.0
        best = max(nodes, key=lambda g: g[("sc", assume, mode)])
        ms = best[("ms", assume, mode)]
        if ms <= 0:
            return 0.0
        return best[("sc", assume, mode)] / ms

    def _pick_tenpai(self, nodes, key_num, key_den, agg):
        """期望听牌枚数 / 绝对枚数：把听牌叶子的概率归一化后再对枚数加权（用户 m02647）。

        分子 = ``Σ p x 枚数``（节点键 ``("tp", ...)``）、分母 = 同一批听牌叶子的 ``Σ p``
        （``("tq", ...)``，叶子值 1.0）—— 即「已经达到听牌状态」前提下的条件期望，达到听牌状态的
        概率本身不计入。``agg == "best"`` 时取「枚数分子最大」的那一手打牌上的比值（打牌选择仍按
        未归一化的分子，与打点同构）。分母为 0（这条路线到不了听牌）时给 0。
        """
        if not nodes:
            return 0.0
        if agg == "sum":
            num = self._pick_sum(nodes, key_num)
            den = self._pick_sum(nodes, key_den)
        else:
            best = max(nodes, key=lambda g: g[key_num])
            num = best[key_num]
            den = best[key_den]
        if den <= 0:
            return 0.0
        return num / den

    def _assign_tp(self, feats, alt, nodes, keys, out_key):
        """``keys`` = (分子 sum, 分母 sum, 分子 best, 分母 best) 四个节点键。"""
        v_sum = self._pick_tenpai(nodes, keys[0], keys[1], "sum")
        v_best = self._pick_tenpai(nodes, keys[2], keys[3], "best")
        feats[out_key] = v_sum if self.agg == "sum" else v_best
        alt[out_key] = v_best if self.agg == "sum" else v_sum

    def _assign_all(self, feats, alt, nodes):
        """把节点字典里的键摊到 12 个特征（副露帧只摊副露那 6 项）。"""
        for mode in (TSUMO, RON):
            for measure in ("avail", "abs"):
                self._assign_tp(feats, alt, nodes, (
                    ("tp", FURO_ASSUME, "sum", mode, measure),
                    ("tq", FURO_ASSUME, "sum", mode, measure),
                    ("tp", FURO_ASSUME, "best", mode, measure),
                    ("tq", FURO_ASSUME, "best", mode, measure),
                ), TENPAI_KEYS[(FURO, mode, measure)])
            feats[SCORE_KEYS[(FURO, mode)]] = self._pick_score(nodes, FURO_ASSUME, mode)
        if not self.menzen:
            return
        for measure in ("avail", "abs"):
            self._assign_tp(feats, alt, nodes, (
                ("tp", MENZEN_ASSUME, "sum", measure),
                ("tq", MENZEN_ASSUME, "sum", measure),
                ("tp", MENZEN_ASSUME, "best", measure),
                ("tq", MENZEN_ASSUME, "best", measure),
            ), MENZEN_TENPAI_KEYS[measure])
        for mode in (TSUMO, RON):
            feats[SCORE_KEYS[(RIICHI, mode)]] = self._pick_score(nodes, RIICHI_ASSUME, mode)
            feats[SCORE_KEYS[(DAMATEN, mode)]] = self._pick_score(nodes, DAMATEN_ASSUME, mode)

    def compute(self):
        """-> (12 个特征值, 另一种打牌聚合口径下的 6 个期望听牌枚数特征)。

    6 个打点项 = 和牌前提下的条件期望（分母 = 同一条 argmax 分支上的和牌概率，m02389）。
    """
        feats = dict((k, 0.0) for k in KEYS)
        alt = dict((k, 0.0) for k in KEYS)
        used = (0,) * 34
        if self.size not in (self.n13, self.n13 + 1):
            return feats, alt
        if self.size == self.n13 + 1:                       # 摸牌帧 / 吃碰帧：先打一张
            d0 = self.dist(self.counts, used)
            # 14 张的向听数 = 打一张之后的最小向听数（唯一的例外是已经和牌：-1 < 0），
            # 所以超过上限时可以直接返回，不必再逐张试打牌（省下 14~34 次 dist 调用）。
            if d0 > self.max:
                return feats, alt
            if d0 == -1:                                    # 已经和牌：枚数按设计 0，只给打点
                for mode in (TSUMO, RON):
                    feats[SCORE_KEYS[(FURO, mode)]] = self._score_now(mode, FURO_ASSUME)
                    if self.menzen:
                        feats[SCORE_KEYS[(RIICHI, mode)]] = self._score_now(mode, RIICHI_ASSUME)
                        feats[SCORE_KEYS[(DAMATEN, mode)]] = self._score_now(mode, DAMATEN_ASSUME)
                return feats, alt
            dmin = None
            keep = []                                       # 打到最小向听数的打牌
            for c in range(34):
                if self.counts[c] <= 0:
                    continue
                h = list(self.counts)
                h[c] -= 1
                d = self.dist(h, used)
                if dmin is None or d < dmin:
                    dmin, keep = d, [h]
                elif d == dmin:
                    keep.append(h)
            if dmin is None or dmin > self.max:
                return feats, alt
            self._assign_all(feats, alt, [self.node(h, used) for h in keep])
            return feats, alt
        self._assign_all(feats, alt, [self.node(self.counts, used)])
        return feats, alt


def values_both(state, seat, agg="sum", max_shanten=DEFAULT_MAX_SHANTEN):
    """-> (12 个特征值, alt)；不在本帧范畴的特征 = 0.0。"""
    return Expect(state, seat, agg=agg, max_shanten=max_shanten).compute()


def values(state, seat, agg="sum", max_shanten=DEFAULT_MAX_SHANTEN):
    """该帧该座位的 12 个期望特征值（不在本帧范畴的项 = 0.0）。"""
    return values_both(state, seat, agg=agg, max_shanten=max_shanten)[0]