# -*- coding: utf-8 -*-
"""Mortal 复盘报告（``https://mjai.ekyu.moe/report/<report_id>.json``）-> 与天凤 xml / NAGA 同构的
game dict（用户 m05545 ① / m05937 ③：Mortal 系列牌谱沿用 NAGA 的分析与展示模板）。

报告结构（两个真实样例实测，``build/_scratch/mortal/*.json``）：

* 顶层 ``engine`` / ``version`` / ``player_id`` / ``mjai_log`` / ``review``；
* ``mjai_log`` = 标准 mjai 事件流（``start_kyoku`` … ``hora`` / ``ryukyoku`` … ``end_kyoku``）。
  **和了事件里没有役种 / 番 / 符 / 点数**，只有 ``deltas`` / ``ura_markers`` ⇒ 结算（符 / 点 / 役种）
  全部由 :mod:`mjscore.agari` 现算，点数据扣本场 300 / 供托 1000（口径与 NAGA 的
  :func:`mjscore.naga._hora_settle` 相同，用户 m02546）；事件流里也没有 ``kan`` / ``dora`` 的取样，
  真遇到 ``kakan`` / ``daiminkan`` / ``ankan`` / ``dora`` 时同样按 mjai 语义处理；
* ``review.model_tag`` = ``4.1a`` / ``4.1b`` / ``4.1c``（避四 / 平衡 / 争一，用户 m05806 ①）；
* ``review.kyokus[局].entries[]`` = **只含被复盘那一家（``player_id``）的决策点**（不像 NAGA 覆盖四家）。
  每条 entry 有 ``tile``（触发牌）/ ``last_actor``（触发者）/ ``tiles_left``（触发后的余牌数）/
  ``details[]``（``{action, q_value, prob}``，prob 是 0..1 浮点）⇒ 折算成 NAGA 帧里的
  ``dahai_pred``（万分比 34 数组）/ ``huro``（座位 → 下标 → 万分比，下标 0 = スルー、1/2/3 = 吃、
  4 = 碰、5 = 杠）/ ``reach`` / ``kan``（``{'1': 暗杠, '2': 加杠}``），挂到「触发那一决策的帧」上。

帧口径：帧 0 = 配牌，帧 i = 处理完 ``events[i-1]``（与 :mod:`mjscore.naga` 及前端
``nagaFrameOf()`` 完全一致）。Mortal 报告不提供 ``danger_*`` / ``tenpai_*`` / ``end_type`` /
``game_rank`` ⇒ 这些帧字段留空，前端相应位置显示空白 / ``—``。
"""

import json
import os

from . import ai_models, naga, paths

MORTAL_SUFFIXES = paths.MORTAL_SUFFIXES
MORTAL_VIEW_URL = "https://mjai.ekyu.moe/report/%s.json"
MODEL_INDEX = 0                      # Mortal 报告只含一种模型 ⇒ 「模型维」恒为第 0 档

# 触发一次「自己的决策」的消息（摸牌后选打牌 / 鸣牌后选打牌），以及「别人打牌后的鸣牌决策」
OWN_TRIGGERS = ("tsumo", "chi", "pon", "daiminkan", "kakan", "ankan")
CALL_TRIGGERS = ("dahai", "kakan")   # kakan 对应抢杠（チャンカン）
HURO_PASS, HURO_PON, HURO_KAN = 0, 4, 5
KAN_ANKAN, KAN_KAKAN = "1", "2"
_END_TYPES = ("hora", "ryukyoku")
_SKIP_TYPES = ("start_kyoku", "end_kyoku", "start_game", "end_game")


def is_mortal_file(path):
    """文件名后缀是不是 Mortal 报告（``.mortal-a`` / ``.mortal-b`` / ``.mortal-c``，旧 ``.mortal``）。"""
    low = os.path.basename(str(path or "")).lower()
    return low.endswith(MORTAL_SUFFIXES)


def _report_id_from_path(path):
    if not path:
        return None
    name = os.path.basename(str(path))
    low = name.lower()
    for suf in MORTAL_SUFFIXES:
        if low.endswith(suf):
            return name[:len(name) - len(suf)]
    return None


