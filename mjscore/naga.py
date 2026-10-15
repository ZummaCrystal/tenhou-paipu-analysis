# -*- coding: utf-8 -*-
"""NAGA 牌谱报告（``<report_id>.naga``，旧后缀 ``.json.gz`` / ``.json`` 仍然认）
-> 与 :mod:`mjscore.mjlog` 同构的 game 字典。

NAGA 报告每一帧自带的 ``info.msg`` 就是一条 mjai 消息，本模块把它还原成现有播放
（``mjscore/replay.py`` / ``web/js/replay.js``）与特征链路可以原样消费的结构::

    {"meta": {...}, "rounds": [{"init": {...}, "events": [...]}], "naga": {...}}

``game["naga"]`` 保存与「我们的帧」对齐的 NAGA 独有数据（用户 m00198 的可视化、
目标 3 的 NAGA 特征都用它）。决策概率只取**平衡形 NAGA**（``naga_types`` 里名为
「ニシキ」的那一档，用户 m00418），其余风格（カガシ / 4.1b 等）一律丢弃。

报告的 ``end_msgs`` 里没有流局种类字段（``tenpais`` 也恒为全 true），所以流局种类由
:func:`infer_ryuukyoku_reason` 从事件流推断、听牌家由向听数算（用户 m00653）。

报告的 ``hu`` / ``fan`` 恒为 0、``ten`` 是空数组，所以**和了局的符与点数由我们自己算**
（用户 m02546）：役种直接取报告的 ``yakus_detail``，符走 :mod:`mjscore.agari`，点数取报告
``deltas`` 扣掉「本场 300 / 供托 1000」后的值 —— 与天凤 ``<AGARI ten="n符 n点">`` 同口径，
这样 NAGA 与天凤的结算信息（符 / 点 / 四家配分 / 流局听牌）在界面上完全一致。

:func:`game_from_file` 另外补上 ``game["path"]`` 与 ``game["log_id"]``（= 完整 report_id），
打点链路（mjscore/cli.py）与特征（mjscore/feats.py）据此把 NAGA 报告与天凤牌谱同构处理
（用户 m00080 目标 3）。
"""
from __future__ import annotations

import gzip
import json
import os

from . import ai_models, agari, mjlog, paths, replay, shanten

# 平衡形 naga 的模型名（用户 m00418：只保存这一档决策概率）
BALANCED_MODEL_NAME = "ニシキ"
# 文件名后缀（用户 m05545 ②）：新下载的写 <report_id>.naga，旧的 .json.gz / .json 仍然认
NAGA_SUFFIXES = paths.NAGA_SUFFIXES
# 赤 5 的牌种索引（0m/5m 系：4=5m, 13=5p, 22=5s）
RED_FIVE_KINDS = (4, 13, 22)
HONOR_KIND = {"E": 27, "S": 28, "W": 29, "N": 30, "P": 31, "F": 32, "C": 33}
_BAKAZE_INDEX = {"E": 0, "S": 1, "W": 2, "N": 3}
# NAGA 官方播放页（写进打点行的 url 列；天凤那边用 mjlog.paipu_url，用户 m00080 目标 3）
NAGA_VIEW_URL = "https://naga.dmv.nico/htmls/report_viewer.html?report_id=%s&tw=0"


# ------------------------------------------------------------------ 牌名 / 牌 id
def _name_body(name):
    s = str(name).strip()
    if s.endswith("r") or s.endswith("R"):
        s = s[:-1]
    return s


def tile_kind(name):
    """mjai 牌名 -> 牌种索引 0..33（解析失败返回 None）。赤 5 写作 '5mr'，也接受 '0m'。"""
    s = _name_body(name)
    if not s:
        return None
    up = s.upper()
    if len(s) == 1 and up in HONOR_KIND:
        # 单个字母一律是字牌：S=南 / P=白（不能落进下面 mps 的花色判断）
        return HONOR_KIND[up]
    ch = s[-1].lower()
    if ch in ("m", "p", "s"):
        try:
            rank = int(s[:-1])
        except ValueError:
            return None
        if rank == 0:
            rank = 5
        if 1 <= rank <= 9:
            return "mps".index(ch) * 9 + (rank - 1)
        return None
    return HONOR_KIND.get(s.upper())


def name_is_red(name):
    s = str(name).strip()
    if s.endswith("r") or s.endswith("R"):
        return True
    body = _name_body(s)
    return len(body) >= 2 and body[0] == "0" and body[-1].lower() in ("m", "p", "s")


def _is_red_tid(tid):
    k = tid >> 2
    return k < 27 and (k % 9) == 4 and (tid & 3) == 0


