# -*- coding: utf-8 -*-
"""打点特征提取（第零类 + 第一类 + 第二类 + 第三类）。

打点对象（三种帧，一行 = 一个帧，用 kind 列区分）：
    * kind='draw'         非自摸的摸牌帧（摸牌事件帧，且该摸牌没有立刻自摸和了）
    * kind='chi' / 'pon'  吃 / 碰之后「等待出牌」的那一帧（摆出副露牌、还没打出牌）
    * kind='wait'         「鸣牌响应」帧（第三类特征「等待鸣牌」= 是，用户 m07289）：
                          别人打出牌之后、**可能鸣牌（吃 / 碰 / 杠）的那一家各出一行**。
出牌帧（kind='draw' / 'chi' / 'pon'）与鸣牌响应帧（kind='wait'）合起来 = 所有「决策帧」，
于是「决策帧」等价于「可检索静态帧」（用户 m06801 / m07289）。
    关键帧判据 = 「这张牌**可能**被他家鸣牌」，与牌谱里实际有没有出现鸣牌无关（用户 m07289 ①）：
        * 碰 / 大明杠：任何非立直家手牌里同种牌 ≥2 张；
        * 吃：只有下家可能吃，且吃后必须还剩至少一张可打的牌（食替禁止 —— 打出的牌不能与被吃的
          两张牌组成顺子，用户 m07289 ②）；
        * 立直家不能鸣牌（见 responders()）。
立直宣言按「打出立直宣言牌」这一次出牌处理，进入「是否能被他家鸣牌」的流程（用户 m07289 ③）；
立直 / 杠的宣言帧、暗杠 / 加杠帧、自摸和了帧一律不出帧（他家与杠牌唯一的交互是抢杠和牌，
能和就和，构不成决策点）；加杠 / 大明杠 / 暗杠不单独出帧：杠完摸岭上牌、等待出牌的那一帧
本身就是 kind='draw' 的摸牌帧。
打点视角：**当前决策者**（等待出牌的摸牌者 / 刚吃碰的人 / 能鸣牌的响应者）。
「自家」= 当前决策者、「他家」= 另外三家（用户 m06801 / m06832）。

第零类特征 5 项（用户 m04556 ② / m05937 ②；第 60 轮起改为**按帧判定**，用户 m06323 ①、口径按 m06560 更正）：
     值「是 / 否」，判定 = 「这一帧**做决策的那名玩家**带该模型的决策概率表」
     （帧级 dahai_pred / reach / kan 属于这一帧的 actor，huro 只看这名玩家那一格；与牌谱初始的主视角无关）
     A NAGA-平衡 分析             是/否              (naga_types 含「ニシキ」⇒ 是；列 f_ai_balance)
     B NAGA-超副露 分析           是/否              (含「カガシ」；列 f_ai_superhuro)
     C Mortal-4.1-避四 分析       是/否              (含「4.1a」；列 f_ai_mortal41a)
     D Mortal-4.1-平衡 分析       是/否              (含「4.1b」；列 f_ai_mortal41b)
     E Mortal-4.1-争一 分析       是/否              (含「4.1c」；列 f_ai_mortal41c)
   天凤牌谱五项都是「否」，没有该模型概率表的帧也是「否」；
    第零类**不参与**「添加特征词条再填取值」的选取方式，
   检索走四种互斥方案（用户 m04556 ③），见 store.compile_ai()。

第一类特征 17 项：
    1 局况                     東一局..北四局      (init.round)
    2 是否南三局及以后           是/否              (round >= 6，即南三局及之后的延长战)
    3 巡目                     正整数              (该家本局第 N 次出牌，含本次；暗杠/加杠也算一次出牌；
                                                鸣牌响应帧 = 该家下一次出牌会是第几巡，用户 m06832)
    4 供托                     整百非负整数         (立直棒×1000 + 本场×300)
    5 自家                     亲家/子家
    6 顺位                     1/2/3/4            (按当前分数，同分时按自风 東→南→西→北 排先)
    7 自家立直状态               是/否
    8 自家副露状态               是/否
    9 自家副露数量               0/1/2/3/4
   10 立直家（他家）数量          0/1/2/3
   11 立直家（他家）一发巡         是/否              (另外三家的「一发」状态逻辑或，用户 m02227 ②；位置见用户 m02357)
   12 副露家（他家）数量          0/1/2/3
   13 两副露以上（他家）数量       0/1/2/3
   14 三副露以上（他家）数量       0/1/2/3
   15 亲家（他家）立直状态         是/否
   16 亲家（他家）副露状态          是/否
   17 亲家（他家）副露数量         0/1/2/3/4
（原第 1 项「NAGA决策（有/无）」按用户 m04556 ② 改名「NAGA-平衡 分析」并移到第零类；
  原第 7 项「等待鸣牌」按用户 m07289 的补充要求单独编为**第三类特征**）

第三类特征 1 项（用户 m07289：不适合作为普通第一类特征 ⇒ 移出检索页可选的「特征词条」）：
    A 等待鸣牌                   是/否              (这一帧是不是「鸣牌响应」帧，列 f_meld_wait；不进播放界面
                                                「当前帧特征」面板，检索改走必选单选「出牌 / 鸣牌响应」，
                                                见 store.compile_wait())

口径说明（写进 DB 的 meta 与 log.md）：
    * 「副露」= 吃 / 碰 / 加杠 / 大明杠 / 暗杠 的组数，**拔北不计**（四人牌谱里没有拔北）；
      即自摸帧上的副露数量可能含暗杠。牌河里的被鸣牌只算一次。
    * 「亲家（他家）」在决策者自己就是亲家时记 否 / 否 / 0（不存在"他家的亲家"）。
    * 顺位并列时按自风顺序（東南西北）排先，与天凤一致。
    * 供托按"立直棒×1000 + 本场×300"折算，与 readme 定义一致。
     * 第 21 轮起本模块还产出 17 个第二类特征（见下面的 SECOND_FEATURES，m02959）：
       向听数 3（国士無双 / 七対子 / 面子手，-1 = 已和牌、0 = 听牌；
       内部值 3 表示 >=3，对外显示一律写成 >=3）+
       期望枚数 6（副露自摸 / 副露荣和 × 期望枚数 / 绝对枚数，立直/默听共用两项）+
       期望打点 6（副露 / 立直 / 默听 × 荣和 / 自摸）+ 立直家（他家）危险特征 2
       （-1 = 场上没有他家立直）。第二类特征只在本模块（Python）实现，--tool node
       时由 cli.py 后处理补齐；期望特征的算法与口径见 log.md 第 13 / 19 节。
     * 「巡目」按「出牌」计：打牌 +1；暗杠/加杠视为出了一次牌 +1；吃/碰/大明杠不算。
      即巡目 = 该家本局已出牌次数（含暗杠/加杠）+ 1。副露过的人巡目会比"按摸牌次数计"大：
      第 5 巡出牌后吃了一张再出牌，那一手就是第 6 巡（大明杠同理）；
      第 6 巡摸牌后暗杠/加杠再摸岭上牌，就是第 7 巡。
      等待鸣牌帧的巡目 = 该家**下一次出牌**会是第几巡（用户 m06832：巡目指「自家」= 当前决策者的巡目）。
"""