def report_id_of_path(path):
    """文件名 -> 报告 id（小写）。认不出返回 None。"""
    rid = _report_id_from_path(path)
    if not rid:
        base, ext = os.path.splitext(os.path.basename(str(path or "")))
        if ext.lower() == ".json" and base:
            rid = base
    return rid.lower() if rid else None


def view_url(report_id):
    """Mortal 报告地址（打点行的 url 列；天凤用 :func:`mjscore.mjlog.paipu_url`、NAGA 用 naga.view_url）。"""
    return MORTAL_VIEW_URL % (report_id or "")


def load_report(source):
    """报告 dict / 文件路径 / 原始字节 -> 报告 dict（顺带校验 ``mjai_log`` / ``review``）。"""
    if isinstance(source, dict):
        data = source
    else:
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
        else:
            if not os.path.exists(str(source)):
                raise ValueError("文件不存在：%s" % source)
            with open(str(source), "rb") as fh:
                raw = fh.read()
        if raw[:2] == b"\x1f\x8b":                       # 万一是 gzip（用户自己压过）
            import gzip
            raw = gzip.decompress(raw)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:                         # noqa: BLE001
            raise ValueError("内容不是 JSON：%s" % exc)
    if not isinstance(data, dict) or "mjai_log" not in data:
        raise ValueError("内容不像 Mortal 报告（缺少 mjai_log 字段）")
    if not isinstance(data.get("review"), dict):
        raise ValueError("内容不像 Mortal 报告（缺少 review 字段）")
    return data


def model_list(report):
    """报告 -> 模型表（与 :func:`mjscore.ai_models.model_list` 同构；Mortal 只有一种模型）。"""
    tag = str(((report or {}).get("review") or {}).get("model_tag") or "").strip()
    name = ai_models.normalize(tag) if tag else ai_models.MORTAL_41B
    # 软件暂时只支持 4.1 的三种风格（用户 m05806 ①）⇒ 认不出的 model_tag 一律按 4.1-平衡 处理，
    # 免得展示一个我们并不支持的模型名（第零类五项也就都不会点亮）。
    if name not in ai_models.MORTAL_TAG_TO_NAME.values():
        name, tag = ai_models.MORTAL_41B, "4.1b"
    return [{"index": MODEL_INDEX, "raw": tag, "name": name,
             "series": ai_models.SERIES_MORTAL}]


def _reviewed_seat(report):
    """被复盘的那一家（报告只含他一人的决策；认不出按 0 号位）。"""
    try:
        seat = int(report.get("player_id"))
    except (TypeError, ValueError):
        return 0
    return seat if 0 <= seat < 4 else 0


def _split_rounds(mjai_log):
    """``mjai_log`` -> ``[{"start": <start_kyoku>, "msgs": [...], "ends": [<hora|ryukyoku>, ...]}]``。

    ``msgs`` 不含 ``start_kyoku`` / ``end_kyoku`` 与结束事件；``ends`` 是和了 / 流局事件（可能两条：
    一炮双响按 mjai 语义就是两条 ``hora``）。
    """
    rounds, cur = [], None
    for msg in mjai_log or []:
        if not isinstance(msg, dict):
            continue
        t = msg.get("type")
        if t == "start_kyoku":
            cur = {"start": msg, "msgs": [], "ends": []}
            rounds.append(cur)
            continue
        if cur is None:
            continue
        if t == "end_kyoku":
            cur = None
            continue
        if t in _END_TYPES:
            cur["ends"].append(msg)
            continue
        if t in _SKIP_TYPES:
            continue
        cur["msgs"].append(msg)
    return rounds

def _dora_markers(start, msgs):
    """明牌指示牌：配牌那 1 张 + 后续 ``dora`` 事件（Mortal 报告里通常没有，遇到也认）。"""
    marks = []
    if start.get("dora_marker") is not None:
        marks.append(start.get("dora_marker"))
    for m in msgs:
        if m.get("type") == "dora" and m.get("dora_marker") is not None:
            marks.append(m.get("dora_marker"))
    return marks


