# -*- coding: utf-8 -*-
"""牌谱判重与 AI 分析合并（用户 m00001）。

同一场实际对局可能来自天凤、NAGA、Mortal，文件后缀、特征码、AI 模型都不同：
  * 天凤 .tenhou / 旧 .xml / .mjlog
  * NAGA .naga / 旧 .json.gz / .json
  * Mortal .mortal-a / -b / -c / 旧 .mortal

本模块用「牌局进程」的规范化 sha256 判重：只看每局的配牌、宝牌、座次、分数与
draw / discard / call / reach / dora / agari / ryuukyoku 事件，忽略来源相关的
dices / m / yaku / ten / before / 手牌摊牌口径 / 立直 step2 等。命中后把各份报告
的模型维度按规范模型名合并，写成 ``[mix]`` 前缀的 JSON 容器，并删除原来的文件。

容器格式（紧凑 JSON，后缀沿用最早文件的源后缀）::

    {"mjscore_mix": 1, "created": 175..., "game": {meta, rounds, naga}, "sources": [...]}

``sources`` 只记来源元数据（文件名 / 种类 / report_id / 模型 / 指纹 / 时间 / 大小），
不嵌原始字节，避免四份 NAGA 合并后超过前端 32MB 的文本上限。``game`` 本身与
``cli.game_from_file`` 的输出同构；加载时把 path / log_id 改成 mix 文件自己的，
因此后端打点、前端回放、数据库特征码都以 mix 文件为准。
"""

import copy
import hashlib
import json
import os
import threading
import time

from . import mjlog, paths

MIX_MARKER = "mjscore_mix"
MIX_VERSION = 1
MIX_PREFIX = paths.MIX_PREFIX

# 模型维字段：值都是「每模型一项」的 list。合并时按 source model index -> union index 填槽。
_MODEL_LIST_FIELDS = (
    "dahai_pred", "pred_dahai", "reach", "kan", "dahai_split", "kyushu",
    "ankan_pai", "kakan_pai",
)
# 模型维字段：外层是座位，内层是「每模型一项」的 list。
_MODEL_MAP_FIELDS = ("huro", "hora")

_LOCK = threading.RLock()
_CACHE = {}
_CACHE_LOCK = threading.Lock()


class MixError(ValueError):
    """牌谱无法判重 / 合并时抛出。"""


# ---------------------------------------------------------------------------
# 容器识别 / 读取
# ---------------------------------------------------------------------------
def is_mix(obj):
    """判断一个已解析的 JSON 对象是不是 mix 容器。"""
    return (isinstance(obj, dict) and obj.get(MIX_MARKER) in (1, "1", True)
            and isinstance(obj.get("game"), dict))


def _looks_like_mix_head(head):
    """只看文件头（给 is_mix_file 用，不解析整个大 JSON）。"""
    if not isinstance(head, bytes):
        return False
    s = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    return s.startswith(b"{") and (b'"%s"' % MIX_MARKER.encode("ascii")) in head[:4096]


