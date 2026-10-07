# -*- coding: utf-8 -*-
"""mjlog XML 解析器（Python 版，行为对齐 web/js/mjlog.js）。

牌谱文件是 UTF-8 XML（通常整份无换行），所有子节点均为自闭合标签，
属性值中不含双引号与 '>'，因此用正则分词即可，无需 XML 库。

牌 id 编码：0..135，tile>>2 = kind(0..33)，tile&3 = 同种第几张。
    0..8   1m..9m      9..17  1p..9p      18..26 1s..9s      27..33 東南西北白發中
赤宝牌 = (tile&3)==0 且 kind%9==4（即 id 16 / 52 / 88 分别是赤5m/赤5p/赤5s）。
"""

import os
import re

SUIT_CHAR = ("m", "p", "s", "z")
WINDS = ("東", "南", "西", "北")
DIRS = ("東", "南", "西", "北")
NUM_KANJI = ("一", "二", "三", "四")

_TAG_RE = re.compile(r'<([A-Za-z][A-Za-z0-9]*)((?:\s+[A-Za-z0-9_]+="[^"]*")*)\s*/?>')
_ATTR_RE = re.compile(r'([A-Za-z0-9_]+)="([^"]*)"')


# ------------------------------------------------------------------ 牌
def kind_of(tid):
    return tid >> 2


def suit_of(tid):
    return kind_of(tid) // 9


def rank_of(tid):
    return kind_of(tid) % 9 + 1


def is_honor(tid):
    return kind_of(tid) >= 27


def is_red(tid):
    # 赤宝牌 = 5m/5p/5s 的第一张；字牌（白 = kind 31）没有赤宝牌
    return kind_of(tid) < 27 and (tid & 3) == 0 and (kind_of(tid) % 9) == 4


def tile_name(tid):
    k = kind_of(tid)
    s = k // 9
    if s == 3:
        return "%dz" % (k - 26)
    n = k % 9 + 1
    if n == 5 and (tid & 3) == 0:
        return "0" + SUIT_CHAR[s]
    return "%d%s" % (n, SUIT_CHAR[s])


def names_to_str(tiles):
    return " ".join(tile_name(t) for t in tiles)


# ------------------------------------------------------------------ XML 分词
def parse_attrs(text):
    out = {}
    for m in _ATTR_RE.finditer(text):
        out[m.group(1)] = m.group(2)
    return out


def tokenize(text):
    """把 XML 切成 [{tag, attr}, ...]（只保留带属性的自闭合标签）。"""
    return [{"tag": m.group(1), "attr": parse_attrs(m.group(2) or "")}
            for m in _TAG_RE.finditer(text)]


# ------------------------------------------------------------------ 小工具
def ints(s):
    if not s:
        return []
    return [int(x, 10) for x in s.split(",") if x != ""]


def floats(s):
    if not s:
        return []
    return [float(x) for x in s.split(",") if x != ""]


def nest_pairs(a):
    return [[a[i], a[i + 1]] for i in range(0, len(a) - 1, 2)]


def _unq(s):
    from urllib.parse import unquote
    try:
        return unquote(s, encoding="utf-8", errors="replace")
    except Exception:
        return s


def score_pairs(sc):
    before, gain = [], []
    for i in range(0, len(sc) - 1, 2):
        before.append(sc[i] * 100)
        gain.append(sc[i + 1] * 100)
    return before, gain