def _scores_after(state, deltas, applied, e):
    """和了 / 流局后的四家点数：报告给了就用报告的，否则用本局起始点 + 已结算 + 本次 deltas 推。"""
    if isinstance(e.get("scores"), (list, tuple)) and len(e["scores"]) == 4:
        return [int(x) for x in e["scores"]]
    if state is None:
        return list(applied)
    out = []
    for i in range(4):
        base = int((state["players"][i] or {}).get("score") or 0)
        out.append(base + int(applied[i]) + int(deltas[i]))
    return out


def _end_msgs_for(rnd, state, table, dora_markers, honba, kyotaku):
    """把本局的 ``hora`` / ``ryukyoku`` 事件整理成 :func:`mjscore.naga._end_event` 认的形态。

    报告里和了事件只有 ``deltas`` / ``ura_markers``（没有役种 / 番 / 符 / 点数、没有 ``scores``）
    ⇒ 这里补上 ``ba``（本场 / 供托，供托取开局值 + 本局立直宣言数）与 ``scores``（起始点 + deltas），
    符 / 点 / 役种留给 :func:`mjscore.naga._hora_settle` 用 :mod:`mjscore.agari` 现算。
    """
    ends, applied = [], [0, 0, 0, 0]
    for e in rnd.get("ends") or []:
        deltas = [int(x or 0) for x in (e.get("deltas") or [0, 0, 0, 0])][:4]
        while len(deltas) < 4:
            deltas.append(0)
        msg = dict(e)
        msg["deltas"] = deltas
        msg["scores"] = _scores_after(state, deltas, applied, e)
        msg["ba"] = [int(honba), int(kyotaku)]
        if e.get("type") == "hora":
            # mjai 的里宝牌指示牌是牌名（"3s"），而结算链路（:func:`mjscore.naga._hora_ctx`）要的是
            # 牌 id ⇒ 用与 NAGA 一样的 _side_ids 换算（用户 m05937 ③：Mortal 沿用 NAGA 模板）
            msg["uradora_markers"] = naga._side_ids(e.get("ura_markers"), table)
            msg["dora_markers"] = list(dora_markers)
        for i in range(4):
            applied[i] += deltas[i]
        ends.append(msg)
    return ends


def _replay(init, events):
    """重放事件流，返回末状态（异常 -> None）。"""
    return naga._replay_state(init, events)


def _tiles_left_by_event(events):
    """每一步事件之后的余牌数（= 70 - 已摸牌数；转换出的 ``draw`` 事件一一对应 ``tsumo``）。

    与 :mod:`mjscore.replay` 状态的 ``tilesLeft`` 同口径 —— mortal entry 的 ``tiles_left`` 正是
    触发消息处理完之后的这个值（实测逐条相等），所以能用来精确定位触发消息。
    """
    left, out = 70, []
    for ev in events:
        if ev.get("type") == "draw":
            left -= 1
        out.append(max(0, left))
    return out


def _base_frame(msg_type, m):
    """帧基础字段（与 NAGA 帧同构；Mortal 报告没有 ``danger_*`` / ``tenpai_*`` / ``end_type`` / ``game_rank``）。"""
    return {
        "msg": msg_type,
        "actor": m.get("actor"),
        "target": m.get("target"),
        "pai": m.get("pai"),
        "consumed": list(m.get("consumed") or []),
        "kind": m.get("kind"),
        "tsumogiri": bool(m.get("tsumogiri")),
    }