class _Table(object):
    """一局内的牌 id 分配 + 四家手牌/牌河追踪。

    与 mjlog 一致：牌 id 0..135、``kind = tid >> 2``、赤 5 = ``kind % 9 == 4 and tid & 3 == 0``。
    逐事件从「手牌里真取」是保证 ``replay.check_invariants`` 零错误的关键。
    """

    def __init__(self):
        self.pool = dict((k, [4 * k + i for i in range(4)]) for k in range(34))
        self.hands = [[], [], [], []]
        self.rivers = [[], [], [], []]

    def _take_pool(self, kind, red):
        pool = self.pool.get(kind) or []
        if not pool:
            return None
        if kind in RED_FIVE_KINDS:
            if red:
                for i, t in enumerate(pool):
                    if t == 4 * kind:
                        return pool.pop(i)
            for i, t in enumerate(pool):
                if not _is_red_tid(t):
                    return pool.pop(i)
            return pool.pop(0)
        return pool.pop(0)

    def draw(self, name):
        kind = tile_kind(name)
        if kind is None:
            return None
        return self._take_pool(kind, name_is_red(name))

    def take_hand(self, seat, name):
        kind = tile_kind(name)
        if kind is None:
            return None
        hand = self.hands[seat]
        red = name_is_red(name)
        best = None
        for i, t in enumerate(hand):
            if (t >> 2) != kind:
                continue
            if _is_red_tid(t) == red:
                best = i
                break
            if best is None:
                best = i
        if best is None:
            return None
        return hand.pop(best)


# ------------------------------------------------------------------ 报告读取
def is_naga_file(path):
    """按文件名判断是不是 NAGA 报告（``.naga`` 或旧后缀 ``.json.gz`` / ``.json``）。"""
    return os.path.basename(str(path)).lower().endswith(NAGA_SUFFIXES)


def load_report(source):
    """source: 文件路径 / bytes / 已解析的 dict -> 报告 dict（gzip 自动解压）。"""
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, bytes, os.PathLike)) and not isinstance(source, bytes):
        if isinstance(source, os.PathLike) or (isinstance(source, str) and os.path.exists(source)):
            with open(source, "rb") as fh:
                data = fh.read()
        elif isinstance(source, str):
            data = source.encode("utf-8")
        else:
            data = bytes(source)
    else:
        data = bytes(source)
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise ValueError("NAGA 报告解压失败：%s" % exc)
    try:
        report = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("NAGA 报告不是合法的 JSON：%s" % exc)
    if not isinstance(report, dict) or "pred" not in report:
        raise ValueError("内容不像 NAGA 报告（缺少 pred 字段）")
    return report


def balanced_model_index(report):
    """``naga_types`` 里值为「ニシキ」的模型下标；找不到时退回 0（用户 m00418）。"""
    types = report.get("naga_types") or {}
    for key, name in types.items():
        if str(name) == BALANCED_MODEL_NAME:
            try:
                return int(key)
            except (TypeError, ValueError):
                pass
    return 0


# ------------------------------------------------------------------ 每模型：保留全部模型
def _model_values(seq, models):
    """``[每模型 ...]`` -> 与 ``models`` 同序的值列表（用户 m04556 ①）。

    * ``seq`` 为 None / 空列表 -> None；
    * ``seq`` 是 dict、或列表首个元素不是 list/tuple/dict（旧版单模型报告的扁平值）
      -> 长度等于模型数的扁平标量列表按「每模型一个值」返回（如 ``reach``），
         否则把同一个值复制给所有模型；
    * 否则 ``seq`` 就是「每模型」外层：按 ``m["index"]`` 取（越界给 None）。
    """
    if seq is None:
        return None
    if isinstance(seq, dict):
        return [dict(seq) for _ in (models or [None])]
    if not isinstance(seq, (list, tuple)) or not seq:
        return None
    if isinstance(seq[0], (list, tuple, dict)):
        values = []
        for m in (models or [{"index": 0}]):
            try:
                idx = int((m or {}).get("index", 0))
            except (TypeError, ValueError, AttributeError):
                idx = 0
            values.append(seq[idx] if 0 <= idx < len(seq) else None)
        return values
    # 扁平标量列表且长度 == 模型数 ⇒ 就是「每模型一个值」（如 reach = [9291, 888, 9291]：
    # 前端 aiPick 的 ``v.length === models.length`` 分支正是为它准备的）；否则按单模型值复制。
    if len(seq) == len(models or [None]) and not any(isinstance(v, (list, tuple, dict)) for v in seq):
        return list(seq)
    flat = list(seq)
    return [flat for _ in (models or [None])]


def _model_indexed(seq, models):
    """``[每模型 ...]``（元素允许是 None / dict）-> 与 ``models`` 同序的列表。

    与 :func:`_model_values` 的区别：首位元素是 None 时也按「每模型」处理 —— 新版 NAGA 的
    ``ankan_pai`` / ``kakan_pai`` 形如 ``[null, {"F": 9944}, {"F": 9984}]``（模型 0 恒为 None），
    按 ``m["index"]`` 取；不是列表时退回 :func:`_model_values`。
    """
    if not isinstance(seq, (list, tuple)):
        return _model_values(seq, models)
    if not seq:
        return None
    out = []
    for i, m in enumerate(models or [{"index": 0}]):
        try:
            idx = int((m or {}).get("index", i))
        except (TypeError, ValueError, AttributeError):
            idx = i
        out.append(seq[idx] if 0 <= idx < len(seq) else None)
    return out


# 新版 NAGA（アナンタ / ウロボロス，用户 m09507）的打牌分布是 37 槽：
# 0..33 = 34 种，34 / 35 / 36 = 赤 5m / 赤 5p / 赤 5s（3,563 帧的 argmax 与报告自带的
# info.msg.pred_dahai 交叉验证：合并后一致率 99.8%）。
_DAHAI_TAIL = {34: 4, 35: 13, 36: 22}


