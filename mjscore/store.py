# -*- coding: utf-8 -*-
"""SQLite 打点数据库：建库 / 写库 / 检索 / 导出。

表结构（star schema，压缩维度 = 33 个特征：16 个第一类 + 17 个第二类）：
    meta          库级元信息（schema 版本、软件版本、工具、口径说明、特征注册表）
    feature_def   33 个特征的注册表（key / 中文名 / 类型 / 值域 / 列名）
    source        每个已入库牌谱（特征码 / 原始文件路径 / 局数 / 打点数）
    round         每个已入库的局（局况 / 本场 / 供托 / 起家 / 分数）
    frame         **一行 = 一个打点帧**（kind=draw 非自摸的摸牌帧 / kind=chi|pon 吃碰后等待出牌的帧）：
                  定位列 + 33 个特征列（打点维度）
    frame_full   惰性维度：后续新增特征时按 key 逐列追加，无需改表结构（--full 时写原始数据）
检索：把用户填的特征条件编译成 WHERE 子句（枚举精确匹配 / 整数区间 / 比较），
      全部条件用 AND 组合（readme：「检索满足全部条件的帧」）。
"""

import json
import os
import re
import sqlite3

from . import feats, mjlog
from . import __version__ as APP_VERSION   # 软件本体版本，写进 meta.app_version

SCHEMA_VERSION = 3   # 3：新增 17 个第二类特征列（s_*，第 21 轮）；2 = frame.kind + 巡目按出牌计（第 13 轮）

META_KEYS = ("schema_version", "app_version", "created_at", "updated_at", "tool", "record_count",
             "source_count", "round_count", "full", "noted")

TABLES = [
    """CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS feature_def (
        key TEXT PRIMARY KEY, name TEXT, kind TEXT, col TEXT, values_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS source (
        log_id TEXT PRIMARY KEY, path TEXT, rounds INTEGER, annotations INTEGER,
        tool TEXT, added_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS round (
        log_id TEXT, round_index INTEGER, kyoku INTEGER, honba INTEGER, kyotaku INTEGER,
        oya INTEGER, joukyoku TEXT, scores_json TEXT, events INTEGER,
        PRIMARY KEY (log_id, round_index))""",
    """CREATE TABLE IF NOT EXISTS frame (
        idx INTEGER PRIMARY KEY,
        log_id TEXT NOT NULL, url TEXT, round_index INTEGER NOT NULL, ev_index INTEGER NOT NULL,
        frame_index INTEGER NOT NULL, seat INTEGER NOT NULL, round INTEGER, honba INTEGER,
        kyotaku_raw INTEGER, kyotaku_total INTEGER, score INTEGER, oya INTEGER, dealer INTEGER,
        joukyoku TEXT, wind TEXT, junme INTEGER, rank INTEGER, drawn INTEGER, hand_size INTEGER,
        kind TEXT,
        %s,
        label TEXT, log_path TEXT, tool TEXT, added_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS frame_full (
        frame_idx INTEGER, key TEXT, value TEXT, PRIMARY KEY (frame_idx, key))""",
]


FEATURE_DDL_TYPES = {"int": "INTEGER", "float": "REAL", "enum": "TEXT"}


def _feature_columns_ddl():
    """frame 表的特征列声明（名字、顺序 = feats.FEATURES 注册表顺序；第 21 轮起含 17 个第二类特征）。"""
    return ", ".join("%s %s" % (f["col"], FEATURE_DDL_TYPES.get(f["kind"], "TEXT"))
                     for f in feats.FEATURES)


# 只有 frame 的 DDL 留了 %s 占位（特征列），其余照原样
TABLES = [sql % _feature_columns_ddl() if "%s" in sql else sql for sql in TABLES]

INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS frame_uniq ON frame (log_id, round_index, ev_index, seat)",
    "CREATE INDEX IF NOT EXISTS frame_dims ON frame (f_joukyoku, f_junme, f_kyotaku, f_rank, f_oyako)",
    "CREATE INDEX IF NOT EXISTS frame_flags ON frame (f_riichi_self, f_meld_self, f_meld_self_n)",
    "CREATE INDEX IF NOT EXISTS frame_others ON frame (f_riichi_others_n, f_meld_others_n, f_meld2_others_n, f_meld3_others_n)",
    "CREATE INDEX IF NOT EXISTS frame_oya ON frame (f_oya_riichi, f_oya_meld, f_oya_meld_n)",
]

FRAME_FACT_COLS = ["log_id", "url", "round_index", "ev_index", "frame_index", "seat", "round",
                   "honba", "kyotaku_raw", "kyotaku_total", "score", "oya", "dealer", "joukyoku",
                   "wind", "junme", "rank", "drawn", "hand_size", "kind"]

DOUKOU = ("打点对象：非自摸的摸牌帧（kind=draw）+ 吃/碰之后等待出牌的帧（kind=chi/pon）；加杠/大明杠/暗杠不单独出帧"
          "（杠后的岭上摸牌帧就是 kind=draw）。视角：该家本人。巡目 = 该家本局第 N 次出牌（打牌 +1；暗杠/加杠视为出牌 +1；吃/碰/大明杠不算）+ 1。副露 = 吃/碰/加杠/大明杠/暗杠 的组数"
          "（拔北不计）；供托 = 立直棒×1000 + 本场×300；顺位同分时按自风 東→南→西→北 排先；"
          "该家自己就是亲家时，亲家（他家）三项记 否/否/0。")
FULL_NOTE = ("--full（同时写入原始数据）：勾选时除了 33 个特征值，还把该帧的原始数据"
             "（手牌 / 副露 / 宝牌指示牌 / 分数 / 牌谱路径）写进 frame_full 表 —— "
             "以后新增特征时可以只按这些原始数据重算，不必重新解析 XML；"
             "不勾选时只写 33 个特征值（库更小、写库略快），但后续新增特征只能重新分析全部牌谱。")


