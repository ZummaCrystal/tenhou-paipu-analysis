# -*- coding: utf-8 -*-
"""逐帧回放引擎（Python 版，行为对齐 web/js/replay.js）。

只维护特征打点需要的部分：手牌 / 副露 / 牌河 / 立直 / 分数 / 供托 / 宝牌 / 摸牌。
帧号约定与 web/js/replay.js 完全一致：
    frames[0] = 开局（配牌后、未处理任何事件）
    frames[k] = 处理完第 k-1 个事件后的状态  =>  事件下标 i 对应帧下标 i+1

校验不变量（与 test/selftest.js 同款）：
    - 每张牌 id(0..135) 在「手牌 ∪ 副露 ∪ 牌河(被鸣走的除外) ∪ 宝牌指示牌」中至多出现一次；
    - 每种 kind 至多 4 张（被鸣走的那张同时留在牌河与副露里，只算一张）。
"""

from . import mjlog

CALL_NAME = {"chi": "吃", "pon": "碰", "kakan": "加杠", "daiminkan": "大明杠",
             "ankan": "暗杠", "nuki": "拔北"}
# 会破坏「门前」的副露（拔北 / 暗杠都不算副露计数）
OPEN_CALLS = ("chi", "pon", "kakan", "daiminkan")


def seat_wind(seat, oya):
    return mjlog.WINDS[(seat - oya) % 4]


def clone_state(st):
    return {
        "round_index": st["round_index"], "round": st["round"], "honba": st["honba"],
        "kyotaku": st["kyotaku"], "oya": st["oya"], "scores": list(st["scores"]),
        "players": [{
            "hand": list(p["hand"]),
            "melds": [{"callType": m["callType"], "tiles": list(m["tiles"]),
                       "calledId": m["calledId"], "from": m["from"], "open": m["open"]}
                      for m in p["melds"]],
            "river": [dict(r) for r in p["river"]],
            "riichi": p["riichi"], "riichiPending": p["riichiPending"],
            "score": p["score"], "name": p["name"], "turns": p["turns"],
        } for p in st["players"]],
        "dora": list(st["dora"]), "dices": st["dices"], "drawn": st["drawn"],
        "tilesLeft": st["tilesLeft"], "phase": st["phase"], "result": st["result"],
        "reveal": list(st["reveal"]), "desc": st["desc"], "evIndex": st["evIndex"],
        "warnings": list(st["warnings"]),
    }


def initial_state(game, round_index):
    rnd = game["rounds"][round_index]
    init = rnd["init"]
    names = game["meta"]["names"] or []
    return {
        "round_index": round_index, "round": init["round"], "honba": init["combo"],
        "kyotaku": init["kyotaku"], "oya": init["oya"], "scores": list(init["scores"]),
        "players": [{
            "hand": list(init["hands"][i]), "melds": [], "river": [],
            "riichi": False, "riichiPending": False, "score": init["scores"][i],
            "name": (names[i] if i < len(names) and names[i] else "P%d" % i),
            # 出牌计数（巡目 = turns + 1）：打牌 +1；暗杠/加杠视为出牌 +1；吃/碰/大明杠不算
            "turns": 0,
        } for i in range(4)],
        "dora": [init["dora"]], "dices": init["dices"], "drawn": None, "tilesLeft": 70,
        "phase": "playing", "result": None, "reveal": [], "desc": "开局 · 配牌",
        "evIndex": -1, "warnings": [],
    }


# --------------------------------------------------------------- 手牌操作
def take_kind(hand, k):
    """移除指定 kind 的一张（优先移除普通牌，保留赤宝牌）。"""
    plain = red = -1
    for i, t in enumerate(hand):
        if mjlog.kind_of(t) == k:
            if mjlog.is_red(t):
                red = i
            else:
                plain = i
                break
    idx = plain if plain >= 0 else red
    if idx < 0:
        return None
    return hand.pop(idx)


def take_exact(hand, tid):
    if tid in hand:
        hand.remove(tid)
        return tid
    return take_kind(hand, mjlog.kind_of(tid))