def is_mix_file(path):
    """按内容判断本地文件是否 mix 容器（不看文件名，``[mix]`` 只是命名约定）。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return _looks_like_mix_head(head)


def looks_like_mix(raw):
    """判断原始字节 / 文本是否是 mix 容器（服务端上传时用）。"""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
    else:
        text = str(raw or "")
    text = text.lstrip("\ufeff \t\r\n")
    if not text.startswith("{"):
        return False
    try:
        return is_mix(json.loads(text))
    except (ValueError, TypeError):
        return False


def is_mix_name(name):
    """文件名是否已有 ``[mix]`` 前缀（大小写不敏感，避免重复加）。"""
    return os.path.basename(str(name or "")).lower().startswith(MIX_PREFIX.lower())


def mix_name_for(name):
    """给最早的文件名加上 ``[mix]`` 前缀（已有则不重复加）。"""
    base = os.path.basename(str(name or ""))
    return base if is_mix_name(base) else MIX_PREFIX + base


def _load_container(path):
    with open(path, "r", encoding="utf-8-sig", errors="strict") as fh:
        data = json.load(fh)
    if not is_mix(data):
        raise MixError("不是 mix 牌谱：%s" % path)
    return data


def _adopt_game(game, path=None):
    """加载 mix 时把 path / log_id 换成 mix 文件自己的，保证数据库身份与文件一致。"""
    if not isinstance(game, dict):
        raise MixError("mix 容器里的 game 不是对象")
    if path:
        p = os.path.abspath(path)
        stem = os.path.splitext(os.path.basename(p))[0]
        game["path"] = p
        game["log_id"] = stem
        meta = game.setdefault("meta", {})
        meta["log_id"] = stem
        meta["path"] = p
    return game


def game_from_bytes(raw, name=None):
    """把 mix 容器的原始字节转成 game dict（服务端 /api/naga-convert 用）。"""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        text = str(raw or "")
    data = json.loads(text)
    if not is_mix(data):
        raise MixError("不是 mix 牌谱")
    game = copy.deepcopy(data["game"])
    if name:
        return _adopt_game(game, name)
    return game


def sources_of_file(path):
    """读取 mix 容器的来源元数据；不是 mix 或读取失败时返回 []（下载判重用）。"""
    try:
        data = _load_container(path)
    except (OSError, ValueError, TypeError):
        return []
    return list(data.get("sources") or [])


def game_from_file(path):
    """读取 mix 文件 -> game dict（与 cli.game_from_file 同构）。"""
    data = _load_container(path)
    return _adopt_game(copy.deepcopy(data["game"]), path)


# ---------------------------------------------------------------------------
# 规范化指纹
# ---------------------------------------------------------------------------
def _tile(value):
    """牌 id -> 跨来源统一的牌名；红 5 -> 0m/0p/0s（mjlog.tile_name 的口径）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        # 原始 NAGA / mjai 牌名也可能直接传进来：5mr / 5pr / 5sr -> 0m / 0p / 0s
        if len(s) == 3 and s[0] == "5" and s[2] == "r":
            return "0" + s[1]
        return s
    try:
        return mjlog.tile_name(int(value))
    except (TypeError, ValueError, IndexError):
        return str(value)


def _tiles(values):
    """牌张列表 -> 排序后的牌名（保留重复，用于手牌 / 副露）。"""
    return tuple(sorted(_tile(v) for v in (values or [])))


def _tile_set(values):
    """牌张列表 -> 排序去重后的牌名（用于 call：天凤加杠 4 张 = NAGA/Mortal 1 张）。"""
    return tuple(sorted(set(_tile(v) for v in (values or []))))


def _canon_round(rnd):
    rnd = rnd or {}
    init = rnd.get("init") or {}
    hands = init.get("hands") or []
    hand_canon = []
    for seat in range(4):
        h = hands[seat] if seat < len(hands) else []
        hand_canon.append(_tiles(h))

    events = []
    reach_done = set()
    end_buf = []

    def flush_end():
        if end_buf:
            events.extend(sorted(end_buf))
            del end_buf[:]

    for ev in rnd.get("events") or []:
        typ = ev.get("type")
        if typ in ("draw", "discard"):
            flush_end()
            events.append((typ, ev.get("player"), _tile(ev.get("tile"))))
        elif typ == "call":
            flush_end()
            ct = ev.get("callType")
            item = ["call", ev.get("player"), ct, _tile_set(ev.get("tiles") or [])]
            # 吃 / 碰 / 大明杠的放铳者参与判重；暗杠 / 加杠的 callee 各来源口径不同，忽略。
            if ct in ("chi", "pon", "daiminkan"):
                item.append(ev.get("callee"))
            events.append(tuple(item))
        elif typ == "reach":
            flush_end()
            player = ev.get("player")
            # 只记第一次立直宣言；某些来源没有 reach_accepted，step2 一律忽略。
            if player not in reach_done:
                reach_done.add(player)
                events.append(("reach", player))
        elif typ == "dora":
            flush_end()
            events.append(("dora", _tile(ev.get("tile"))))
        elif typ == "agari":
            # 和牌手牌 / 待牌 / 宝牌 / 里宝 / 役 / 点数 / 收支各来源口径不同，只留胜负关系。
            end_buf.append(("agari", ev.get("winner"), ev.get("fromWho")))
        elif typ == "ryuukyoku":
            end_buf.append(("ryuukyoku",))
        else:
            flush_end()
            events.append(("?", typ, ev.get("player"), _tile(ev.get("tile"))))
    flush_end()

    return [
        "round",
        init.get("round"), init.get("combo"), init.get("kyotaku"),
        _tile(init.get("dora")), list(init.get("scores") or []), init.get("oya"),
        hand_canon, events,
    ]