def _collapse_dahai(*arrs):
    """37 槽（含赤 5）-> 34 槽（赤 5 并入普通 5，与 dahai_pred 的 34 槽口径一致）。

    可一次传多个 37 槽数组：官方 viewer 的 ``gt()`` 会先把两支逐槽相加再折叠
    （``gt(a[0].map((t, e) => t + a[1][e]))``）。
    """
    out = [0] * 34
    for arr in arrs:
        for i, v in enumerate(arr or []):
            k = _DAHAI_TAIL.get(i, i)
            if not (0 <= k <= 33) or not isinstance(v, (int, float)):
                continue
            out[k] += v
    return out


def _model_map(obj, models):
    """``{"座位": [每模型 ...]}`` -> ``{"座位": [每模型值 ...]}``（丢掉完全空的座位）。"""
    out = {}
    for key, seq in (obj or {}).items():
        vals = _model_values(seq, models)
        if vals is not None:
            out[str(key)] = vals
    return out


# ------------------------------------------------------------------ 帧 -> 事件
def _round_lists(pred):
    """``pred`` 是「每局一个帧列表」的二维结构（viewer 也按 pred[局][帧] 取）；
    兼容「扁平帧列表」的旧形态（按 start_kyoku 现切）。"""
    if not pred:
        return []
    if isinstance(pred[0], (list, tuple)):
        return [list(x) for x in pred]
    return _group_frames(pred)


def _group_frames(pred):
    """按 start_kyoku 切成一局一局的帧列表。"""
    groups = []
    cur = None
    for fr in pred:
        info = (fr or {}).get("info") or {}
        msg = info.get("msg") or {}
        if cur is None or msg.get("type") == "start_kyoku":
            cur = []
            groups.append(cur)
        cur.append(fr)
    return groups


def _side_ids(names, table):
    out = []
    for nm in names or []:
        tid = table.draw(nm)
        if tid is not None:
            out.append(tid)
    return out


def _convert_round(frames, models, ri):
    start = ((frames[0].get("info") or {}).get("msg")) or {}
    table = _Table()
    for seat, names in enumerate(start.get("tehais") or []):
        for tid in _side_ids(names, table):
            table.hands[seat].append(tid)

    bakaze = str(start.get("bakaze") or "E").upper()
    kyoku = int(start.get("kyoku") or 1)
    round_index = _BAKAZE_INDEX.get(bakaze, 0) * 4 + (kyoku - 1)
    init = {
        "round": round_index,
        "combo": int(start.get("honba") or 0),
        "kyotaku": int(start.get("kyotaku") or 0),
        "dices": [0, 0],
        "dora": table.draw(start.get("dora_marker")),
        "scores": [int(x) for x in (start.get("scores") or [0, 0, 0, 0])],
        "oya": int(start.get("oya") or 0),
        "hands": [list(h) for h in table.hands],
    }

    msgs = [((fr.get("info") or {}).get("msg") or {}) for fr in frames[1:]]
    events = []
    for msg in msgs:
        ev = _event(msg, table)
        if ev is not None:
            events.append(ev)
    try:
        state = _replay_state(init, events)
    except Exception:                                  # noqa: BLE001 - 判不出来就不摊牌
        state = None
    # 一炮双响时会有两条和了（用户 m02984 ①）：逐条追加，第二家不再被丢掉
    events.extend(_end_events(start.get("end_msgs"), table, msgs, state))

    naga_frames = [_frame(fr, models) for fr in frames]
    return init, events, naga_frames


def _event(msg, table):
    t = msg.get("type")
    actor = msg.get("actor")
    if t == "tsumo":
        tid = table.draw(msg.get("pai"))
        if tid is None:
            return None
        table.hands[actor].append(tid)
        return {"type": "draw", "player": actor, "tile": tid}
    if t == "dahai":
        tid = table.take_hand(actor, msg.get("pai"))
        if tid is None:
            tid = table.draw(msg.get("pai"))
        if tid is None:
            return None
        table.rivers[actor].append(tid)
        return {"type": "discard", "player": actor, "tile": tid}
    if t in ("chi", "pon", "daiminkan", "kakan", "ankan"):
        if t == "ankan":
            tiles = []
            for nm in msg.get("consumed") or []:
                tid = table.take_hand(actor, nm)
                if tid is None:
                    tid = table.draw(nm)
                if tid is not None:
                    tiles.append(tid)
            return {"type": "call", "player": actor, "callee": None, "rel": 0,
                    "m": None, "callType": "ankan", "tiles": tiles}
        if t == "kakan":
            # tiles[0] = 加进去的那张（replay/ui 都这么约定）；后面那 3 张**不在这里凑**，
            # 由 replay.apply_call 从已有的碰补齐 —— 加杠时另外 3 张早已被「碰」用掉，
            # 牌山池里取不到（用户 m08125 ①：加杠后 4 张全部消失的根因）。
            added = table.take_hand(actor, msg.get("pai"))
            if added is None:
                added = table.draw(msg.get("pai"))
            return {"type": "call", "player": actor, "callee": None, "rel": 0,
                    "m": None, "callType": "kakan",
                    "tiles": [added] if added is not None else []}
        target = msg.get("target")
        river = table.rivers[target] if target is not None else []
        called = river[-1] if river else table.draw(msg.get("pai"))
        if called is None:
            called = table.draw(msg.get("pai"))
        tiles = [called] if called is not None else []
        for nm in msg.get("consumed") or []:
            tid = table.take_hand(actor, nm)
            if tid is None:
                tid = table.draw(nm)
            if tid is not None:
                tiles.append(tid)
        if t == "chi" and len(tiles) > 1:
            tiles = [tiles[0]] + sorted(tiles[1:])
        rel = 0 if target is None else (int(target) - int(actor)) % 4
        return {"type": "call", "player": actor, "callee": target, "rel": rel,
                "m": None, "callType": t, "tiles": tiles}
    if t == "reach":
        return {"type": "reach", "player": actor, "step": 1}
    if t == "reach_accepted":
        ev = {"type": "reach", "player": actor, "step": 2}
        if msg.get("scores"):
            ev["scores"] = [int(x) for x in msg["scores"]]
        return ev
    if t == "dora":
        tid = table.draw(msg.get("dora_marker"))
        if tid is None:
            return None
        return {"type": "dora", "tile": tid}
    return None


