# -*- coding: utf-8 -*-
"""第一类特征打点。

打点对象（两种帧，一行 = 一个帧，用 kind 列区分）：
    * kind='draw'         非自摸的摸牌帧（摸牌事件帧，且该摸牌没有立刻自摸和了）
    * kind='chi' / 'pon'  吃 / 碰之后「等待出牌」的那一帧（摆出副露牌、还没打出牌）
加杠 / 大明杠 / 暗杠不单独出帧：杠完摸岭上牌、等待出牌的那一帧本身就是 kind='draw' 的摸牌帧。
打点视角：**摸牌者 / 副露者自己**（所以"自家"= 摸牌者，"他家"= 另外三家）

16 个第一类特征：
     1 局况                     東一局..北四局      (init.round)
     2 是否南三局及以后           是/否              (round >= 6，即南三局及之后的延长战)
     3 巡目                     正整数              (该家本局第 N 次出牌，含本次；暗杠/加杠也算一次出牌)
     4 供托                     整百非负整数         (立直棒×1000 + 本场×300)
     5 自家                     亲家/子家
     6 顺位                     1/2/3/4            (按当前分数，同分时按自风 東→南→西→北 排先)
     7 自家立直状态               是/否
     8 自家副露状态               是/否
     9 自家副露数量               0/1/2/3/4
    10 立直家（他家）数量          0/1/2/3
    11 副露家（他家）数量          0/1/2/3
    12 两副露以上（他家）数量       0/1/2/3
    13 三副露以上（他家）数量       0/1/2/3
    14 亲家（他家）立直状态         是/否
    15 亲家（他家）副露状态          是/否
    16 亲家（他家）副露数量         0/1/2/3/4

口径说明（写进 DB 的 meta 与 log.md）：
    * 「副露」= 吃 / 碰 / 加杠 / 大明杠 / 暗杠 的组数，**拔北不计**（四人牌谱里没有拔北）；
      即自摸帧上的副露数量可能含暗杠。牌河里的被鸣牌只算一次。
    * 「亲家（他家）」在摸牌者自己就是亲家时记 否 / 否 / 0（不存在"他家的亲家"）。
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
"""

from . import danger, expect, mjlog, replay, shanten

YES, NO = "是", "否"
DEALER, CHILD = "亲家", "子家"

_BAKAZE = ["東", "南", "西", "北"]

# ------------------------------------------------------------------ 特征注册表
# col: SQLite 列名；kind: enum(枚举) / int(整数)；values: 值域（前端据此渲染下拉选取）
FEATURES = [
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
    {"key": "meld_others_n", "name": "副露家（他家）数量", "col": "f_meld_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "meld2_others_n", "name": "两副露以上（他家）数量", "col": "f_meld2_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "meld3_others_n", "name": "三副露以上（他家）数量", "col": "f_meld3_others_n", "kind": "int", "min": 0, "max": 3},
    {"key": "oya_riichi", "name": "亲家（他家）立直状态", "col": "f_oya_riichi", "kind": "enum", "values": [YES, NO]},
    {"key": "oya_meld", "name": "亲家（他家）副露状态", "col": "f_oya_meld", "kind": "enum", "values": [YES, NO]},
    {"key": "oya_meld_n", "name": "亲家（他家）副露数量", "col": "f_oya_meld_n", "kind": "int", "min": 0, "max": 4},
]

# ------------------------------------------------ 第二类特征（用户 m02959 接入检索）
# 17 个 = 三种向听数 3 + 期望枚数 6 + 期望打点 6（mjscore/expect.py）+ 立直家危险特征 2（mjscore/danger.py）。
# kind = int(整数) / float(实数)：期望特征是实数，检索条件支持小数（见 store.parse_cond）。
# 算法只在 Python 一侧实现（expect 的枚举开销很大，移植到 js 风险过高）：--tool node 时
# node 只算第一类 16 项，这 17 列由 cli.py 的 Python 后处理补齐（见 cli.fill_second_class）。
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

FEATURES = FEATURES + SECOND_FEATURES

BY_KEY = {f["key"]: f for f in FEATURES}

# 打点行里除 16 个特征外的"事实"字段（检索结果条目名 / 定位用，不入特征检索）
FACT_COLS = [
    ("log_id", "TEXT"), ("url", "TEXT"), ("round_index", "INTEGER"), ("frame_index", "INTEGER"),
    ("ev_index", "INTEGER"), ("seat", "INTEGER"), ("round", "INTEGER"), ("honba", "INTEGER"),
    ("kyotaku_raw", "INTEGER"), ("score", "INTEGER"), ("oya", "INTEGER"),
    ("joukyoku", "TEXT"), ("wind", "TEXT"), ("junme", "INTEGER"), ("dealer", "INTEGER"),
    ("rank", "INTEGER"), ("kyotaku_total", "INTEGER"), ("drawn", "INTEGER"),
    ("hand_size", "INTEGER"), ("kind", "TEXT"),   # draw / chi / pon
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


def extract(st, seat):
    """从当前帧状态 st 提取 16 个特征（视角 = seat）。返回 {key: value}。"""
    oya = st["oya"]
    me = st["players"][seat]
    others = [s for s in range(4) if s != seat]
    my_melds = meld_count(me)
    oth_melds = {s: meld_count(st["players"][s]) for s in others}
    oth_riichi = sum(1 for s in others if is_riichi(st["players"][s]))
    rnd = st["round"]
    joukyoku = mjlog.joukyoku_label(rnd)
    rank = calc_rank(st["scores"], oya)[seat]
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
        "riichi_self": YES if is_riichi(me) else NO,
        "meld_self": YES if my_melds > 0 else NO,
        "meld_self_n": my_melds,
        "riichi_others_n": oth_riichi,
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


def make_record(game, round_index, ev_index, st, seat, kind, drawn, log=None):
    """组装一个打点行（16 + 17 特征 + 事实字段）。kind = draw / chi / pon；drawn = 摸到的牌或 None。"""
    me = st["players"][seat]
    vals = extract(st, seat)                    # 第一类 16 项
    vals.update(second_class(st, seat, log))    # 第二类 17 项（m02959）
    rec = {
        "log_id": game.get("log_id") or "",
        "url": mjlog.paipu_url(game.get("log_id") or ""),
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
        "feats": vals,
    }
    return rec


def draw_record(game, round_index, ev_index, st, ev, seat, log=None):
    """非自摸的摸牌帧（kind='draw'）。"""
    return make_record(game, round_index, ev_index, st, seat, "draw", ev["tile"], log)


def call_record(game, round_index, ev_index, st, ev, seat, log=None):
    """吃 / 碰之后「等待出牌」的那一帧（kind = 'chi' / 'pon'）。"""
    return make_record(game, round_index, ev_index, st, seat, ev["callType"], None, log)


def records_for_round(game, round_index, log=None):
    """产出本局所有打点行（非自摸的摸牌帧 + 吃/碰后等待出牌的帧）。

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
    return out


def records_for_game(game):
    out = []
    for ri in range(len(game["rounds"])):
        out.extend(records_for_round(game, ri))
    return out


def feature_values(rec):
    """把打点行压成「16 个特征名 -> 值」的 dict（前端展示用）。"""
    f = rec["feats"]
    return {BY_KEY[k]["name"]: f[k] for k in BY_KEY}