# ------------------------------------------------------------------ 连接与建库
def connect(db_path, create=True):
    if create:
        d = os.path.dirname(os.path.abspath(db_path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
    elif not os.path.isfile(os.path.abspath(db_path)):
        # create=False 时不顺手建库：检索/浏览不该凭空产生空库
        raise FileNotFoundError("数据库文件不存在：%s" % os.path.abspath(db_path))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        check_version(conn, db_path)
    except Exception:
        # 校验失败就要把连接关掉：否则 Windows 上这个 sqlite 文件会被一直占着，
        # 之后既删不掉（WinError 32）也覆盖不了。
        conn.close()
        raise
    return conn


def check_version(conn, db_path=""):
    """校验这个库能不能被当前软件使用。

    ① 结构版本（meta.schema_version）必须等于 SCHEMA_VERSION，否则提示重建；
    ② 软件版本（meta.app_version，第 22 轮起）：记录生成该库的软件本体版本。
       有记录就必须与当前 __version__ 一致，否则拒绝使用（格式可能已变）；
       没有记录（v0.1.0 之前生成的库）按兼容处理，返回 False。

    返回 True = 有版本记录且匹配；False = 全新库 / 没有版本记录的库。
    """
    try:
        row = conn.execute("SELECT v FROM meta WHERE k = 'schema_version'").fetchone()
    except sqlite3.Error:
        return False          # 全新库（还没有 meta 表）
    if row is None:
        return False
    ver = int(row["v"])
    if ver != SCHEMA_VERSION:
        raise ValueError(
            "数据库结构版本 %d ≠ 当前 %d（第 13 轮新增 kind 列、巡目改为按出牌计；"
            "第 21 轮新增 17 个第二类特征列 s_*），"
            "请删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（%s）"
            % (ver, SCHEMA_VERSION, os.path.abspath(db_path)))
    row = conn.execute("SELECT v FROM meta WHERE k = 'app_version'").fetchone()
    if row is None or not str(row["v"]).strip():
        return False          # v0.1.0 之前生成的库：没有软件版本记录
    recorded = str(row["v"]).strip()
    if recorded != APP_VERSION:
        raise ValueError(
            "数据库由软件版本 %s 生成，当前软件版本 %s，数据库格式可能不兼容；"
            "请改用原版本软件，或删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（%s）"
            % (recorded, APP_VERSION, os.path.abspath(db_path)))
    return True


def create_schema(conn):
    cur = conn.cursor()
    for sql in TABLES:
        cur.execute(sql)
    for sql in INDEXES:
        cur.execute(sql)
    conn.commit()


def set_meta(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, str(v)))


def get_meta(conn):
    return {r["k"]: r["v"] for r in conn.execute("SELECT k, v FROM meta")}


def app_version_of(conn):
    """该库记录的软件版本（没有记录时返回空串）。"""
    return str(get_meta(conn).get("app_version") or "")


def source_ids(conn):
    """已入库的全部牌谱特征码（扩充数据库时用来跳过重复牌谱）。"""
    return {r["log_id"] for r in conn.execute("SELECT log_id FROM source")}


def totals(conn):
    """库内的总行数（frame / source / round），扩充后重新统计用。"""
    cur = conn.cursor()
    return {"frames": cur.execute("SELECT COUNT(*) c FROM frame").fetchone()["c"],
            "sources": cur.execute("SELECT COUNT(*) c FROM source").fetchone()["c"],
            "rounds": cur.execute("SELECT COUNT(*) c FROM round").fetchone()["c"]}


def write_feature_defs(conn):
    for f in feats.FEATURES:
        conn.execute("INSERT OR REPLACE INTO feature_def (key, name, kind, col, values_json) VALUES (?,?,?,?,?)",
                     (f["key"], f["name"], f["kind"], f["col"], json.dumps(f.get("values"), ensure_ascii=False)))
    conn.commit()


def open_db(db_path):
    conn = connect(db_path)
    create_schema(conn)
    return conn


# ------------------------------------------------------------------ 写库
def _json(v):
    return json.dumps(v, ensure_ascii=False)


def insert_rounds(conn, game, tool):
    log_id = game["log_id"]
    for ri, rnd in enumerate(game["rounds"]):
        init = rnd["init"]
        conn.execute("INSERT OR REPLACE INTO round (log_id, round_index, kyoku, honba, kyotaku, oya,"
                     " joukyoku, scores_json, events) VALUES (?,?,?,?,?,?,?,?,?)",
                     (log_id, ri, init["round"], init["combo"], init["kyotaku"], init["oya"],
                      mjlog.joukyoku_label(init["round"]), _json(init["scores"]), len(rnd["events"])))


FRAME_INSERT = ("INSERT OR REPLACE INTO frame ("
                + ", ".join(FRAME_FACT_COLS + [f["col"] for f in feats.FEATURES]
                            + ["label", "log_path", "tool", "added_at"])
                + ") VALUES (" + ", ".join(["?"] * (len(FRAME_FACT_COLS) + len(feats.FEATURES) + 4)) + ")")


def insert_records(conn, records, tool="", log_path="", added_at="", full=False):
    n = 0
    for rec in records:
        vals = [rec.get(c) for c in FRAME_FACT_COLS]
        # 第二类特征（第 21 轮）与第一类一起写入；老 fixture 缺列时记 NULL 而不是 KeyError
        vals += [rec["feats"].get(f["key"]) for f in feats.FEATURES]
        vals += [feats.row_label(rec), log_path or rec.get("path", ""), tool, added_at]
        cur = conn.execute(FRAME_INSERT, vals)
        idx = cur.lastrowid
        n += 1
        if full:
            for key, value in (("tiles", rec.get("tiles")), ("melds", rec.get("melds")),
                               ("dora", rec.get("dora")), ("scores", rec.get("scores")),
                               ("names", rec.get("names"))):
                if value is not None:
                    conn.execute("INSERT OR REPLACE INTO frame_full (frame_idx, key, value) VALUES (?,?,?)",
                                 (idx, key, _json(value)))
    return n


def insert_source(conn, game, annotations, tool, added_at):
    conn.execute("INSERT OR REPLACE INTO source (log_id, path, rounds, annotations, tool, added_at)"
                 " VALUES (?,?,?,?,?,?)",
                 (game["log_id"], game.get("path", ""), len(game["rounds"]), annotations, tool, added_at))


def prune_frame_full(conn):
    """清掉 frame_full 里指向已不存在帧的原始数据。

    frame 的唯一键是 (log_id, round_index, ev_index, seat)：重新分析同一个牌谱时
    `INSERT OR REPLACE` 会先删旧行、再插入**新的 idx**；frame_full 是按 frame_idx 存的，
    不清就会留下永远取不到的孤儿行（--full 重分析 N 次就多 N 份垃圾，实测 1 次多 13930 行）。
    返回删除的行数。
    """
    cur = conn.execute("DELETE FROM frame_full WHERE frame_idx NOT IN (SELECT idx FROM frame)")
    return cur.rowcount


# ------------------------------------------------------------------ 检索
NUM_RE = re.compile(r"^\s*(-?\d+)\s*$")
RANGE_RE = re.compile(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$")
CMP_RE = re.compile(r"^\s*(<=|>=|<|>)\s*(-?\d+)\s*$")
# 实数（kind=float 的 12 个期望特征）：0 / 0.5 / -1.25 / .5 / 3.
FLOAT_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
FRANGE_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*-\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
FCMP_RE = re.compile(r"^\s*(<=|>=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")


def parse_cond(feature, expr):
    """把用户的检索条件文本编译成 (sql, params)。

    支持：`3`（精确）、`1,2,3`（多值）、`1-3`（区间）、`>=3` / `<=2` / `>1` / `<4`（比较）；
    实数特征（kind=float）同样支持 `0.5` / `0,1.5` / `0-1.5` / `>=2.5`。
    """
    if expr is None or str(expr).strip() == "":
        raise ValueError("「%s」的条件没有填写" % feature["name"])
    text = str(expr).strip()
    col = feature["col"]
    if feature["kind"] == "int":
        m = NUM_RE.match(text)
        if m:
            return "%s = ?" % col, [int(m.group(1))]
        m = RANGE_RE.match(text)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return "%s BETWEEN ? AND ?" % col, [lo, hi]
        m = CMP_RE.match(text)
        if m:
            return "%s %s ?" % (col, m.group(1)), [int(m.group(2))]
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if parts and all(NUM_RE.match(p) for p in parts):
            return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), [int(p) for p in parts]
        raise ValueError("「%s」的可接受条件：整数 / 区间(1-3) / 列表(1,2,3) / 比较(>=3)，收到「%s」"
                         % (feature["name"], text))
    if feature["kind"] == "float":
        m = FLOAT_RE.match(text)
        if m:
            return "%s = ?" % col, [float(m.group(1))]
        m = FRANGE_RE.match(text)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return "%s BETWEEN ? AND ?" % col, [lo, hi]
        m = FCMP_RE.match(text)
        if m:
            return "%s %s ?" % (col, m.group(1)), [float(m.group(2))]
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if parts and all(FLOAT_RE.match(p) for p in parts):
            return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), [float(p) for p in parts]
        raise ValueError("「%s」的可接受条件：实数 / 区间(0-1.5) / 列表(0,1,2.5) / 比较(>=3)，收到「%s」"
                         % (feature["name"], text))
    # 枚举：精确或多值
    allowed = feature.get("values") or []
    parts = [p.strip() for p in text.split(",") if p.strip() != ""]
    if not parts:
        raise ValueError("「%s」的条件为空" % feature["name"])
    for p in parts:
        if allowed and p not in allowed:
            raise ValueError("「%s」不接受「%s」，可选值：%s"
                             % (feature["name"], p, " / ".join(allowed)))
    if len(parts) == 1:
        return "%s = ?" % col, [parts[0]]
    return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), parts