# ------------------------------------------------------- 流局种类推断（用户 m00653）
def _is_yao_kind(kind):
    """么九牌：1/9 数牌 + 字牌（27..33）。"""
    return kind >= 27 or (kind % 9) in (0, 8)


def _count_yao_kinds(tids):
    """给定牌 id 列表里么九牌的**种类**数（九种九牌判定用）。"""
    return sum(1 for k in set(int(t) >> 2 for t in tids) if _is_yao_kind(k))


def _called_seats(msgs):
    """被鸣牌的座位（吃/碰/大明杠的 target）：流局满贯要求自己的弃牌一张都没被鸣走。"""
    out = set()
    for m in msgs:
        if m.get("type") in ("chi", "pon", "daiminkan"):
            target = m.get("target")
            if target is not None:
                out.add(int(target))
    return out


def infer_ryuukyoku_reason(msgs, end_msgs=None, table=None):
    """从事件流推断流局种类，返回 :data:`mjscore.mjlog.REASON_NAME` 的键。

    判定顺序按用户 m00653：「先检查途中流局（九种九牌 / 四风连打 / 四杠散了 / 四家立直 /
    三家和了），都不是再看流局满贯，都没有才算荒牌流局」⇒ 荒牌流局返回 ``""``。

    ``msgs`` = 本局逐帧的 mjai 消息（不含 start_kyoku）、``end_msgs`` = 报告局末消息、
    ``table`` = 本局的 :class:`_Table`（九种九牌与流局满贯要看牌）。
    """
    msgs = list(msgs or [])
    ends = list(end_msgs or [])
    calls = [m for m in msgs if m.get("type") in ("chi", "pon", "daiminkan", "kakan", "ankan")]
    dahai = [m for m in msgs if m.get("type") == "dahai"]
    tsumo = [m for m in msgs if m.get("type") == "tsumo"]
    reach = [m for m in msgs if m.get("type") in ("reach", "reach_accepted")]
    hora = [x for x in ends if isinstance(x, dict) and x.get("type") == "hora"]
    if len(hora) >= 3:                                  # 三家和了
        return "tripleRon"
    if sum(1 for m in msgs if m.get("type") == "reach_accepted") >= 4:   # 四家立直
        return "reach4"
    if not calls:
        if len(dahai) == 4 and len(tsumo) == 4 and not reach:
            names = [str(m.get("pai") or "") for m in dahai]           # 四风连打
            actors = sorted(str(m.get("actor")) for m in dahai)
            drew = sorted(str(m.get("actor")) for m in tsumo)
            if (names[0] == names[1] == names[2] == names[3]
                    and HONOR_KIND.get(names[0]) in (27, 28, 29, 30)
                    and len(set(actors)) == 4 and actors == drew):
                return "kaze4"
        if tsumo and not reach and table is not None:   # 九种九牌：第一巡么九牌 >= 9 种
            actor = tsumo[-1].get("actor")
            if actor is not None and not any(m.get("actor") == actor for m in dahai):
                if _count_yao_kinds(table.hands[actor]) >= 9:
                    return "yao9"
    else:
        kans = [m for m in calls if m.get("type") in ("ankan", "kakan", "daiminkan")]
        if len(kans) >= 4 and len(set(m.get("actor") for m in kans)) >= 2:   # 四杠散了
            return "rck4"
    if table is not None:                               # 流局满贯：牌河全是么九且没被鸣走
        called = _called_seats(msgs)
        for seat in range(4):
            river = table.rivers[seat]
            if river and seat not in called and all(_is_yao_kind(t >> 2) for t in river):
                return "nm"
    return ""


def _replay_state(init, events):
    """用 :mod:`mjscore.replay` 把本局走一遍，拿末状态（听牌判定要副露与场上可见牌）。"""
    game = {"meta": {"names": []}, "rounds": [{"init": init, "events": list(events)}]}
    st = replay.initial_state(game, 0)
    for ev in events:
        replay.apply_event(st, ev)
    return st


def _tenpai_seats(state):
    """按向听数算听牌家（报告的 ``tenpais`` 恒为全 true、不可信；用户 m00653）。"""
    if state is None:
        return []
    out = []
    for seat in range(4):
        try:
            if shanten.min_shanten(shanten.shanten_at(state, seat)) <= 0:
                out.append(seat)
        except Exception:                               # noqa: BLE001 - 判不出来就不摊牌
            continue
    return out


