# -*- coding: utf-8 -*-
r"""第二类特征：立直家（他家）危险筋组数量 / 危险两面组数（用户 m02865）。

打点视角 = 当前摸牌者 / 副露者自己（"自家" = 摸牌者，"他家" = 另外三家）。

口径（全部来自用户 m02865）
    1. **-1**：其他家无人立直（即第一类特征「立直家（他家）数量」= 0）时，两项都取 -1；
       有立直家时取非负整数。
    2. **立直家的安全牌** = ① 该立直家打出过的所有牌（无论是否被其他家鸣走）
       + ② 立直动作发生后，场上任何一家打出过的牌（不包括暗杠）。
       「立直动作发生」取宣告那一刻（mjlog ``REACH step="1"``，宣言牌打出之后）：宣告之后、
       别家在他 step="2" 之前打出的那张牌也算「立直动作发生后」。暗杠不是出牌事件，
       天然不进 ②。
    3. **筋组**：m/p/s 中数字相差 3 的两种牌构成一个筋组，三种花色 x
       {1,4},{2,5},{3,6},{4,7},{5,8},{6,9}，共 **18 组**；每组对应一种両面 = 构成筋组的
       两种牌中间间隔的两张牌（筋组 25m -> 両面 34m）。
    4. **危险筋组**：以下两种情形之一成立则该筋组（両面）**安全**，否则危险：
       ① 该筋组中存在至少一种牌是立直家的安全牌；
       ② 主视角视野中（自身手牌 + 公共信息）该筋组对应両面中至少有一种牌能看到 4 张。
       危险筋组数量 = 危险组的计数（0..18）。
    5. **危险两面组数** = 对每个危险筋组，把両面两张牌「主视角看不到的张数」相乘后相加
       （加法原理 + 乘法原理）：筋组 14m 危险、主视角看到 2 张 2m、1 张 3m
       => 2m 剩 2 张、3m 剩 3 张 => 両面 23m 共 2 x 3 = 6 组。
    6. **多家立直**：危险 = 对**任意一家**立直家危险；安全 = 对**全体**立直家均安全，即
       组安全 <=> ② 成立 或（对每家立直家 X，X 的安全牌里都含该筋组的至少一种牌）；
       危险 <=> 非 ② 且（存在立直家 X 的安全牌里不含该筋组任何一张）。

出牌序
    「立直动作发生后，场上任何一家打出过的牌」需要**全局出牌序**，而 replay 的状态里只有
    各家自己的牌河顺序（river 条目没有全局序号）=> 本模块用 :class:`DangerLog` 按事件顺序
    维护全局出牌序与各家立直位置（``feed(ev)``，与 ``replay.apply_event`` 同序调用），
    逐帧复用它；``values_at()`` 是一次性取数（回放到指定帧再算）的便利入口。
    可见张数复用 ``shanten.visible_counts``（自己手牌 + 四家副露（含暗杠）+ 四家牌河
    （被鸣走的那张算在副露里、不再算牌河）+ 宝牌指示牌），与向听 / 期望特征同口径。

本模块只吃「状态 + 出牌序 + 立直位置」；立直状态复用 feats.is_riichi（函数内延迟导入，
因为 feats 模块级 import danger，模块级互相 import 会造成循环导入），不依赖 DB / 界面。
"""
from . import replay, shanten

# 18 个筋组：(筋组第一张 kind, 筋组第二张 kind, 両面第一张 kind, 両面第二张 kind)
#   筋组 = 同花色数字相差 3 的两种牌（n 与 n+3）；両面 = 中间间隔的两张（n+1 与 n+2）
SUJI = tuple(
    (s * 9 + n - 1, s * 9 + n + 2, s * 9 + n, s * 9 + n + 1)
    for s in range(3)
    for n in range(1, 7)
)

# 2 个特征：key -> 显示名（key 命名沿用第一类特征 riichi_others_n 的风格）
FEATURES = [
    ("riichi_others_danger_suji", "立直家（他家）危险筋组数量"),
    ("riichi_others_danger_ryanmen", "立直家（他家）危险两面组数"),
]
NAMES = dict(FEATURES)
KEYS = [k for k, _n in FEATURES]

# 取值域：-1 = 场上没有他家立直；有立直家时 suji 0..18、ryanmen 0..288（18 组 x 4x4）
RANGES = {
    "riichi_others_danger_suji": (-1, len(SUJI)),
    "riichi_others_danger_ryanmen": (-1, len(SUJI) * 16),
}