RESULT_COLS = ("idx", "log_id", "url", "round_index", "ev_index", "frame_index", "seat", "joukyoku",
               "honba", "wind", "junme", "score", "rank", "kyotaku_total", "kind", "label", "log_path")


def compile_query(conds):
    """conds = [{'key': 'kyotaku', 'expr': '1000'}, ...] -> (where_sql, params, 用到的特征)"""
    if not conds:
        raise ValueError("请至少添加一条牌谱特征条件")
    clauses, params, used = [], [], []
    for c in conds:
        key = c.get("key")
        feature = feats.BY_KEY.get(key)
        if feature is None:
            raise ValueError("未知的牌谱特征：%s" % key)
        sql, ps = parse_cond(feature, c.get("expr"))
        clauses.append(sql)
        params.extend(ps)
        used.append(feature["name"])
    return " AND ".join(clauses), params, used


def query(conn, conds, limit=200, offset=0, order="log_id, round_index, ev_index, seat"):
    where, params, used = compile_query(conds)
    total = conn.execute("SELECT COUNT(*) c FROM frame WHERE " + where, params).fetchone()["c"]
    rows = conn.execute("SELECT %s FROM frame WHERE %s ORDER BY %s LIMIT ? OFFSET ?"
                        % (", ".join(RESULT_COLS), where, order),
                        params + [limit, offset]).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "used": used,
            "rows": [dict(r) for r in rows]}