# --------------------------------------------------------------- 事件处理
def apply_call(st, ev):
    p = ev["player"]
    pl = st["players"][p]
    called_id = None
    ct = ev["callType"]

    if ct in ("chi", "pon", "daiminkan"):
        cp = st["players"][ev["callee"]]
        if cp["river"]:
            last = cp["river"][-1]
            last["called"] = True
            called_id = last["tile"]

    nm = CALL_NAME.get(ct, ct)
    if ct in ("nuki", "kakan"):
        if take_exact(pl["hand"], ev["tiles"][0]) is None:
            st["warnings"].append("%s: 手牌中找不到 %s" % (nm, mjlog.tile_name(ev["tiles"][0])))
    else:
        if called_id is not None and called_id not in ev["tiles"]:
            st["warnings"].append("%s: 副露[%s] 与牌河 %s 不一致" % (
                nm, mjlog.names_to_str(ev["tiles"]), mjlog.tile_name(called_id)))
        for t in ev["tiles"]:
            if t == called_id:
                continue
            if take_exact(pl["hand"], t) is None:
                st["warnings"].append("%s: 手牌中找不到 %s" % (nm, mjlog.tile_name(t)))

    if ct == "kakan":
        found = False
        for m in pl["melds"]:
            if m["callType"] == "pon" and mjlog.kind_of(m["tiles"][0]) == mjlog.kind_of(ev["tiles"][0]):
                m["callType"] = "kakan"; m["tiles"] = list(ev["tiles"]); found = True
                break
        if not found:
            pl["melds"].append({"callType": "kakan", "tiles": list(ev["tiles"]),
                                "calledId": None, "from": None, "open": True})
    else:
        pl["melds"].append({"callType": ct, "tiles": list(ev["tiles"]), "calledId": called_id,
                            "from": ev["callee"], "open": ct != "ankan"})

    if ct in ("ankan", "kakan"):
        # 暗杠/加杠的动作视为出了一次牌（巡目 +1）；吃/碰/大明杠不算
        pl["turns"] += 1

    st["drawn"] = None
    st["desc"] = pl["name"] + " " + nm


def apply_event(st, ev):
    t = ev["type"]
    if t == "draw":
        p = ev["player"]; pl = st["players"][p]
        pl["hand"].append(ev["tile"])
        # 摸牌不加巡目：巡目按「出牌」计（见 apply_call 的杠 与 discard 的 turns）
        st["drawn"] = {"player": p, "tile": ev["tile"]}
        st["tilesLeft"] = max(0, st["tilesLeft"] - 1)
        st["desc"] = pl["name"] + " 摸牌 " + mjlog.tile_name(ev["tile"])
    elif t == "discard":
        p = ev["player"]; pl = st["players"][p]
        tsumogiri = bool(st["drawn"] and st["drawn"]["player"] == p and st["drawn"]["tile"] == ev["tile"])
        if ev["tile"] in pl["hand"]:
            pl["hand"].remove(ev["tile"])
        elif take_kind(pl["hand"], mjlog.kind_of(ev["tile"])) is None:
            st["warnings"].append("打牌: 手牌中找不到 " + mjlog.tile_name(ev["tile"]))
        entry = {"tile": ev["tile"], "tsumogiri": tsumogiri, "riichi": False, "called": False, "win": False}
        if pl["riichiPending"]:
            entry["riichi"] = True
            pl["riichiPending"] = False
        pl["river"].append(entry)
        pl["turns"] += 1   # 出牌一次 +1（巡目口径）
        st["drawn"] = None
        st["desc"] = pl["name"] + (" 摸切 " if tsumogiri else " 打牌 ") + mjlog.tile_name(ev["tile"])
    elif t == "call":
        apply_call(st, ev)
    elif t == "reach":
        p = ev["player"]; pl = st["players"][p]
        if ev["step"] == 1:
            pl["riichiPending"] = True
            st["desc"] = pl["name"] + " 立直宣告"
        else:
            pl["riichi"] = True
            pl["riichiPending"] = False
            if ev.get("scores"):
                st["scores"] = list(ev["scores"])
                for i in range(4):
                    st["players"][i]["score"] = st["scores"][i]
            st["kyotaku"] += 1
            st["desc"] = pl["name"] + " 立直（供托 +1000）"
    elif t == "dora":
        st["dora"].append(ev["tile"])
        st["desc"] = "新宝牌指示牌 " + mjlog.tile_name(ev["tile"])
    elif t == "agari":
        st["phase"] = "agari"
        for i in range(4):
            st["scores"][i] = ev["before"][i] + ev["gain"][i]
            st["players"][i]["score"] = st["scores"][i]
        win_tile = None
        if ev["winner"] == ev["fromWho"]:
            if st["drawn"] and st["drawn"]["player"] == ev["winner"]:
                win_tile = st["drawn"]["tile"]
        else:
            dp = st["players"][ev["fromWho"]]
            if dp["river"]:
                dp["river"][-1]["win"] = True
                win_tile = dp["river"][-1]["tile"]
        ev["winTile"] = win_tile
        st["reveal"] = st["reveal"] + [ev["winner"]]
        st["result"] = ev
        st["kyotaku"] = 0
        st["desc"] = st["players"][ev["winner"]]["name"] + (
            " 自摸和了" if ev["winner"] == ev["fromWho"] else
            " 荣和（放铳：" + st["players"][ev["fromWho"]]["name"] + "）")
    elif t == "ryuukyoku":
        st["phase"] = "ryuukyoku"
        for i in range(4):
            st["scores"][i] = ev["before"][i] + ev["gain"][i]
            st["players"][i]["score"] = st["scores"][i]
        for i in range(4):
            if ev["hands"][i]:
                st["players"][i]["hand"] = list(ev["hands"][i])
        reason = ev.get("reason") or ""
        ev["tenpai"] = [i for i in range(4) if ev["hands"][i]]
        ev["nagashi"] = [i for i in range(4) if reason == "nm" and ev["gain"][i] > 0]
        declarer = ev.get("who")
        if declarer is None:
            declarer = st["drawn"]["player"] if st["drawn"] else -1
        if reason == "nm":
            st["reveal"] = list(ev["nagashi"])
        elif reason == "yao9":
            st["reveal"] = [declarer] if declarer >= 0 else []
        elif reason == "reach4":
            st["reveal"] = [0, 1, 2, 3]
        elif reason in ("kaze4", "rck4"):
            st["reveal"] = []
        elif reason == "tripleRon":
            st["reveal"] = [s for s in (0, 1, 2, 3) if s != declarer] if declarer >= 0 else []
        else:
            st["reveal"] = list(ev["tenpai"])
        st["result"] = ev
        st["kyotaku"] = 0
        st["desc"] = "流局（%s）" % (mjlog.REASON_NAME.get(reason, "荒牌流局"))