def _hora_ctx(state, msgs, end, actor, target, yaku_hint=()):
    """和了局的场况旗标（自摸 / 荣和的差别由 ``target == actor`` 决定）。

    * 旗标先从消息序列推：岭上 / 抢杠要往前找「上一次杠」，而**杠与岭上摸牌之间可能夹着
      一条新宝牌消息**（`杠 → dora → 摸岭上牌 → 和了`），所以要跳过它
      （否则会像 `data/paipu/20261007-165558/2026090821gm-00a9-0000-7019128e.xml` 第 1 局那样漏算嶺上開花）。
    * 报告的役种是权威：一発 / 槍槓 / 嶺上開花 / 海底摸月 / 河底撈魚 出现在 ``yaku_hint``
      里时直接置真 —— 与 ``test/agari_test.py`` 第 5 节校验天凤 640 局用的口径相同（用户 m02801 ②）。
    """
    tsumo = (int(target) == int(actor))
    msgs = msgs or []
    hs = set(int(y) for y in (yaku_hint or ()))
    kan_types = ("ankan", "kakan", "daiminkan")

    def before(i):
        """第 i 帧之前的上一帧（跳过夹在中间的新宝牌消息）。"""
        j = i - 1
        while j >= 0 and msgs[j].get("type") == "dora":
            j -= 1
        return msgs[j] if j >= 0 else None

    prev = before(len(msgs)) if msgs else None
    prev2 = before(len(msgs) - 1) if len(msgs) >= 2 else None
    ippatsu = state.get("ippatsu") or [False, False, False, False]
    return {
        "ippatsu": bool(ippatsu[int(actor)]) or (2 in hs),
        # 岭上：和牌前一帧（摸牌）之前是自己的一次杠（暗杠 / 加杠 / 大明杠）
        "rinshan": bool(tsumo and prev2 is not None and prev2.get("type") in kan_types
                        and prev2.get("actor") == int(actor)) or (4 in hs),
        "haitei": bool(tsumo and state.get("tilesLeft") == 0) or (5 in hs),
        "houtei": bool((not tsumo) and state.get("tilesLeft") == 0) or (6 in hs),
        # 抢杠：荣和的上一帧是放铳家的加杠
        "chankan": bool((not tsumo) and prev is not None and prev.get("type") == "kakan"
                        and prev.get("actor") == int(target)) or (3 in hs),
        "dora": tuple(state.get("dora") or ()),
        "ura": tuple(int(x) for x in (end.get("uradora_markers") or [])),
    }


def _hora_settle(state, msgs, end, actor, target, win, deltas, riichi_hint=0, hu_report=0,
                 yaku_hint=(), honba=None, kyotaku=None):
    """算这一局和牌的符 / 点，返回 ``(符, 点数, agari.score 的结果或 None)``（用户 m02546）。

    * **符**：用 :mod:`mjscore.agari` 从「末状态的手牌 / 副露 + 和了张 + 场况旗标」算。
      用 71 个天凤牌谱 640 个和了局实测，本引擎的 ``fu`` 与天凤 ``<AGARI ten="n符 …">``
      **逐局完全一致**（口径与 ``test/agari_test.py`` 第 5 节相同：场况旗标由谱面役种提示）。
    * **点**：报告自带 ``deltas``（最终收支配分），和牌家的增减扣掉「本场 300 / 供托 1000」
      就是天凤 ``ten`` 里的点数（637 个单和了局 637/637；3 局ダブロン的本场 / 供托只归先和者）。
    * ``yaku_hint``：报告给的役种 id 列表，用来提示场况旗标（用户 m02801 ②）。
    * ``honba`` / ``kyotaku``：显式覆盖本场 / 供托，``None`` 时取报告 ``ba`` 的前两项。
      一炮双响（ダブロン）时只有**先和的那一家**拿本场 / 供托（用户 m02984 ①）。
    """
    ba = [int(x) for x in (end.get("ba") or [])]
    if honba is None:
        honba = ba[0] if ba else 0
    if kyotaku is None:
        kyotaku = ba[1] if len(ba) > 1 else 0

    def _pts(gain=None):
        """和牌家收到的点数（扣掉本场 300 / 供托 1000，与天凤 ``ten`` 同口径）。"""
        seat = int(actor)
        v = int(deltas[seat]) if deltas and len(deltas) > seat else 0
        if v <= 0 and gain is not None:
            v = int(gain)
        if v <= 0:
            return 0
        return v - honba * 300 - kyotaku * 1000

    if state is None or win is None:
        return int(hu_report or 0), _pts(), None
    try:
        pl = state["players"][int(actor)]
    except (KeyError, IndexError, TypeError):
        return int(hu_report or 0), _pts(), None
    tsumo = (int(target) == int(actor))
    hand = list(pl["hand"])
    drawn = state.get("drawn")
    if tsumo and drawn and drawn.get("player") == int(actor) and win in hand:
        hand.remove(win)
    # 报告的役种里有立直 / 一発时按立直算：报告偶尔漏发立直消息，但和了役种是权威（用户 m02546）
    riichi = 1 if (pl["riichi"] or riichi_hint) else 0
    res = None
    try:
        res = agari.score(
            hand, pl["melds"], win_tile=win, tsumo=tsumo,
            oya=(int(actor) == state["oya"]), honba=honba, kyotaku=kyotaku,
            seat_wind=27 + (int(actor) - state["oya"]) % 4,
            round_wind=27 + int(state["round"]) // 4,
            riichi=riichi,
            ctx=_hora_ctx(state, msgs, end, actor, target, yaku_hint),
        )
    except Exception:                                  # noqa: BLE001 - 算不出来就用报告给的符
        res = None
    fu = int(res["fu"]) if res is not None else int(hu_report or 0)
    return fu, _pts(res["gain"] if res is not None else None), res