def _convert_round(rnd, entries, models, seat, ri):
    """一局 -> ``(init, events, frames, attached)``（帧口径与 NAGA 完全一致）。"""
    start = rnd["start"]
    table = naga._Table()
    for s, names in enumerate(start.get("tehais") or []):
        if s >= 4:
            break
        table.hands[s] = naga._side_ids(names, table)
    bakaze = str(start.get("bakaze") or "E").upper()
    scores = [int(x or 0) for x in (start.get("scores") or [0, 0, 0, 0])][:4]
    while len(scores) < 4:
        scores.append(0)
    init = {
        "round": naga._BAKAZE_INDEX.get(bakaze, 0) * 4 + (int(start.get("kyoku") or 1) - 1),
        "combo": int(start.get("honba") or 0),
        "kyotaku": int(start.get("kyotaku") or 0),
        "dices": [0, 0],
        "dora": table.draw(start.get("dora_marker")),
        "scores": scores,
        "oya": int(start.get("oya") or 0),
        "hands": [list(h) for h in table.hands],
    }
    pairs = []
    for m in rnd["msgs"]:
        ev = naga._event(m, table)
        if ev is not None:
            pairs.append((m, ev))
    events = [ev for _m, ev in pairs]
    state = _replay(init, events)
    kyotaku = int((state or {}).get("kyotaku") or init["kyotaku"])
    end_msgs = _end_msgs_for(rnd, state, table, _dora_markers(start, rnd["msgs"]),
                             init["combo"], kyotaku)
    events.extend(naga._end_events(end_msgs, table, [m for m, _ev in pairs], state))

    frames = [_base_frame("start_kyoku", start)]
    for m, _ev in pairs:
        frames.append(_base_frame(m.get("type"), m))
    tiles = _tiles_left_by_event([ev for _m, ev in pairs])
    attached = _attach_entries(frames, pairs, tiles, entries, seat)
    while len(frames) < len(events) + 1:     # 末帧 = 和了 / 流局帧（没有决策字段）
        frames.append({"msg": None})
    return init, events, frames, attached


def _find_trigger(pairs, tiles, start, left, actor, want, kinds):
    """从 ``start`` 起找触发某条 entry 的消息下标。

    判据（用户 m05545 ① 的结构分析）：消息类型在 ``kinds`` 内 + 余牌数等于 ``entry.tiles_left``
    （实测逐条相等）+ 座位对得上 + 触发牌对得上（``dahai`` 的 ``pai`` 就是被打出的那张）。
    """
    for i in range(max(0, int(start)), len(pairs)):
        m = pairs[i][0]
        if m.get("type") not in kinds:
            continue
        if left is not None and int(tiles[i]) != int(left):
            continue
        try:
            got = int(m.get("actor")) if m.get("actor") is not None else None
        except (TypeError, ValueError):
            got = None
        if actor is not None and got != int(actor):
            continue
        if want is not None and naga.tile_kind(m.get("pai")) != want:
            continue
        return i
    return None


def _attach_entries(frames, pairs, tiles, entries, seat):
    """把 ``review.kyokus[..].entries`` 的决策概率挂到对齐的帧上。

    返回 ``{"hit": 命中条数, "miss": 没找到触发消息的条数}``。同一次摸牌可以对应两条 entry
    （立直 + 立直后的打牌 ⇒ 同一帧既有 ``dahai_pred`` 又有 ``reach``，与 NAGA 的形态一致）。
    """
    me = int(seat)
    cursor, hit, miss = 0, 0, 0
    for en in entries or []:
        if not isinstance(en, dict):
            continue
        last = en.get("last_actor")
        try:
            last = int(last) if last is not None else None
        except (TypeError, ValueError):
            last = None
        own = last is None or last == me
        kinds = OWN_TRIGGERS if own else CALL_TRIGGERS
        actor = me if own else last
        want = naga.tile_kind(en.get("tile"))
        left = en.get("tiles_left")
        idx = _find_trigger(pairs, tiles, cursor, left, actor, want, kinds)
        if idx is None:
            idx = _find_trigger(pairs, tiles, cursor, None, actor, want, kinds)
        if idx is None and want is not None:
            idx = _find_trigger(pairs, tiles, cursor, left, actor, None, kinds)
        if idx is None or idx + 1 >= len(frames):
            miss += 1
            continue
        cursor = idx                      # 不 +1：同一次触发可能承载两条 entry
        pay = _payload(en)
        if not pay:
            continue                      # 和了 / 自摸 / 荣和的选项没有对应展示位（NAGA 也没有）
        _merge_payload(frames[idx + 1], pay, me)
        hit += 1
    return {"hit": hit, "miss": miss}


def _pct(prob):
    """0..1 浮点 -> 万分比整数（与 NAGA 报告 / 官方 viewer 的 /1e4 口径一致）。"""
    try:
        return int(round(float(prob) * 10000))
    except (TypeError, ValueError):
        return 0