class DangerLog(object):
    """一局内的「全局出牌序 + 各家立直动作发生的位置」。

    ``seq``      = [(player, kind)] 全局出牌序（含被其他家鸣走的牌；暗杠不是出牌，不在其中）
    ``reach_at`` = {player: 立直宣告时已经发生过的出牌数}（= 该时刻 ``len(seq)``）

    用法：与 ``replay.apply_event`` 同序 ``feed(ev)``，然后每帧调 ``values(state, seat, log)``。
    """

    def __init__(self):
        self.seq = []
        self.reach_at = {}

    def feed(self, ev):
        """按事件顺序喂一个事件（``replay.iter_events`` 的 ``ev``）。"""
        t = ev.get("type")
        if t == "discard":
            self.seq.append((ev["player"], ev["tile"] // 4))
        elif t == "reach" and ev.get("step") == 1:
            self.reach_at[ev["player"]] = len(self.seq)
        return self

    def after_reach(self, player):
        """该家立直动作发生之后（宣告那一刻起）被场上任何一家打出过的牌种集合。"""
        start = self.reach_at.get(player)
        if start is None:
            return set()
        return set(k for _p, k in self.seq[start:])


def round_log(game, round_index, ev_index=None):
    """把该局回放到 ev_index（含；None = 整局），返回 :class:`DangerLog`。"""
    log = DangerLog()
    for i, ev in enumerate(game["rounds"][round_index]["events"]):
        log.feed(ev)
        if ev_index is not None and i >= ev_index:
            break
    return log


def riichi_others(state, seat):
    """场上其他家里的立直家座位（含已宣告、还没走完 step2 的 riichiPending）。"""
    from . import feats     # 延迟导入（feats 模块级 import danger，见文件头说明）
    return [s for s in range(4) if s != seat and feats.is_riichi(state["players"][s])]


def safe_kinds(state, player, log):
    """某个立直家的安全牌种：打出过的所有牌（含被鸣走的）+ 立直动作发生后场上任何一家打出过的牌。"""
    out = set(r["tile"] // 4 for r in state["players"][player]["river"])
    out |= log.after_reach(player)
    return out


def groups_detail(state, seat, log=None):
    """逐筋组明细（测试 / 调试用）。

    返回 [(筋组第一张 kind, 筋组第二张 kind, 両面第一张 kind, 両面第二张 kind,
           safe, blocked, 危险両面的组数)]；``blocked`` = ② 成立（両面能看到 4 张），
    ``safe`` = ② 或 ①。场上没有他家立直时，明细只表示 ② 的结果（调用者先用
    :func:`riichi_others` 判 -1，正常取数走 :func:`values`）。
    """
    riichis = riichi_others(state, seat)
    if riichis and log is None:
        raise ValueError("有他家立直时必须传 DangerLog（安全牌要用全局出牌序）")
    seen = shanten.visible_counts(state, seat)
    safes = dict((x, safe_kinds(state, x, log)) for x in riichis)
    out = []
    for k1, k2, r1, r2 in SUJI:
        blocked = seen[r1] >= 4 or seen[r2] >= 4
        safe = blocked or (bool(riichis) and all(k1 in safes[x] or k2 in safes[x] for x in riichis))
        out.append((k1, k2, r1, r2, safe, blocked,
                    max(0, 4 - seen[r1]) * max(0, 4 - seen[r2])))
    return out


def values(state, seat, log=None):
    """两项危险特征。``log`` = :class:`DangerLog`（有他家立直时必传）。"""
    if not riichi_others(state, seat):
        return dict((k, -1) for k in KEYS)
    n_suji = 0
    n_ryanmen = 0
    for _k1, _k2, _r1, _r2, safe, _blocked, prod in groups_detail(state, seat, log):
        if safe:
            continue
        n_suji += 1
        n_ryanmen += prod
    return {"riichi_others_danger_suji": n_suji,
            "riichi_others_danger_ryanmen": n_ryanmen}


def values_at(game, round_index, ev_index, seat):
    """一次性取数（回放到 ev_index 那一帧为止再算），测试 / 单帧查询用。"""
    st = replay.initial_state(game, round_index)
    log = DangerLog()
    for i, ev in enumerate(game["rounds"][round_index]["events"]):
        replay.apply_event(st, ev)
        st["evIndex"] = i
        log.feed(ev)
        if i >= ev_index:
            break
    return values(st, seat, log)