def _end_event(end_msgs, table, msgs=None, state=None, pick=0, first=True):
    """一条结束事件：``pick`` 指定用 ``end_msgs`` 里的第几条（一炮双响时每家和一条）。

    ``first`` 为假时不给本场 / 供托（只有先和的那一家拿，用户 m02984 ①）。
    """
    if not end_msgs:
        return None
    if isinstance(end_msgs, (list, tuple)):
        if pick >= len(end_msgs):
            return None
        e = end_msgs[pick]
    else:
        e = end_msgs if pick == 0 else None
    if not isinstance(e, dict):
        return None
    deltas = [int(x) for x in (e.get("deltas") or [0, 0, 0, 0])]
    scores = [int(x) for x in (e.get("scores") or [0, 0, 0, 0])]
    before = [scores[i] - deltas[i] for i in range(4)]
    t = e.get("type")
    if t == "hora":
        actor = int(e.get("actor") or 0)
        # 注意：target 可能真的是 0（放铳家坐在 0 号位），不能用 ``or`` 兜底（用户 m02546 排查）
        _tgt = e.get("target")
        target = actor if _tgt is None else int(_tgt)
        hand = list(table.hands[actor])
        if target != actor:
            riv = table.rivers[target]
            win = riv[-1] if riv else table.draw(e.get("pai"))
            if win is not None:
                hand = hand + [win]
        else:
            win = hand[-1] if hand else table.draw(e.get("pai"))
        # 报告可能给「役种 + 番数」（yakus_detail），也可能只给役种 id（yakus），甚至什么都不给
        # （例如 60b5c2ad 那份报告里 12 个和了局全空）。只给 id 时**不假设每项 1 番**，
        # 一律用引擎判出的役种 + 番数（用户 m02801 ②）。
        detail = [[int(p[0]), int(p[1])] for p in (e.get("yakus_detail") or [])]
        ids = [int(y) for y in (e.get("yakus") or [])]
        ura = [int(x) for x in (e.get("uradora_markers") or []) if isinstance(x, int)]
        # 结算（用户 m02546）：符 / 点由我们算；役种优先用报告的，报告没给就用我们引擎判的
        ten = []
        yakuman = []
        raw_yakuman = e.get("yakuman")
        if isinstance(raw_yakuman, (list, tuple)):
            yakuman = [int(y) for y in raw_yakuman]
        _hint_ids = [p[0] for p in detail] or ids
        _hint = 1 if any(i in (1, 2, 21) for i in _hint_ids) else 0   # 立直 / 一発 / 両立直
        fu, pts, res = _hora_settle(state, msgs, e, actor, target, win, deltas,
                                    riichi_hint=_hint, hu_report=int(e.get("hu") or 0),
                                    yaku_hint=_hint_ids,
                                    honba=None if first else 0, kyotaku=None if first else 0)
        if fu > 0 and pts > 0:
            ten = [int(fu), int(pts)]
        yaku = list(detail)
        if res is not None and not yakuman and res.get("yakuman"):
            # 役満：役種用我们引擎判出来的（报告此时通常不给役种），符为 0
            yakuman = [int(y[0]) for y in res["yaku"] if y[1] == 0]
            if yakuman:
                yaku = []
        elif not yaku:
            # 报告没给「役种 + 番数」：用引擎判的（宝牌 / 里宝牌的张数也一并算准）
            if res is not None:
                yaku = [[int(y[0]), int(y[1])] for y in res["yaku"] if y[1] > 0]
            if not yaku and ids:
                # 引擎也判不出：只显示役种名，不猜番数
                yaku = [[i, 0] for i in ids]
        return {
            "type": "agari", "winner": actor, "fromWho": target,
            "hand": hand, "machi": [] if win is None else [win],
            "dora": _side_ids(e.get("dora_markers"), table),
            "ura": ura, "yaku": yaku, "yakuman": yakuman, "ten": ten,
            "ba": [int(x) for x in (e.get("ba") or [])],
            "before": before, "gain": deltas,
        }
    if t == "ryukyoku":
        ends = list(end_msgs) if isinstance(end_msgs, (list, tuple)) else [end_msgs]
        reason = infer_ryuukyoku_reason(msgs, ends, table)
        if not reason:
            # 事件流推不出来时，才退回报告里可能存在的种类字段
            for cand in ends:
                if isinstance(cand, dict) and str(cand.get("reason") or "") in mjlog.REASON_NAME:
                    reason = str(cand["reason"])
                    break
        # 途中流局 / 流局满贯都不给 hands；荒牌流局只给听牌家（replay 用它出摊牌名单）
        tenpai = [] if reason else _tenpai_seats(state)
        hands = [list(table.hands[i]) if i in tenpai else None for i in range(4)]
        who = None
        if reason == "yao9":
            decl = [m.get("actor") for m in (msgs or []) if m.get("type") == "tsumo"]
            who = decl[-1] if decl else None
        elif reason == "tripleRon":
            hora = [x for x in ends if isinstance(x, dict) and x.get("type") == "hora"]
            if hora:
                who = hora[0].get("target")
                if who is None:
                    who = hora[0].get("actor")
        return {"type": "ryuukyoku", "reason": reason, "who": who, "hands": hands,
                "ba": [int(x) for x in (e.get("ba") or [])],
                "before": before, "gain": deltas}
    return None