def iter_events(game, round_index, state=None):
    """逐事件走一遍，产出 (ev_index, ev, state_after)。state_after 是就地修改的同一个 dict。"""
    st = state if state is not None else initial_state(game, round_index)
    for i, ev in enumerate(game["rounds"][round_index]["events"]):
        apply_event(st, ev)
        st["evIndex"] = i
        yield i, ev, st


# --------------------------------------------------------------- 不变量自检
def count_tiles(st):
    """统计每个牌 id / kind 的出现次数。

    约定与 web/js/replay.js 一致：被鸣走的牌在牌河与副露里各存在一份，但只算一张
    => 牌河里 called=True 的那张不计数，副露里的那张计数。
    """
    seen, kinds = {}, {}
    def add(t):
        seen[t] = seen.get(t, 0) + 1
        kinds[mjlog.kind_of(t)] = kinds.get(mjlog.kind_of(t), 0) + 1
    for p in st["players"]:
        for t in p["hand"]:
            add(t)
        for m in p["melds"]:
            for t in m["tiles"]:
                add(t)
        for r in p["river"]:
            if r["called"]:
                continue
            add(r["tile"])
    for t in st["dora"]:
        add(t)
    return seen, kinds


def check_invariants(game, round_index):
    """逐帧校验：返回 (错误列表, 帧数)。空错误 = 通过。"""
    st = initial_state(game, round_index)
    errs = []
    n = 0
    for i, ev in enumerate(game["rounds"][round_index]["events"]):
        apply_event(st, ev)
        st["evIndex"] = i
        n += 1
        seen, kinds = count_tiles(st)
        for t, c in seen.items():
            if c > 1:
                errs.append("局 %d 帧 %d：牌 %s 出现 %d 次" % (round_index, i + 1, mjlog.tile_name(t), c))
        for k, c in kinds.items():
            if c > 4:
                errs.append("局 %d 帧 %d：kind %d 出现 %d 次" % (round_index, i + 1, k, c))
        for w in st["warnings"]:
            if w not in errs:
                errs.append("局 %d 帧 %d：%s" % (round_index, i + 1, w))
    return errs, n