def canonical(game):
    """把 game dict 转成可哈希的规范化结构（调试 / 测试用）。

    只取牌局进程：每局 init + 事件。显式不使用 meta.names、naga.player_id、
    meta.viewer_seat、report_id、文件特征码——分析软件可以隐去对局者 ID，
    这些字段不属于牌局进程本身（用户 m00606）。
    """
    return [_canon_round(r) for r in (game.get("rounds") or [])]


def fingerprint(game):
    """牌局进程 hash：同一场实际对局（无论来源 / 视角 / 模型 / 是否匿名）应得到同一个值。"""
    text = json.dumps(canonical(game), ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 文件信息 / 缓存
# ---------------------------------------------------------------------------
def _models_of(naga):
    """取报告里的模型列表（兼容 models 缺失、types 只有字典的旧报告）。"""
    naga = naga or {}
    models = naga.get("models")
    if isinstance(models, list) and models:
        return [m for m in models if isinstance(m, dict)]
    out = []
    types = naga.get("types")
    if isinstance(types, dict):
        for key, raw in types.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            name = raw
            try:
                from . import ai_models
                name = ai_models.normalize(raw)
            except Exception:
                pass
            out.append({"index": idx, "raw": raw, "name": name})
    return out


def _model_name(model):
    return str((model or {}).get("name") or (model or {}).get("raw") or "").strip()


def _model_index(model, pos):
    try:
        return int(model.get("index", pos))
    except (TypeError, ValueError):
        return pos


def _info_from_game(path, game, st=None):
    p = os.path.abspath(path)
    st = st or os.stat(p)
    naga = game.get("naga") or {}
    models = [m for m in (_models_of(naga) or []) if _model_name(m)]
    return {
        "path": p,
        "mtime": st.st_mtime,
        "mtime_ns": st.st_mtime_ns,
        "size": st.st_size,
        "fingerprint": fingerprint(game),
        "rounds": len(game.get("rounds") or []),
        "has_ai": bool(naga.get("rounds")),
        "models": [_model_name(m) for m in models],
        "kind": (naga.get("kind") or ("tenhou" if not naga else "ai")),
        "report_id": naga.get("report_id") or game.get("log_id"),
        "player_id": naga.get("player_id"),
        "viewer_seat": (game.get("meta") or {}).get("viewer_seat"),
    }


def _cache_get(path):
    p = os.path.abspath(path)
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    with _CACHE_LOCK:
        hit = _CACHE.get(p)
    if hit and hit[0] == key:
        return hit[1]
    return None


def _cache_put(path, info):
    p = os.path.abspath(path)
    with _CACHE_LOCK:
        _CACHE[p] = ((info["mtime_ns"], info["size"]), info)


def _load_game(path):
    """按内容 / 后缀加载任意牌谱；mix 走本模块，其余复用 cli 的分派（惰性 import 避免循环）。"""
    if is_mix_file(path):
        return game_from_file(path)
    from . import cli
    return cli.game_from_file(path)


def _file_info(path):
    cached = _cache_get(path)
    if cached is not None:
        return cached
    game = _load_game(path)
    st = os.stat(path)
    info = _info_from_game(path, game, st)
    _cache_put(path, info)
    return info


def _source_meta(path, info=None):
    p = os.path.abspath(path)
    info = info or _file_info(p)
    st = os.stat(p)
    return {
        "name": os.path.basename(p),
        "kind": ("mix" if is_mix_file(p) else info.get("kind")),
        "report_id": info.get("report_id"),
        "player_id": info.get("player_id"),
        "viewer_seat": info.get("viewer_seat"),
        "mtime": round(float(st.st_mtime), 3),
        "size": int(st.st_size),
        "fingerprint": info.get("fingerprint"),
        "models": list(info.get("models") or []),
    }


def _all_suffixes():
    return tuple(paths.TENHOU_SUFFIXES) + tuple(paths.NAGA_SUFFIXES) + tuple(paths.MORTAL_SUFFIXES)


def _is_paipu_name(name):
    low = name.lower()
    return any(low.endswith(sfx) for sfx in _all_suffixes())


def scan_root_for(path):
    """默认扫描根：data/paipu（路径在它下面时）否则文件所在目录。"""
    p = os.path.abspath(path)
    root = os.path.abspath(paths.paipu_root())
    try:
        if os.path.commonpath([p, root]) == root:
            return root
    except ValueError:
        pass
    return os.path.dirname(p)


def _iter_paipu_files(root):
    seen = set()
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(names):
            if not _is_paipu_name(name):
                continue
            p = os.path.abspath(os.path.join(dirpath, name))
            if p not in seen:
                seen.add(p)
                yield p


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def _entries(paths):
    out = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.isfile(p):
            continue
        game = _load_game(p)
        st = os.stat(p)
        info = _info_from_game(p, game, st)
        _cache_put(p, info)
        if is_mix_file(p):
            sources = _load_container(p).get("sources") or []
        else:
            sources = []
        out.append({"path": p, "game": game, "info": info, "sources": sources,
                    "is_mix": is_mix_file(p)})
    return out


def _base_key(entry):
    # 已有 mix 优先作为 base（保留它的 [mix] 名字与已合并模型），否则 mtime 最早者。
    return (0 if entry["is_mix"] else 1, entry["info"]["mtime"], entry["path"])


def _add_source(sources, seen, src):
    if not isinstance(src, dict):
        return
    key = (src.get("name"), src.get("fingerprint"), src.get("report_id"))
    if key in seen:
        return
    seen.add(key)
    sources.append(src)


def _expand_frame(frame, count):
    for field in _MODEL_LIST_FIELDS:
        v = frame.get(field)
        if isinstance(v, list):
            frame[field] = list(v) + [None] * max(0, count - len(v))
    for field in _MODEL_MAP_FIELDS:
        v = frame.get(field)
        if isinstance(v, dict):
            for seat, arr in list(v.items()):
                if isinstance(arr, list):
                    v[str(seat)] = list(arr) + [None] * max(0, count - len(arr))


def _slot_empty(value):
    return value is None or value == []


def _merge_frame(out, src, mapping, count):
    for field in _MODEL_LIST_FIELDS:
        vals = src.get(field)
        if not isinstance(vals, list):
            continue
        if not isinstance(out.get(field), list):
            out[field] = [None] * count
        arr = out[field]
        if len(arr) < count:
            arr.extend([None] * (count - len(arr)))
        for si, ui in mapping.items():
            if si < 0 or si >= len(vals) or ui < 0 or ui >= count:
                continue
            val = vals[si]
            if val is None:
                continue
            if _slot_empty(arr[ui]):
                arr[ui] = copy.deepcopy(val)

    for field in _MODEL_MAP_FIELDS:
        vals = src.get(field)
        if not isinstance(vals, dict):
            continue
        outmap = out.get(field)
        if not isinstance(outmap, dict):
            outmap = {}
            out[field] = outmap
        for seat, sarr in vals.items():
            if not isinstance(sarr, list):
                continue
            key = str(seat)
            oarr = outmap.get(key)
            if not isinstance(oarr, list):
                oarr = [None] * count
                outmap[key] = oarr
            if len(oarr) < count:
                oarr.extend([None] * (count - len(oarr)))
            for si, ui in mapping.items():
                if si < 0 or si >= len(sarr) or ui < 0 or ui >= count:
                    continue
                val = sarr[si]
                if val is not None and _slot_empty(oarr[ui]):
                    oarr[ui] = copy.deepcopy(val)

    # 非模型字段：base 优先；base 缺 / 为 None 时用其它来源补。
    for key, val in src.items():
        if key in _MODEL_LIST_FIELDS or key in _MODEL_MAP_FIELDS:
            continue
        if key not in out or out[key] is None:
            out[key] = copy.deepcopy(val)


def _merge_entries(entries, out_path=None, delete=True):
    entries = [e for e in entries if e and e.get("game")]
    if not entries:
        raise MixError("没有可合并的牌谱")
    fps = {e["info"]["fingerprint"] for e in entries}
    if len(fps) != 1:
        raise MixError("这些牌谱不是同一场对局（牌局进程 hash 不同）")
    fp = next(iter(fps))

    # 目标文件已存在且不是本次输入时：若它也是同一局的 mix，就并进来（手动合并可重复执行）。
    input_paths = {e["path"] for e in entries}
    if out_path:
        out_path = os.path.abspath(out_path)
        if os.path.exists(out_path) and out_path not in input_paths:
            try:
                extra = _entries([out_path])
            except Exception as exc:
                raise MixError("目标文件已存在且无法读取：%s（%s）" % (out_path, exc))
            if extra and extra[0]["info"]["fingerprint"] == fp:
                entries.extend(extra)
                input_paths.add(out_path)
            else:
                raise MixError("目标文件已存在且不是同一场对局：%s" % out_path)

    entries.sort(key=_base_key)
    base = entries[0]
    ai_entries = [e for e in entries if e["info"]["has_ai"] and (e["game"].get("naga") or {}).get("rounds")]
    if not ai_entries:
        return {"ok": True, "merged": False, "reason": "no_ai", "path": base["path"],
                "fingerprint": fp, "sources": [e["path"] for e in entries]}

    base_ai = base if base in ai_entries else ai_entries[0]
    base_game = base["game"]
    base_ai_naga = base_ai["game"].get("naga") or {}
    base_frames = base_ai_naga.get("rounds") or []
    rounds = base_game.get("rounds") or []
    if len(base_frames) != len(rounds):
        raise MixError("AI 帧数与对局局数不一致：frames=%d rounds=%d" % (len(base_frames), len(rounds)))

    # 模型 union：base（或最早 AI 源）在前；按规范名去重。
    union = []
    by_name = {}
    for entry in [base_ai] + [e for e in entries if e is not base_ai]:
        for pos, model in enumerate(_models_of(entry["game"].get("naga") or {})):
            name = _model_name(model)
            if not name or name in by_name:
                continue
            m = copy.deepcopy(model)
            m["index"] = len(union)
            union.append(m)
            by_name[name] = m["index"]
    if not union:
        return {"ok": True, "merged": False, "reason": "no_models", "path": base["path"],
                "fingerprint": fp, "sources": [e["path"] for e in entries]}

    # source model index -> union index
    maps = {}
    for entry in ai_entries:
        smap = {}
        for pos, model in enumerate(_models_of(entry["game"].get("naga") or {})):
            name = _model_name(model)
            if name in by_name:
                smap[_model_index(model, pos)] = by_name[name]
        maps[entry["path"]] = smap

    out_game = copy.deepcopy(base_game)
    out_naga = copy.deepcopy(base_ai_naga)
    out_naga["models"] = union
    out_naga["types"] = {str(i): (m.get("raw") or m.get("name")) for i, m in enumerate(union)}
    # base AI 源选中的模型名 -> union 位置
    sel_name = ""
    sel_idx = base_ai_naga.get("model_index")
    for pos, model in enumerate(_models_of(base_ai_naga)):
        if _model_index(model, pos) == sel_idx:
            sel_name = _model_name(model)
            break
    if sel_name not in by_name:
        sel_name = _model_name(union[0])
    out_naga["model_index"] = by_name.get(sel_name, 0)
    out_naga["mix"] = True
    out_naga["mix_fingerprint"] = fp

    count = len(union)
    out_rounds = []
    for ri, base_round_frames in enumerate(base_frames):
        frames = []
        for fi in range(len(base_round_frames)):
            src_frame = base_round_frames[fi]
            # 先只保留非模型字段，模型字段由下面所有 AI 源按 union 槽位统一填。
            # 不能先深拷贝 base 的模型数组再合并 base：base 的 index 顺序与 union 位置
            # 不一致时会在旧槽位留下重复数据。
            frame = dict((key, copy.deepcopy(val)) for key, val in src_frame.items()
                         if key not in _MODEL_LIST_FIELDS and key not in _MODEL_MAP_FIELDS)
            for entry in ai_entries:
                src_rounds = (entry["game"].get("naga") or {}).get("rounds") or []
                if ri >= len(src_rounds) or fi >= len(src_rounds[ri]):
                    continue
                _merge_frame(frame, src_rounds[ri][fi], maps[entry["path"]], count)
            frames.append(frame)
        out_rounds.append(frames)
    out_naga["rounds"] = out_rounds
    out_game["naga"] = out_naga

    meta = out_game.setdefault("meta", {})
    meta["mix"] = True
    meta["mix_fingerprint"] = fp
    meta["naga"] = True
    if any((e["game"].get("naga") or {}).get("kind") == "mortal"
           or e["info"].get("kind") == "mortal" for e in entries):
        meta["mortal"] = True
    if meta.get("viewer_seat") is None:
        # 座位 0 是合法值，不能用 or 兜底（否则 0 会被 player_id 覆盖成别家）。
        seat = (base_ai["game"].get("meta") or {}).get("viewer_seat")
        if seat is None:
            seat = base_ai_naga.get("player_id")
        meta["viewer_seat"] = seat
    if not meta.get("names"):
        meta["names"] = (base_ai["game"].get("meta") or {}).get("names")
    out_game["mix"] = {"fingerprint": fp, "sources": []}
    out_game.pop("path", None)

    # 目标名 / 目录
    base_path = base["path"]
    if out_path is None:
        out_path = os.path.join(os.path.dirname(base_path), mix_name_for(os.path.basename(base_path)))
    out_path = os.path.abspath(out_path)
    if os.path.exists(out_path) and out_path not in input_paths:
        raise MixError("目标文件已存在且不是本次输入，拒绝覆盖：%s" % out_path)
    out_stem = os.path.splitext(os.path.basename(out_path))[0]
    out_game["log_id"] = out_stem
    meta["log_id"] = out_stem
    meta.pop("path", None)

    # 来源元数据：已有 mix 的 sources 原样保留；新文件追加。
    sources = []
    seen_src = set()
    for entry in entries:
        if entry["is_mix"] and entry["sources"]:
            for src in entry["sources"]:
                _add_source(sources, seen_src, src)
        else:
            _add_source(sources, seen_src, _source_meta(entry["path"], entry["info"]))

    # 来源名用原始文件名（已有 mix 的 sources 元数据会保留最初的名字），
    # 不把 [mix] 容器名重复列进来。
    source_names = [os.path.basename(str(src.get("name") or "")) for src in sources
                    if isinstance(src, dict)]
    out_naga["mix_sources"] = source_names
    out_game["mix"]["sources"] = source_names

    container = {
        "mjscore_mix": MIX_VERSION,
        "created": int(time.time()),
        "game": out_game,
        "sources": sources,
    }
    _write_container(out_path, container)

    removed = []
    if delete:
        for entry in entries:
            p = entry["path"]
            if os.path.abspath(p) == out_path:
                continue
            try:
                os.remove(p)
                removed.append(p)
            except FileNotFoundError:
                pass
            except OSError:
                # 删除失败不破坏已经写好的 mix；调用方可在结果里看到 removed 不完整。
                pass
    return {
        "ok": True,
        "merged": True,
        "path": out_path,
        "removed": removed,
        "sources": sources,
        "models": [m.get("name") for m in union],
        "fingerprint": fp,
        "bytes": os.path.getsize(out_path),
    }


def _write_container(out_path, container):
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    tmp = "%s.tmp-%d" % (out_path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(container, fh, ensure_ascii=False, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def merge_paths(paths, out_path=None, delete=True):
    """手动合并一组同局牌谱（CLI ``--mix`` 用）。"""
    with _LOCK:
        uniq = []
        seen = set()
        for p in paths or []:
            p = os.path.abspath(p)
            if p not in seen and os.path.isfile(p):
                seen.add(p)
                uniq.append(p)
        if not uniq:
            raise MixError("没有可合并的牌谱文件")
        entries = _entries(uniq)
        if len(entries) < 2:
            return {"ok": True, "merged": False, "reason": "single", "path": entries[0]["path"],
                    "fingerprint": entries[0]["info"]["fingerprint"]}
        return _merge_entries(entries, out_path=out_path, delete=delete)


def scan_and_merge(path, root=None, delete=True):
    """新牌谱落盘后扫描同根目录，命中同一场对局就合并成 ``[mix]`` 文件。

    返回 {ok, merged, path, removed, ...}；没有重复时 merged=False，不删除任何文件。
    扫描范围默认 data/paipu（路径在它下面时）否则文件所在目录。
    """
    with _LOCK:
        p = os.path.abspath(path)
        if not os.path.isfile(p):
            return {"ok": False, "merged": False, "error": "文件不存在：%s" % p}
        try:
            target = _file_info(p)
        except Exception as exc:
            return {"ok": False, "merged": False, "error": "%s: %s" % (type(exc).__name__, exc), "path": p}
        scan_root = os.path.abspath(root) if root else scan_root_for(p)
        candidates = list(_iter_paipu_files(scan_root))
        if p not in candidates:
            candidates.append(p)
        matches = []
        warnings = []
        for fp in candidates:
            try:
                info = _file_info(fp)
            except Exception as exc:
                warnings.append("%s: %s" % (os.path.basename(fp), exc))
                continue
            if info["fingerprint"] == target["fingerprint"]:
                matches.append(fp)
        if len(matches) < 2:
            return {"ok": True, "merged": False, "reason": "unique", "path": p,
                    "fingerprint": target["fingerprint"], "warnings": warnings}
        try:
            infos = [_file_info(m) for m in matches]
        except Exception as exc:
            return {"ok": False, "merged": False, "error": "%s: %s" % (type(exc).__name__, exc),
                    "path": p, "warnings": warnings}
        if not any(i.get("has_ai") for i in infos):
            return {"ok": True, "merged": False, "reason": "no_ai", "path": p,
                    "fingerprint": target["fingerprint"], "matches": matches, "warnings": warnings}
        try:
            entries = _entries(matches)
            res = _merge_entries(entries, out_path=None, delete=delete)
            res["warnings"] = warnings
            return res
        except Exception as exc:
            return {"ok": False, "merged": False, "error": "%s: %s" % (type(exc).__name__, exc),
                    "path": p, "matches": matches, "warnings": warnings}


def fingerprint_file(path):
    """读取一个牌谱并返回它的牌局进程 hash（测试 / 调试用）。"""
    return _file_info(path)["fingerprint"]