def _chi_index(called, act):
    """吃牌的牌对 -> NAGA ``huro`` 下标（1 = r+1,r+2；2 = r-1,r+1；3 = r-2,r-1，与官方一致）。"""
    if called is None or called >= 27:
        return None
    suit, r = called // 9, called % 9
    ranks = []
    for name in (act.get("consumed") or []):
        k = naga.tile_kind(name)
        if k is None or k >= 27 or k // 9 != suit:
            return None
        ranks.append(k % 9)
    if len(ranks) != 2:
        return None
    lo, hi = min(ranks), max(ranks)
    if lo == r + 1 and hi == r + 2:
        return 1
    if lo == r - 1 and hi == r + 1:
        return 2
    if lo == r - 2 and hi == r - 1:
        return 3
    return None


def _payload(en):
    """一条 entry 的 ``details`` -> NAGA 帧字段（万分比）。返回 ``{}`` 表示这条不展示。

    * ``dahai`` -> ``dahai_pred``（34 数组，按打出的牌的 kind 落位）
    * ``reach`` -> ``reach``（标量）
    * ``ankan`` / ``kakan`` -> ``kan``（``{'1': 暗杠, '2': 加杠}``）；``daiminkan`` -> ``huro[5]``
    * ``pon`` -> ``huro[4]``、``chi`` -> ``huro[1|2|3]``、``none`` -> ``huro[0]``（スルー）
    * 含 ``hora`` 的 entry（荣和 / 自摸）报告里没有对应展示位（NAGA 也没有）-> 整条不展示
    """
    details = en.get("details") or []
    types = set()
    for d in details:
        if isinstance(d, dict):
            t = (d.get("action") or {}).get("type")
            if t:
                types.add(t)
    if not types or "hora" in types:
        return {}
    dahai = [0] * 34
    has_dahai, reach, kan, huro = False, None, {}, {}
    called = naga.tile_kind(en.get("tile"))
    for d in details:
        if not isinstance(d, dict):
            continue
        act = d.get("action") or {}
        t = act.get("type")
        pct = _pct(d.get("prob"))
        if t == "dahai":
            k = naga.tile_kind(act.get("pai"))
            if k is not None:
                dahai[k] = pct
                has_dahai = True
        elif t == "reach":
            reach = pct
        elif t == "ankan":
            kan[KAN_ANKAN] = pct
        elif t == "kakan":
            kan[KAN_KAKAN] = pct
        elif t == "daiminkan":
            huro[HURO_KAN] = pct
        elif t == "pon":
            huro[HURO_PON] = pct
        elif t == "chi":
            idx = _chi_index(called, act)
            if idx:
                huro[idx] = pct
        elif t == "none":
            huro[HURO_PASS] = pct
    out = {}
    if has_dahai:
        out["dahai_pred"] = dahai
    if reach is not None:
        out["reach"] = reach
    if kan:
        out["kan"] = kan
    if huro:
        out["huro"] = huro
    return out


def _merge_payload(fr, pay, seat):
    """把一条 entry 折算出的字段并进帧（模型维恒为第 0 档；同一帧可能被两条 entry 叠加）。"""
    if pay.get("dahai_pred") is not None:
        fr["dahai_pred"] = [pay["dahai_pred"]]
    if pay.get("reach") is not None:
        fr["reach"] = [pay["reach"]]
    if pay.get("kan"):
        fr["kan"] = [pay["kan"]]
    if pay.get("huro"):
        huro = dict(fr.get("huro") or {})
        key = str(seat)
        cur = huro.get(key)
        if isinstance(cur, (list, tuple)) and cur and isinstance(cur[0], dict):
            cur = dict(cur[0])
        else:
            cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update({str(k): v for k, v in pay["huro"].items()})
        huro[key] = [cur]
        fr["huro"] = huro