def query_detail(conn, idx):
    row = conn.execute("SELECT * FROM frame WHERE idx = ?", (idx,)).fetchone()
    if row is None:
        raise ValueError("没有 idx = %s 的打点行" % idx)
    d = dict(row)
    d["feats"] = {f["key"]: d[f["col"]] for f in feats.FEATURES}
    d["full"] = {r["key"]: json.loads(r["value"])
                 for r in conn.execute("SELECT key, value FROM frame_full WHERE frame_idx = ?", (idx,))}
    return d


def frame_feats(conn, log_id, round_index, frame_index, seat=None):
    """按 (log_id, round_index, frame_index[, seat]) 取一帧的全部 33 个特征值。

    前端「当前帧特征面板」用：Python 的 frame_index = ev_index + 1，
    与 web/js/replay.js buildFrames() 的帧号同口径，所以前端可直接把播放位置传进来。
    库里没有这一帧时返回 None（例如手动播放到的帧不是打点帧）。
    """
    if log_id is None or round_index is None or frame_index is None:
        raise ValueError("需要 log_id / round_index / frame_index")
    sql = "SELECT idx FROM frame WHERE log_id=? AND round_index=? AND frame_index=?"
    params = [str(log_id), int(round_index), int(frame_index)]
    if seat is not None and str(seat) != "":
        sql += " AND seat=?"
        params.append(int(seat))
    sql += " LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return query_detail(conn, int(row["idx"]))


def round_frames(conn, log_id, round_index):
    rows = conn.execute("SELECT idx, ev_index, frame_index, seat, junme, kind, label FROM frame"
                        " WHERE log_id=? AND round_index=? ORDER BY ev_index", (log_id, round_index)).fetchall()
    return [dict(r) for r in rows]


def export_json(conn, limit=None):
    out = {"meta": get_meta(conn), "features": feats.FEATURES,
           "source": [dict(r) for r in conn.execute("SELECT * FROM source ORDER BY log_id")],
           "frames": []}
    sql = "SELECT * FROM frame ORDER BY log_id, round_index, ev_index, seat"
    if limit:
        sql += " LIMIT %d" % int(limit)
    for r in conn.execute(sql):
        d = dict(r)
        d["feats"] = {f["key"]: d[f["col"]] for f in feats.FEATURES}
        out["frames"].append(d)
    return out


def list_feature_values(conn, key):
    f = feats.BY_KEY.get(key)
    if f is None:
        raise ValueError("未知的牌谱特征：%s" % key)
    rows = conn.execute("SELECT %s v, COUNT(*) c FROM frame GROUP BY %s ORDER BY v" % (f["col"], f["col"])).fetchall()
    return [{"value": r["v"], "count": r["c"]} for r in rows]