from . import ai_models, danger, expect, mjlog, mortal, naga, replay, shanten

YES, NO = "是", "否"
DEALER, CHILD = "亲家", "子家"

_BAKAZE = ["東", "南", "西", "北"]

# ------------------------------------------------------------------ 特征注册表
# col: SQLite 列名；kind: enum(枚举) / int(整数)；values: 值域（前端据此渲染下拉选取）
# 顺序 = 第零类 5 项（AI_FEATURES，用户 m04556 ② / m05937 ②）→ 第一类 17 项（BASE_FEATURES，
# 第 11 项是「立直家（他家）一发巡」（用户 m02357））→ 第二类 17 项 → 第三类 1 项（THIRD_FEATURES，
# 「等待鸣牌」，用户 m07289）。数据库列顺序 / 界面显示顺序都按最终 FEATURES。
BASE_FEATURES = [
    {"key": "joukyoku", "name": "局况", "col": "f_joukyoku", "kind": "enum",
     "values": ["%s%s局" % (b, k) for b in _BAKAZE for k in mjlog.NUM_KANJI]},
    {"key": "minami3", "name": "是否南三局及以后", "col": "f_minami3", "kind": "enum",
     "values": [YES, NO]},
    {"key": "junme", "name": "巡目", "col": "f_junme", "kind": "int", "min": 1, "max": 30},
    {"key": "kyotaku", "name": "供托", "col": "f_kyotaku", "kind": "int", "min": 0, "max": 30000, "step": 100},
    {"key": "oyako", "name": "自家", "col": "f_oyako", "kind": "enum", "values": [DEALER, CHILD]},
    {"key": "rank", "name": "顺位", "col": "f_rank", "kind": "int", "min": 1, "max": 4},
    {"key": "riichi_self", "name": "自家立直状态", "col": "f_riichi_self", "kind": "enum", "values": [YES, NO]},
    {"key": "meld_self", "name": "自家副露状态", "col": "f_meld_self", "kind": "enum", "values": [YES, NO]},
    {"key": "meld_self_n", "name": "自家副露数量", "col": "f_meld_self_n", "kind": "int", "min": 0, "max": 4},
    {"key": "riichi_others_n", "name": "立直家（他家）数量", "col": "f_riichi_others_n", "kind": "int", "min": 0, "max": 3},
    # 立直家（他家）一发巡（用户 m02227 ②、m02356 改名、m02357 位置）：另外三家的「一发」状态逻辑或
    {"key": "ippatsu", "name": "立直家（他家）一发巡", "col": "f_ippatsu", "kind": "enum", "values": [YES, NO]},
    {"key": "meld_others_n", "name": "副露家（他家）数量", "col": "f_meld_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "meld2_others_n", "name": "两副露以上（他家）数量", "col": "f_meld2_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "meld3_others_n", "name": "三副露以上（他家）数量", "col": "f_meld3_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "oya_riichi", "name": "亲家（他家）立直状态", "col": "f_oya_riichi", "kind": "enum", "values": [YES, NO]},
    {"key": "oya_meld", "name": "亲家（他家）副露状态", "col": "f_oya_meld", "kind": "enum", "values": [YES, NO]},
    {"key": "oya_meld_n", "name": "亲家（他家）副露数量", "col": "f_oya_meld_n", "kind": "int", "min": 0, "max": 4},
]

# ---------------- 第零类特征：牌谱文件里含哪些 AI 模型的分析结果（用户 m04556 ②）
# 天凤牌谱三项都是「否」；NAGA 报告按 naga_types 里的模型判定，规范名见 mjscore/ai_models.py。
# 第零类**不参与**「添加特征词条再给取值」的选取方式：检索用四种互斥方案（用户 m04556 ③），见 store.compile_ai()。
AI_FEATURES = [
    {"key": key, "name": name, "col": col, "kind": "enum", "values": [YES, NO], "model": model}
    for key, name, col, model in ai_models.CHOICES
]
AI_KEYS = [f["key"] for f in AI_FEATURES]

# ------------------------------------------------ 第二类特征（用户 m02959 接入检索）
# 17 个 = 三种向听数 3 + 期望枚数 6 + 期望打点 6（mjscore/expect.py）+ 立直家危险特征 2（mjscore/danger.py）。
# kind = int(整数) / float(实数)：期望特征是实数，检索条件支持小数（见 store.parse_cond）。
# 算法只在 Python 一侧实现（expect 的枚举开销很大，移植到 js 风险过高）：--tool node 时
# node 算第一类 17 项（web/js/mjsfeat.js 与这里同构，用户 m06832；「等待鸣牌」是第三类，用户 m07289）：
# 这 17 列由 cli.fill_second_class 用 Python 补齐；第零类 3 列由 cli.fill_ai 按牌谱来源补（用户 m04556 ②）。
SHANTEN_FEATURES = [
    {"key": "shanten_kokushi", "name": "国士無双向听数", "col": "s_shanten_kokushi",
     "kind": "int", "min": -1, "max": 3},
    {"key": "shanten_chiitoi", "name": "七対子向听数", "col": "s_shanten_chiitoi",
     "kind": "int", "min": -1, "max": 3},
    {"key": "shanten_mentsu", "name": "面子手向听数", "col": "s_shanten_mentsu",
     "kind": "int", "min": -1, "max": 3},
]
# 向听数的三个 key：内部取值 3 表示「>=3 向听」，对外显示一律写成 >=3（用户 m04115②）。
# 界面的取值格式化见 web/js/app.js fmtFeatValue()，命令行见 cli.feat_value_text()。
SHANTEN_KEYS = tuple(f["key"] for f in SHANTEN_FEATURES)

EXPECT_FEATURES = [
    {"key": k, "name": n, "col": "s_" + k, "kind": "float", "min": 0.0, "max": 100000.0}
    for k, n in expect.FEATURES
]

DANGER_FEATURES = [
    {"key": k, "name": n, "col": "s_" + k, "kind": "int",
     "min": danger.RANGES[k][0], "max": danger.RANGES[k][1]}
    for k, n in danger.FEATURES
]

SECOND_FEATURES = SHANTEN_FEATURES + EXPECT_FEATURES + DANGER_FEATURES
SECOND_KEYS = [f["key"] for f in SECOND_FEATURES]

# ------------------------------------------------- 第三类特征（用户 m07289 的补充要求）
# 「等待鸣牌」不再算普通第一类特征：它描述的是**帧的类型**（这一帧是不是「鸣牌响应」帧），
# 既不进播放界面「当前帧特征」面板，也不进检索页「添加特征词条」的下拉；
# 检索改走一个必选的单选「出牌 / 鸣牌响应」（见 store.compile_wait()）。
THIRD_FEATURES = [
    {"key": "meld_wait", "name": "等待鸣牌", "col": "f_meld_wait", "kind": "enum", "values": [YES, NO]},
]
THIRD_KEYS = [f["key"] for f in THIRD_FEATURES]

# 第一类 17 项的最终顺序（用户 m02357：「立直家（他家）一发巡」紧随「立直家（他家）数量」；
# 用户 m04556 ② 把原第 1 项「NAGA决策」移到第零类、用户 m07289 把「等待鸣牌」移到第三类 ⇒ 剩下的就是 BASE_FEATURES）
FIRST_KEYS = [f["key"] for f in BASE_FEATURES]
# 最终注册表 = 第零类 5 项 + 第一类 17 项 + 第二类 17 项 + 第三类 1 项（共 40 项；列顺序 / 界面顺序都按它）
FEATURES = AI_FEATURES + BASE_FEATURES + SECOND_FEATURES + THIRD_FEATURES

BY_KEY = {f["key"]: f for f in FEATURES}

# 打点行里除特征列之外的"事实"字段（检索结果条目名 / 定位用，不入特征检索）
FACT_COLS = [
    ("log_id", "TEXT"), ("url", "TEXT"), ("round_index", "INTEGER"), ("frame_index", "INTEGER"),
    ("ev_index", "INTEGER"), ("seat", "INTEGER"), ("round", "INTEGER"), ("honba", "INTEGER"),
    ("kyotaku_raw", "INTEGER"), ("score", "INTEGER"), ("oya", "INTEGER"),
    ("joukyoku", "TEXT"), ("wind", "TEXT"), ("junme", "INTEGER"), ("dealer", "INTEGER"),
    ("rank", "INTEGER"), ("kyotaku_total", "INTEGER"), ("drawn", "INTEGER"),
    ("hand_size", "INTEGER"), ("kind", "TEXT"),   # draw / chi / pon / wait
    # 第零类的内部辅助列（用户 m04556 ③）：AI 模型规范名 / 系列名的逗号串，供检索按系列聚合
    ("ai_models", "TEXT"), ("ai_series", "TEXT"),
]


def meld_count(player):
    """副露组数（拔北不计入）。"""
    return sum(1 for m in player["melds"] if m["callType"] in replay.OPEN_CALLS or m["callType"] == "ankan")


def is_riichi(player):
    return bool(player["riichi"] or player["riichiPending"])


def calc_rank(scores, oya, seat=None):
    """按分数降序算顺位；同分时按自风顺序（相对起家的座次）排先。返回 [rank0..rank3]。"""
    order = sorted(range(4), key=lambda s: (-scores[s], (s - oya) % 4))
    rank = [0, 0, 0, 0]
    for i, s in enumerate(order):
        rank[s] = i + 1
    return rank


def kyotaku_total(st):
    """供托 = 立直棒×1000 + 本场×300。"""
    return st["kyotaku"] * 1000 + st["honba"] * 300


def _kind_counts(tiles):
    """{kind: 张数}（红 5 与普通 5 同 kind）。"""
    out = {}
    for tid in tiles or []:
        k = mjlog.kind_of(tid)
        if k is None:
            continue
        out[k] = out.get(k, 0) + 1
    return out


def chi_pairs(kind):
    """吃这张牌时另外两张牌可能的 kind（返回 [(a, b)]，a < b）。字牌不能吃。"""
    if kind is None or kind >= 27:
        return []
    num = kind % 9
    out = []
    if num >= 2:
        out.append((kind - 2, kind - 1))
    if 1 <= num <= 7:
        out.append((kind - 1, kind + 1))
    if num <= 6:
        out.append((kind + 1, kind + 2))
    return out


def chi_forbidden(a, b):
    """吃了 a、b 两张之后不能立刻打出的牌（食替禁止，用户 m07289 ②）：
    「能与被吃的两张牌组成顺子」的那些 kind（其中就含被吃进来的那张牌本身）。"""
    lo, hi = (a, b) if a < b else (b, a)
    out = set()
    if hi == lo + 1:
        if lo % 9 >= 1:
            out.add(lo - 1)
        if hi % 9 <= 7:
            out.add(hi + 1)
    elif hi == lo + 2:
        out.add(lo + 1)
    return out


def can_chi(hand, kind):
    """能否吃这张牌：手牌里有两张能凑成顺子，且吃后还剩至少一张可以打出的牌（食替禁止）。"""
    cnt = _kind_counts(hand)
    for a, b in chi_pairs(kind):
        if cnt.get(a, 0) < 1 or cnt.get(b, 0) < 1:
            continue
        rest = dict(cnt)
        rest[a] -= 1
        rest[b] -= 1
        bad = chi_forbidden(a, b)
        for k, n in rest.items():
            if n > 0 and k not in bad:
                return True
    return False


def can_pon(hand, kind):
    """能否碰这张牌（同种 ≥2 张；大明杠要 3 张，但「碰」已经构成可能鸣牌）。"""
    if kind is None:
        return False
    return _kind_counts(hand).get(kind, 0) >= 2


def responders(st, discarder, kind):
    """打出 kind 这张牌之后**可能**鸣牌的所有家（用户 m07289 ①②）。

    判据 = 「可能被他家鸣牌」，与牌谱里实际有没有出现鸣牌无关：
        * 立直家（含刚宣告、还没打出牌的）不能鸣牌；
        * 任何一家手里同种牌 ≥2 张 ⇒ 可能碰 / 大明杠；
        * 只有下家 (discarder + 1) % 4 可能吃，且要过食替禁止（chi_forbidden）。
    返回升序座位号列表（不含出牌者）。
    """
    out = []
    if kind is None or not st or not st.get("players"):
        return out
    for s in range(4):
        if s == discarder:
            continue
        pl = st["players"][s]
        if is_riichi(pl):
            continue
        hand = pl.get("hand") or []
        if can_pon(hand, kind) or (s == (discarder + 1) % 4 and can_chi(hand, kind)):
            out.append(s)
    return out


def meld_possible(st, discarder, kind):
    """这张牌有没有可能被他家鸣牌（用户 m07289 ① 的关键帧判据）。"""
    return bool(responders(st, discarder, kind))


def extract(st, seat, kind=None):
    """从当前帧状态 st 提取第一类 17 项 + 第三类 1 项（视角 = seat = 当前决策者）。返回 {key: value}。

    kind = 这一帧的打点种类（draw / chi / pon / wait，用户 m06832：「等待鸣牌」= 是 当且仅当 kind == 'wait'）。
    由 :func:`ai_values` 在 :func:`make_record` 里补（用户 m04556 ②）。"""
    oya = st["oya"]
    me = st["players"][seat]
    others = [s for s in range(4) if s != seat]
    my_melds = meld_count(me)
    oth_melds = {s: meld_count(st["players"][s]) for s in others}
    oth_riichi = sum(1 for s in others if is_riichi(st["players"][s]))
    rnd = st["round"]
    joukyoku = mjlog.joukyoku_label(rnd)
    rank = calc_rank(st["scores"], oya)[seat]
    ipp = st.get("ippatsu") or [False, False, False, False]
    ipp_others = YES if any(ipp[s] for s in others) else NO   # 立直家（他家）一发巡（用户 m02227 ② / m02356）
    if oya == seat:
        oya_riichi, oya_meld, oya_meld_n = NO, NO, 0
    else:
        p = st["players"][oya]
        oya_meld_n = meld_count(p)
        oya_riichi = YES if is_riichi(p) else NO
        oya_meld = YES if oya_meld_n > 0 else NO
    return {
        "joukyoku": joukyoku,
        "minami3": YES if rnd >= 6 else NO,
        "junme": me["turns"] + 1,   # 巡目 = 该家已出牌次数 + 1（当前这一手）
        "kyotaku": kyotaku_total(st),
        "oyako": DEALER if seat == oya else CHILD,
        "rank": rank,
        "meld_wait": YES if kind == "wait" else NO,   # 第三类「等待鸣牌」（用户 m07289：不进特征词条下拉）
        "riichi_self": YES if is_riichi(me) else NO,
        "meld_self": YES if my_melds > 0 else NO,
        "meld_self_n": my_melds,
        "riichi_others_n": oth_riichi,
        "ippatsu": ipp_others,       # 立直家（他家）一发巡：紧随「立直家（他家）数量」（用户 m02357）
        "meld_others_n": sum(1 for s in others if oth_melds[s] > 0),
        "meld2_others_n": sum(1 for s in others if oth_melds[s] >= 2),
        "meld3_others_n": sum(1 for s in others if oth_melds[s] >= 3),
        "oya_riichi": oya_riichi,
        "oya_meld": oya_meld,
        "oya_meld_n": oya_meld_n,
    }


def second_class(st, seat, log=None):
    """17 个第二类特征的取值（视角 = seat）。返回 {key: value}。

    log 是本局的 danger.DangerLog（危险特征要用全局出牌序）；有他家立直时必须给，
    否则 danger.values 会抛 ValueError。期望特征用 expect 的默认上限（向听 1）。
    """
    sh = shanten.shanten_at(st, seat)          # {'kokushi':…, 'chiitoi':…, 'mentsu':…}
    out = {
        "shanten_kokushi": sh[shanten.KOKUSHI],
        "shanten_chiitoi": sh[shanten.CHIITOI],
        "shanten_mentsu": sh[shanten.MENSU],
    }
    out.update(expect.values(st, seat))
    out.update(danger.values(st, seat, log))
    return out


def row_label(rec):
    """检索结果条目名：牌谱特征码 + 局况 + 本场 + 巡目 + 风位。"""
    return "%s %s %d本場 %d巡目 %s家" % (
        rec["log_id"], rec["joukyoku"], rec["honba"], rec["junme"], rec["wind"])


def _naga_models(game):
    """牌谱里的 AI 模型列表（天凤牌谱 / 没有 models 键的旧结构按 naga_types 现算）。"""
    naga = (game or {}).get("naga") or {}
    models = naga.get("models")
    if models is None:
        models = ai_models.model_list(naga.get("types"))
    return models or []


def ai_values(game):
    """牌谱文件级的第零类特征取值（用户 m04556 ②）：这份牌谱含哪些 AI 模型的分析结果。

    只看「牌谱里有没有这个模型」一个条件，**不区分帧**（打点入库走 ai_frame_values()，
    用户 m06323 ① 起第零类是逐帧判定的）；天凤牌谱没有 models 键 ⇒ 五项全「否」。
    """
    flags = ai_models.value_map(_naga_models(game))
    return dict((k, YES if flags.get(k) else NO) for k in AI_KEYS)


def ai_models_text(game):
    """辅助列 ai_models：AI 模型规范名的逗号串（非空 = 有 AI 分析结果）。"""
    return ", ".join(ai_models.names_of(_naga_models(game)))


def ai_series_text(game):
    """辅助列 ai_series：AI 模型系列名的逗号串（「NAGA决策」/「Mortal决策」按它判定）。"""
    return ", ".join(ai_models.series_of_models(_naga_models(game)))


def viewer_seat(game):
    """牌谱初始的主视角座位（播放时把主视角定到 AI 复盘的那一家）。

    NAGA 报告里没有视角字段（对齐官方 viewer 默认 ``tw=0``）⇒ 0；
    Mortal 报告只复盘一家（``review.player_id``）⇒ mjscore/mortal.py 写进 meta.viewer_seat；
    天凤牌谱没有这个键 ⇒ 0。
    注意：第零类判定**不看**这个座位（用户 m06560 更正后只认「这一帧的决策者」）。
    """
    meta = (game or {}).get("meta") or {}
    seat = meta.get("viewer_seat")
    if isinstance(seat, bool) or not isinstance(seat, int) or seat < 0 or seat > 3:
        return 0
    return seat


def _model_has_data(fr, index, seat=None):
    """这一帧的**决策者**（``seat``）有没有第 index 号模型的决策概率表（用户 m06560 更正口径）。

    帧里的数据都是「每模型一档」：
      * ``dahai_pred``（打哪张）/ ``reach``（立直）/ ``kan``（暗杠・加杠）属于这一帧的 ``actor``
        （= 决策者本人）⇒ 只有 ``seat`` 就是 ``actor`` 时才看它们；
      * ``huro``（每座位 × 每模型：吃・碰・杠・PASS 的选择概率）按座位给 ⇒ 只看 ``seat`` 那一格。
    ``seat`` 为 None 时不做座位过滤（只看这一帧里有没有该模型的数据）。
    """
    if not fr:
        return False

    def _any(v):
        if not v:
            return False
        if isinstance(v, dict):
            return any(x for x in v.values())
        if isinstance(v, (list, tuple)):
            return any(x for x in v)
        return bool(v)

    if seat is None or fr.get("actor") == seat:
        for key in ("dahai_pred", "reach", "kan"):
            arr = fr.get(key)
            if not isinstance(arr, (list, tuple)) or index < 0 or index >= len(arr):
                continue
            if _any(arr[index]):
                return True
    huro = fr.get("huro") or {}
    if isinstance(huro, dict):
        slots = list(huro.values()) if seat is None else [huro.get(str(seat))]
        for arr in slots:
            if not isinstance(arr, (list, tuple)) or index < 0 or index >= len(arr):
                continue
            if _any(arr[index]):
                return True
    return False


def ai_frame_keys(game, round_index, ev_index, seat=None):
    """这一帧的决策者 ``seat`` 有决策概率表的模型 key 列表（用户 m06323 ①，口径见用户 m06560）。

    第零类按帧判定，不再整份牌谱一刀切；``seat`` = 这一帧做决策的玩家（打点行的 seat 列），
    为 None 时不做座位过滤（只看这一帧里有没有该模型的数据）。
    """
    models = _naga_models(game)
    if not models:
        return []
    ai = (game or {}).get("naga") or {}
    rounds = ai.get("rounds") or []
    if not isinstance(round_index, int) or not isinstance(ev_index, int):
        return []
    if round_index < 0 or round_index >= len(rounds):
        return []
    frames = rounds[round_index] or []
    fi = ev_index + 1                    # 帧下标 = 事件序号 + 1（与 store 的 frame_index 一致）
    if fi < 0 or fi >= len(frames):
        return []
    fr = frames[fi] or {}
    keys = []
    for m in models:
        if not _model_has_data(fr, m.get("index", -1), seat):
            continue
        key = ai_models.CHOICE_KEY_BY_MODEL.get(m.get("name"))
        if key and key not in keys:
            keys.append(key)
    return keys


def ai_frame_values(game, round_index, ev_index, seat):
    """一个打点帧的第零类特征（用户 m06323 ①；判定口径按用户 m06560 更正）：(values, 辅助列 ×2)。

    「是」当且仅当**这一帧做决策的那名玩家**（= 打点行的 ``seat`` 列）带该模型的决策概率表
    （``dahai_pred`` / ``reach`` / ``kan`` 属于这一帧的 actor，``huro`` 只看这名玩家那一格）。
    与「牌谱初始的主视角」（``viewer_seat``）无关 —— 第 60 轮首版曾加这道闸门，已按 m06560 删掉。
    天凤牌谱 / 该决策者没有数据的模型 ⇒ 一律「否」，辅助列也只反映这一帧。
    """
    keys = ai_frame_keys(game, round_index, ev_index, seat)
    values = dict((k, YES if k in keys else NO) for k in AI_KEYS)
    names = [ai_models.CHOICE_MODELS[k] for k in keys if k in ai_models.CHOICE_MODELS]
    series = []
    for nm in names:
        s = ai_models.series_of(nm)
        if s and s not in series:
            series.append(s)
    return values, ", ".join(names), ", ".join(series)


def paipu_url_of(game, log_id):
    """打点行的 url 列（用户 m00080 目标 4 / m05937 ③）。

    天凤 = 天凤观战页；NAGA 报告 = 官网观看页；Mortal 报告 = 报告 JSON 地址。
    """
    ai = (game or {}).get("naga") or {}
    if ai.get("kind") == "mortal":
        return mortal.view_url(log_id)
    if ai:
        return naga.view_url(log_id)
    return mjlog.paipu_url(log_id)


def make_record(game, round_index, ev_index, st, seat, kind, drawn, log=None):
    """组装一个打点行（5 + 17 + 17 + 1 特征 + 事实字段）。kind = draw / chi / pon / wait；drawn = 摸到的牌或 None。"""
    me = st["players"][seat]
    vals = extract(st, seat, kind)              # 第一类 17 项 + 第三类「等待鸣牌」（视角 = seat，用户 m07289）
    vals.update(second_class(st, seat, log))    # 第二类 17 项（m02959）
    ai_vals, ai_models_txt, ai_series_txt = ai_frame_values(game, round_index, ev_index, seat)
    vals.update(ai_vals)                        # 第零类 5 项（按帧判定，用户 m06323 ①）
    lid = game.get("log_id") or ""
    rec = {
        "log_id": lid,
        "url": paipu_url_of(game, lid),
        "round_index": round_index,
        "frame_index": ev_index + 1,
        "ev_index": ev_index,
        "seat": seat,
        "round": st["round"],
        "honba": st["honba"],
        "kyotaku_raw": st["kyotaku"],
        "score": me["score"],
        "oya": st["oya"],
        "joukyoku": mjlog.joukyoku_label(st["round"]),
        "wind": replay.seat_wind(seat, st["oya"]),
        "junme": me["turns"] + 1,
        "dealer": 1 if seat == st["oya"] else 0,
        "rank": calc_rank(st["scores"], st["oya"])[seat],
        "kyotaku_total": kyotaku_total(st),
        "drawn": drawn,
        "hand_size": len(me["hand"]),
        "kind": kind,
        "tiles": list(me["hand"]),
        "melds": [[m["callType"], m["tiles"]] for m in me["melds"]],
        "dora": list(st["dora"]),
        "scores": list(st["scores"]),
        "names": [p["name"] for p in st["players"]],
        # 第零类的辅助列（用户 m04556 ③）：AI 模型规范名 / 系列名，供检索按系列聚合；
        # 也按帧判定（用户 m06323 ①），与上面 5 项特征同源
        "ai_models": ai_models_txt,
        "ai_series": ai_series_txt,
        "feats": vals,
    }
    return rec


def draw_record(game, round_index, ev_index, st, ev, seat, log=None):
    """非自摸的摸牌帧（kind='draw'）。"""
    return make_record(game, round_index, ev_index, st, seat, "draw", ev["tile"], log)


def call_record(game, round_index, ev_index, st, ev, seat, log=None):
    """吃 / 碰之后「等待出牌」的那一帧（kind = 'chi' / 'pon'）。"""
    return make_record(game, round_index, ev_index, st, seat, ev["callType"], None, log)


def wait_record(game, round_index, ev_index, st, ev, seat, log=None):
    """「等待鸣牌决策」的一行（kind='wait'，用户 m06801 / m06832）。

    ev = 那张出牌事件；seat = 可能鸣牌（吃 / 碰 / 杠）的一家（用户 m07289 ①②）。
    ev_index 用该出牌事件的下标 ⇒ frame_index = ev_index + 1 = 播放里显示这张出牌的那一帧。
    """
    return make_record(game, round_index, ev_index, st, seat, "wait", None, log)


def records_for_round(game, round_index, log=None):
    """产出本局所有打点行（出牌帧 + 鸣牌响应帧；用户 m06801 / m07289）。

    log = 本局的 danger.DangerLog（危险特征要按全局出牌序算）；不给就现建一个。
    """
    events = game["rounds"][round_index]["events"]
    st = replay.initial_state(game, round_index)
    if log is None:
        log = danger.DangerLog()
    out = []
    for i, ev in enumerate(events):
        replay.apply_event(st, ev)
        log.feed(ev)
        st["evIndex"] = i
        if ev["type"] == "draw":
            nxt = events[i + 1] if i + 1 < len(events) else None
            if (nxt is not None and nxt["type"] == "agari"
                    and nxt["winner"] == ev["player"] and nxt["fromWho"] == ev["player"]):
                continue  # 自摸和了：本轮打点排除
            out.append(draw_record(game, round_index, i, st, ev, ev["player"], log))
        elif ev["type"] == "call" and ev["callType"] in ("chi", "pon"):
            # 摆出副露牌后、等待出牌的那一帧。
            # 暗杠 / 加杠 / 大明杠没有这一帧：它们紧接着摸岭上牌，到那一帧再打点。
            out.append(call_record(game, round_index, i, st, ev, ev["player"], log))
        elif ev["type"] == "discard":
            # 鸣牌响应帧（用户 m07289 ①②）：判据 = 「这张牌**可能**被他家鸣牌」——与牌谱里实际
            # 有没有出现鸣牌无关（碰 = 同种 ≥2 张；吃 = 下家能凑顺子且吃后还剩可打的牌，食替禁止）。
            # 可能鸣牌的每一家各出一行，与播放视图的关键帧判据完全一致。
            kind = mjlog.kind_of(ev["tile"])
            for s in responders(st, ev["player"], kind):
                out.append(wait_record(game, round_index, i, st, ev, s, log))
    return out


def records_for_game(game):
    out = []
    for ri in range(len(game["rounds"])):
        out.extend(records_for_round(game, ri))
    return out


def feature_values(rec):
    """把打点行压成「特征名 -> 值」的 dict（前端展示用）。"""
    f = rec["feats"]
    return {BY_KEY[k]["name"]: f[k] for k in BY_KEY}