def _meta(report, rounds, path, report_id):
    """天凤 / NAGA 同构的 ``meta``（名字取 ``start_game.names``；性别 / 段位 / 段位pt Mortal 不提供）。"""
    names = []
    for m in report.get("mjai_log") or []:
        if isinstance(m, dict) and m.get("type") == "start_game":
            names = [str(x) for x in (m.get("names") or [])]
            break
    while len(names) < 4:
        names.append("P%d" % len(names))
    hanchan = str(report.get("game_length") or "").lower() == "hanchan"
    return {
        "names": names[:4],
        "dan": [], "rate": [], "sex": [],
        "config": {"red": True, "kui": True, "tonnan": hanchan, "sanma": False, "soku": False,
                   "type": 0, "lobby": None},
        "oya": int(((rounds[0]["init"] if rounds else {}) or {}).get("oya") or 0),
        "log_id": report_id,
        # 牌谱初始的主视角（用户 m06323 ①）= 被复盘的那一家（review.player_id）
        "viewer_seat": _reviewed_seat(report),
        "naga": True,
        "mortal": True,
    }


def to_game(report, path=None, report_id=None):
    """Mortal 报告 -> game dict（``meta`` / ``rounds`` / ``naga``，打点与前端播放共用）。"""
    report = load_report(report)
    models = model_list(report)
    reviewed = _reviewed_seat(report)
    kyokus = ((report.get("review") or {}).get("kyokus") or [])
    rounds, ai_rounds, hit, miss = [], [], 0, 0
    for ri, rnd in enumerate(_split_rounds(report.get("mjai_log"))):
        entries = []
        if ri < len(kyokus) and isinstance(kyokus[ri], dict):
            entries = kyokus[ri].get("entries") or []
        init, events, frames, attached = _convert_round(rnd, entries, models, reviewed, ri)
        rounds.append({"init": init, "events": events})
        ai_rounds.append(frames)
        hit += int(attached.get("hit") or 0)
        miss += int(attached.get("miss") or 0)
    if not report_id:
        report_id = report_id_of_path(path)
    meta = _meta(report, rounds, path, report_id)
    hanchan = bool((meta.get("config") or {}).get("tonnan"))
    game = {
        "meta": meta,
        "rounds": rounds,
        "naga": {
            "kind": "mortal",
            "report_id": report_id,
            "types": {str(models[0]["index"]): models[0]["raw"]},
            "version": report.get("version"),
            "model": models[0]["name"],
            "model_index": MODEL_INDEX,
            "models": models,
            "player_id": reviewed,
            "source": "mjai.ekyu.moe",
            "player_info": [{"name": nm} for nm in meta["names"]],
            "report_info": {"hanchan": hanchan, "custom_haihu": False,
                            "use_dan_pt_allocation": False,
                            "dan_pt_allocation": [[0, 0, 0, 0] for _ in range(4)],
                            "raw_score_ratio": False},
            "entries": {"hit": hit, "miss": miss},
            "rounds": ai_rounds,
        },
    }
    game["path"] = os.path.abspath(str(path)) if path else ""
    game["log_id"] = str(report_id or "")
    return game


def game_from_file(path):
    """``.mortal-a`` / ``.mortal-b`` / ``.mortal-c``（旧 ``.mortal``）-> game dict。"""
    return to_game(load_report(path), path=path, report_id=report_id_of_path(path))
def looks_like_mortal(source):
    """内容嗅探：这份报告是不是 Mortal 报告（用户 m05937 ③）。

    下载落盘时会带 ``.mortal-a`` / ``-b`` / ``-c`` 后缀，但 mjai.ekyu.moe 的报告地址是
    ``<report_id>.json``（浏览器另存出来也是 ``.json``），与 NAGA 报告的旧后缀撞车 ⇒
    用内容里的 ``mjai_log`` / ``review`` 两个键消歧（NAGA 报告的特征键是 ``pred`` / ``info``）。
    只对 ``.json`` / ``.gz`` 这类歧义后缀调用，正常 ``.naga`` / ``.mortal-*`` 不必嗅探。
    """
    try:
        data = load_report(source)
    except Exception:                       # noqa: BLE001 - 不是 JSON / 不是 Mortal 报告
        return False
    return isinstance(data, dict) and "mjai_log" in data and "review" in data