# ------------------------------------------------------------------ 鸣牌解码
def decode_chi(m):
    t = (m & 0xFC00) >> 10
    r = t % 3
    t = t // 3
    t = 9 * (t // 7) + (t % 7)
    t *= 4
    h = [t + ((m & 0x0018) >> 3), t + 4 + ((m & 0x0060) >> 5), t + 8 + ((m & 0x0180) >> 7)]
    if r == 1:
        h = [h[1], h[0], h[2]]
    elif r == 2:
        h = [h[2], h[0], h[1]]
    return h


def _triple(m, extra):
    t = (m & 0xFE00) >> 9
    r = t % 3
    t = (t // 3) * 4
    h = [t, t, t]
    if extra == 0:
        h[0] += 1; h[1] += 2; h[2] += 3
    elif extra == 1:
        h[1] += 2; h[2] += 3
    elif extra == 2:
        h[1] += 1; h[2] += 3
    else:
        h[1] += 1; h[2] += 2
    if r == 1:
        h = [h[1], h[0], h[2]]
    elif r == 2:
        h = [h[2], h[0], h[1]]
    return h, t


def decode_pon(m):
    h, _t = _triple(m, (m & 0x0060) >> 5)
    return h


def decode_kakan(m):
    extra = (m & 0x0060) >> 5
    h, t = _triple(m, extra)
    return [t + extra] + h


def decode_kan(m):
    hai0 = (m & 0xFF00) >> 8
    kui = m & 0x3
    if not kui:
        hai0 = (hai0 & ~3) + 3
    t = (hai0 // 4) * 4
    h = [t, t, t]
    rem = hai0 % 4
    if rem == 0:
        h[0] += 1; h[1] += 2; h[2] += 3
    elif rem == 1:
        h[1] += 2; h[2] += 3
    elif rem == 2:
        h[1] += 1; h[2] += 3
    else:
        h[1] += 1; h[2] += 2
    return [hai0] + h


def parse_call(attr):
    caller = int(attr["who"], 10)
    m = int(attr["m"], 10)
    rel = m & 3
    ev = {"type": "call", "player": caller, "callee": (caller + rel) % 4, "rel": rel, "m": m}
    if m & (1 << 2):
        ev["callType"] = "chi"; ev["tiles"] = decode_chi(m)
    elif m & (1 << 3):
        ev["callType"] = "pon"; ev["tiles"] = decode_pon(m)
    elif m & (1 << 4):
        ev["callType"] = "kakan"; ev["tiles"] = decode_kakan(m)
    elif m & (1 << 5):
        ev["callType"] = "nuki"; ev["tiles"] = [m >> 8]
    else:
        ev["callType"] = "daiminkan" if rel else "ankan"
        ev["tiles"] = decode_kan(m)
    return ev


# ------------------------------------------------------------------ 具名标签
def parse_go(attr):
    t = int(attr["type"], 10)
    return {
        "red": ((t & 2) >> 1) == 0, "kui": ((t & 4) >> 2) == 0, "tonnan": ((t & 8) >> 3) == 1,
        "sanma": ((t & 16) >> 4) == 1, "soku": ((t & 64) >> 6) == 1, "type": t,
        "lobby": None if attr.get("lobby") is None else int(attr["lobby"], 10),
    }


def parse_un(attr):
    names = []
    for i in range(4):
        names.append("P%d" % i if attr.get("n%d" % i) is None else _unq(attr["n%d" % i]))
    return {"names": names, "dan": ints(attr.get("dan")), "rate": floats(attr.get("rate")),
            "sex": attr["sx"].split(",") if attr.get("sx") else []}


def parse_init(attr):
    seed = ints(attr["seed"])
    return {
        "round": seed[0], "combo": seed[1], "kyotaku": seed[2],
        "dices": [seed[3], seed[4]], "dora": seed[5],
        "scores": [x * 100 for x in ints(attr.get("ten"))],
        "oya": int(attr["oya"], 10),
        "hands": [ints(attr.get("hai%d" % i, "")) for i in range(4)],
    }


def parse_reach(attr):
    ev = {"type": "reach", "player": int(attr["who"], 10), "step": int(attr["step"], 10)}
    if attr.get("ten"):
        ev["scores"] = [x * 100 for x in ints(attr["ten"])]
    return ev


def parse_agari(attr):
    before, gain = score_pairs(ints(attr.get("sc")))
    return {
        "type": "agari", "winner": int(attr["who"], 10), "fromWho": int(attr["fromWho"], 10),
        "hand": ints(attr.get("hai")), "machi": ints(attr.get("machi")),
        "dora": ints(attr.get("doraHai")), "ura": ints(attr.get("doraHaiUra")),
        "yaku": nest_pairs(ints(attr.get("yaku"))), "yakuman": ints(attr.get("yakuman")),
        "ten": ints(attr.get("ten")), "ba": ints(attr.get("ba")),
        "before": before, "gain": gain,
        "owari": floats(attr["owari"]) if attr.get("owari") else None,
    }


REASON_NAME = {"yao9": "九種九牌", "kaze4": "四風連打", "reach4": "四家立直",
               "rck4": "四槓散了", "nm": "流局満貫", "tripleRon": "三家和了"}


def parse_ryuukyoku(attr):
    before, gain = score_pairs(ints(attr.get("sc")))
    return {
        "type": "ryuukyoku", "reason": attr.get("type", "") or "",
        "who": None if attr.get("who") in (None, "") else int(attr["who"], 10),
        "hands": [ints(attr["hai%d" % i]) if attr.get("hai%d" % i) else None for i in range(4)],
        "ba": ints(attr.get("ba")), "before": before, "gain": gain,
        "owari": floats(attr["owari"]) if attr.get("owari") else None,
    }


# ------------------------------------------------------------------ 主入口
def parse(text):
    """解析 mjlog 文本 -> {"meta": {...}, "rounds": [{"init":..., "events":[...]}]}"""
    nodes = tokenize(text)
    meta = {"names": [], "dan": [], "rate": [], "sex": [], "config": None, "oya": 0}
    rounds, cur = [], None
    for nd in nodes:
        tag, attr = nd["tag"], nd["attr"]
        if tag == "GO":
            meta["config"] = parse_go(attr); continue
        if tag == "UN":
            if len(attr) > 1:
                u = parse_un(attr)
                meta["names"] = u["names"]; meta["dan"] = u["dan"]
                meta["rate"] = u["rate"]; meta["sex"] = u["sex"]
            continue
        if tag == "TAIKYOKU":
            meta["oya"] = int(attr["oya"], 10); continue
        if tag == "SHUFFLE":
            continue
        if tag == "INIT":
            cur = {"init": parse_init(attr), "events": []}
            rounds.append(cur); continue
        if cur is None:
            continue
        if tag == "N":
            cur["events"].append(parse_call(attr)); continue
        if tag == "REACH":
            cur["events"].append(parse_reach(attr)); continue
        if tag == "DORA":
            cur["events"].append({"type": "dora", "tile": int(attr["hai"], 10)}); continue
        if tag == "AGARI":
            cur["events"].append(parse_agari(attr)); continue
        if tag == "RYUUKYOKU":
            cur["events"].append(parse_ryuukyoku(attr)); continue
        if len(tag) < 2:
            continue
        c = ord(tag[0])
        if 84 <= c <= 87:
            cur["events"].append({"type": "draw", "player": c - 84, "tile": int(tag[1:], 10)}); continue
        if 68 <= c <= 71:
            cur["events"].append({"type": "discard", "player": c - 68, "tile": int(tag[1:], 10)}); continue
    return {"meta": meta, "rounds": rounds}


def game_from_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    game = parse(text)
    game["path"] = os.path.abspath(path)
    game["log_id"] = log_id_of(path)
    return game


def log_id_of(path):
    """牌谱文件名 -> 牌谱特征码（log id）。"""
    return os.path.splitext(os.path.basename(path))[0]


def paipu_url(log_id):
    return "http://tenhou.net/0/?log=%s&tw=0" % log_id


def round_label(rnd):
    """局序号(0 起) -> (场风, 局数1起)。0=東一局,4=南一局,8=西一局,12=北一局。"""
    return DIRS[(rnd // 4) % 4], rnd % 4 + 1


def joukyoku_label(rnd):
    """局序号 -> 中文局况，如 5 -> '南二局'。"""
    b, k = round_label(rnd)
    return "%s%s局" % (b, NUM_KANJI[k - 1])