def _end_events(end_msgs, table, msgs=None, state=None):
    """一局的全部结束事件（一炮双响时每家和牌各一条，用户 m02984 ①）。

    报告 ``end_msgs`` 里出现两条 ``hora`` 时，以前只取 ``[0]`` ⇒ 第二家会被丢掉。
    本场 / 供托只归先和的那一家，第二家按 0 计（与天凤 ``<AGARI ten>`` 口径一致）。
    """
    if not end_msgs:
        return []
    total = len(end_msgs) if isinstance(end_msgs, (list, tuple)) else 1
    out = []
    first = True
    for i in range(total):
        ev = _end_event(end_msgs, table, msgs, state, pick=i, first=first)
        if ev is None:
            continue
        out.append(ev)
        if ev.get("type") == "agari":
            first = False
    return out


_FRAME_KEEP = ("tenpai_s", "tenpai_t", "tenpai_k", "danger_s", "danger_t", "danger_k",
               "end_type", "game_rank", "kyoku_rank", "rank_diff", "end_num")


def _frame(fr, models):
    info = (fr.get("info") or {})
    msg = info.get("msg") or {}
    out = {
        "msg": msg.get("type"),
        "actor": msg.get("actor"),
        "target": msg.get("target"),
        "pai": msg.get("pai"),
        "consumed": list(msg.get("consumed") or []),
        "kind": msg.get("kind"),
        "tsumogiri": bool(msg.get("tsumogiri")),
        "real_dahai": msg.get("real_dahai"),
        "pred_dahai": list(msg.get("pred_dahai") or []),
        "next_tsumogiri": bool(msg.get("next_tsumogiri")),
        "dora_marker": msg.get("dora_marker"),
        "scores": list(msg.get("scores") or []),
        "deltas": list(msg.get("deltas") or []),
    }
    # 以下四项在报告里有「模型」维（用户 m04556 ①）：统一保留成与 models 同序的列表，
    # 前端按所选 AI 模型的下标取用；缺该模型的值就是 None。
    dahai = _model_values(fr.get("dahai_pred"), models)
    if dahai is not None:
        out["dahai_pred"] = [(list(v) if isinstance(v, (list, tuple)) else []) for v in dahai]
    # 新版 NAGA 的 dahai_detail 放到 reach 之后再处理（见下面 detail 段），
    # 免得合并出来的取值被报告自带的 reach / dahai_pred 覆盖。
    huro = _model_map(fr.get("huro"), models)
    if huro:
        out["huro"] = huro
    reach = _model_values(fr.get("reach"), models)
    if reach is not None:
        out["reach"] = reach
    # 新版 NAGA（用户 m09507：アナンタ / ウロボロス）不给可用的 dahai_pred，而是给
    # dahai_detail = [每模型 [ダマ时的打牌联合分布(37 槽), 立直时的打牌联合分布(37 槽)]]。
    # 口径与官方 viewer（/static/naga_report/1.2.2/js/index.js 的 mt() / gt()）一致：
    #   dahaiPred[m] = gt(detail[m][0] + detail[m][1])   —— 两支逐槽相加后的边际打牌分布
    #   reach[m]     = sum(gt(detail[m][1]))             —— 立直那一支的概率总和；
    #                   只在该帧报告本来就标了「立直决策」（reach 列表存在）时补 None 的格子
    # 原有模型（ニシキ 等）detail[di] 为 null ⇒ 一字不动（用户 m09507 的零变化前提）。
    detail = fr.get("dahai_detail")
    if isinstance(detail, (list, tuple)):
        pred_list = out.get("dahai_pred")
        if not isinstance(pred_list, list):
            pred_list = out["dahai_pred"] = [[] for _ in (models or [None])]
        reach_list = out.get("reach")
        split_list = [None] * len(models or [{"index": 0}])
        for mi, m in enumerate(models or [{"index": 0}]):
            try:
                di = int((m or {}).get("index", mi))
            except (TypeError, ValueError, AttributeError):
                di = mi
            dv = detail[di] if 0 <= di < len(detail) else None
            if not (isinstance(dv, (list, tuple)) and dv and isinstance(dv[0], (list, tuple))):
                continue
            riichi = dv[1] if len(dv) > 1 and isinstance(dv[1], (list, tuple)) else None
            merged = _collapse_dahai(dv[0], riichi)
            if any(merged) and mi < len(pred_list):
                pred_list[mi] = merged
            if (isinstance(reach_list, list) and mi < len(reach_list)
                    and reach_list[mi] is None and riichi is not None):
                reach_list[mi] = sum(v for v in riichi if isinstance(v, (int, float)))
            # 联合分布的两支（用户 m09803）：前端要按「打 xx」/「打 xx 立直」展示，
            # 并把一根概率条左右一分为二（左半 = 默听支、右半 = 立直支），
            # 所以把两支各自折回 34 槽单独带出（旧报告没有 dahai_detail ⇒ 无此字段）。
            if mi < len(split_list):
                split_list[mi] = {
                    "dama": _collapse_dahai(dv[0]),
                    "riichi": (_collapse_dahai(riichi) if isinstance(riichi, (list, tuple))
                               else [0] * 34),
                }
        if any(s is not None for s in split_list):
            out["dahai_split"] = split_list
    if isinstance(out.get("reach"), list) and any(v is not None for v in out["reach"]):
        pass
    kan = _model_values(fr.get("kan"), models)
    if kan is not None:
        out["kan"] = [(dict(v) if isinstance(v, dict) else None) for v in kan]
    # 新版 NAGA 的「完整动作空间」（用户 m10081）：hora = {座位: [每模型和了概率]}（只有模型 1/2 有值），
    # ankan_pai / kakan_pai = [每模型 {牌名: 概率}]（直接给出「杠哪张牌」，可同时有多张），
    # kyushu = 九種九牌流局的概率。旧模型 / 旧报告没有这些字段 ⇒ 一字不动（用户 m09507 的零变化前提）。
    # 杠的牌名在这里转成牌种索引字符串，前端不用再解析牌名。
    if fr.get("hora") is not None:
        out["hora"] = dict((str(k), list(v)) for k, v in (fr.get("hora") or {}).items())
    if fr.get("kyushu") is not None:
        out["kyushu"] = _model_indexed(fr.get("kyushu"), models)
    for _pai_key in ("ankan_pai", "kakan_pai"):
        _raw = fr.get(_pai_key)
        if _raw is None:
            continue
        _conv = []
        for _v in _model_indexed(_raw, models):
            if not isinstance(_v, dict):
                _conv.append(None)
                continue
            _one = {}
            for _nm, _prob in _v.items():
                _kind = tile_kind(_nm)
                _one[str(_kind if _kind is not None else _nm)] = _prob
            _conv.append(_one)
        out[_pai_key] = _conv
    if fr.get("machi"):
        out["machi"] = dict((k, list(v)) for k, v in fr["machi"].items())
    for key in _FRAME_KEEP:
        val = fr.get(key)
        if val is not None:
            out[key] = val
    return out


def _report_id_from_path(path):
    if not path:
        return None
    name = os.path.basename(str(path))
    low = name.lower()
    for suf in NAGA_SUFFIXES:
        if low.endswith(suf):
            return name[:len(name) - len(suf)]
    return None


def report_id_of_path(path):
    """文件名 -> 完整 report_id（小写；含 ``v2_2`` 这类格式后缀，用户 m00418）。认不出返回 None。"""
    rid = _report_id_from_path(path)
    return rid.lower() if rid else None


def view_url(report_id):
    """NAGA 官方播放页 URL（打点行的 url 列；天凤牌谱用 mjlog.paipu_url）。"""
    return NAGA_VIEW_URL % (report_id or "")


def _meta(report, rounds, path, report_id):
    pi = report.get("player_info") or {}
    names = [str(n) for n in (pi.get("name") or [])]
    while len(names) < 4:
        names.append("P%d" % len(names))
    ri = report.get("report_info") or {}
    return {
        "names": names[:4],
        "dan": list(pi.get("dan") or []),
        "rate": [float(r) for r in (pi.get("rate") or [])],
        "sex": [],
        "config": {"red": True, "kui": True, "tonnan": bool(ri.get("hanchan", True)),
                   "sanma": False, "soku": False, "type": 0, "lobby": None},
        "oya": rounds[0]["init"]["oya"] if rounds else 0,
        "log_id": report_id,
        # 牌谱初始的主视角（用户 m06323 ①）：NAGA 报告里没有视角字段，对齐官方 viewer 默认 tw=0
        "viewer_seat": 0,
        "naga": True,
    }


# ------------------------------------------------------------------ 主入口
def to_game(report, path=None, report_id=None):
    """NAGA 报告 -> mjlog 同构的 game dict（另含 ``game["naga"]``）。"""
    report = load_report(report)
    model = balanced_model_index(report)
    # 报告里含哪些 AI 模型（用户 m04556 ①②）：规范名 / 系列名见 mjscore/ai_models.py
    models = ai_models.model_list(report.get("naga_types"))
    rounds, naga_rounds = [], []
    for ri, frames in enumerate(_round_lists(report.get("pred") or [])):
        init, events, naga_frames = _convert_round(frames, models, ri)
        rounds.append({"init": init, "events": events})
        naga_rounds.append(naga_frames)
    if report_id is None:
        report_id = report_id_of_path(path)
    game = {
        "meta": _meta(report, rounds, path, report_id),
        "rounds": rounds,
        "naga": {
            "report_id": report_id,
            "types": report.get("naga_types"),
            "version": report.get("naga_version"),
            "model": BALANCED_MODEL_NAME,
            "model_index": model,
            "models": models,
            "player_info": report.get("player_info"),
            "report_info": report.get("report_info"),
            "haihu_id": report.get("haihu_id"),
            "hash1": report.get("hash1"),
            "hash2": report.get("hash2"),
            "rounds": naga_rounds,
        },
    }
    # 打点链路（cli.python_records / feats.make_record）按天凤同构读这两个键（用户 m00080 目标 3）
    game["path"] = os.path.abspath(str(path)) if path else ""
    game["log_id"] = str(report_id or "")
    return game


def game_from_file(path):
    """读 ``<report_id>.naga``（旧后缀也认）-> game dict（report_id 从文件名推出，另补 path / log_id）。"""
    return to_game(load_report(path), path=path)